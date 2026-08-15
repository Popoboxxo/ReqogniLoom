"""
COMP-LA-002 ProviderRegistry — Provider implementations and plugin registry.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-002
REQ-IDs: REQ-L2-LA-001, REQ-L2-LA-005, REQ-L2-LA-007,
         REQ-L3-LA002-001, REQ-L3-LA002-002, REQ-L3-LA002-003

Architecture:
    docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/Components/
    COMP-LA-002_ProviderRegistry/L3_COMP-LA-002_ProviderRegistry_Architecture.md

Interface contract (IF-LA-INT-002):
    CapabilityRouter calls get_provider() -> LlmCapabilityInterface.

Provider isolation:
    Each provider class makes HTTP calls only when its methods are invoked.
    Provider SDK libraries (anthropic, openai, etc.) are imported lazily so that
    the module is importable without them installed. MockLlmProvider is always
    available and requires no external SDK.

Note on ResilienceOrchestrator (IF-L1-050, ADR-LA-04, REQ-082):
    Provider classes own their HTTP transport, but every outbound HTTP/SDK
    call is wrapped by ``llm_adapter.resilient_transport.resilient_call``:
    3 retries with exponential backoff (1s/2s/4s) on transient failures
    (connection errors, timeouts, 5xx, 429), no retry on permanent 4xx
    failures, and one circuit breaker per provider class. The interface
    contracts defined here are unchanged.
"""
from __future__ import annotations

import logging
import os
import time
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from llm_adapter.interface import (
    LlmCapabilityInterface,
    LlmConsistencyResult,
    LlmDecompositionResult,
    LlmResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error codes (shared across modules)
# ---------------------------------------------------------------------------

LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
LLM_PROVIDER_UNKNOWN = "LLM_PROVIDER_UNKNOWN"
LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"


# ---------------------------------------------------------------------------
# Provider configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Runtime configuration resolved from environment variables.

    Attributes:
        provider_name: Selected provider key (e.g. "anthropic").
        timeout: HTTP request timeout in seconds (REQ-L3-LA002-002).
        api_key: Provider API key read from environment.
        api_base_url: Optional base URL override (Ollama, Azure).
        azure_deployment: Azure-specific deployment name.
        azure_api_version: Azure-specific API version string.
        mock_delay: Simulated latency for MockLlmProvider (seconds).
        mock_error_rate: Fraction [0.0–1.0] of calls that should raise an error.
    """

    provider_name: str
    timeout: int = 30
    api_key: str = ""
    api_base_url: Optional[str] = None
    model_name: str = ""
    azure_deployment: Optional[str] = None
    azure_api_version: Optional[str] = None
    mock_delay: float = 0.0
    mock_error_rate: float = 0.0


def _read_env_config() -> ProviderConfig:
    """Read ProviderConfig purely from environment variables.

    Two spellings are accepted for the model and the base URL (issue #276):
    ``docker-compose.yml``, ``deployment/docker-compose.ghcr.yml`` and
    ``.env.example`` all pass ``LLM_MODEL`` / ``LLM_BASE_URL`` through to the
    backend, while this function historically read only ``LLM_MODEL_NAME`` /
    ``LLM_API_BASE_URL`` — so every model and base-URL value a deployment
    configured was silently dropped. The historical names keep precedence, so
    environments that already set them are unaffected;
    :class:`OllamaProvider` and :class:`OpencodeGoProvider` already read the
    short ``LLM_MODEL`` directly, which is the precedent for the alias.

    ``or`` (not ``get(name, default)``) is used deliberately: ``.env.example``
    ships these variables *present but empty*, and an empty value must fall
    through to the alias rather than shadow it.

    Returns:
        Populated ProviderConfig instance.
    """
    return ProviderConfig(
        provider_name=os.environ.get("LLM_PROVIDER", ""),
        timeout=int(os.environ.get("LLM_TIMEOUT", "30")),
        api_key=os.environ.get("LLM_API_KEY", ""),
        api_base_url=(
            os.environ.get("LLM_API_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or None
        ),
        model_name=(
            os.environ.get("LLM_MODEL_NAME") or os.environ.get("LLM_MODEL") or ""
        ),
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT") or None,
        azure_api_version=os.environ.get("AZURE_OPENAI_API_VERSION") or None,
        mock_delay=float(os.environ.get("MOCK_LLM_DELAY", "0.0")),
        mock_error_rate=float(os.environ.get("MOCK_LLM_ERROR_RATE", "0.0")),
    )


def _apply_db_settings(cfg: ProviderConfig) -> ProviderConfig:
    """Overlay persisted LlmSettings (REQ-L2-LLM-001) onto an env-based config.

    Behaviour:
      - If a LlmSettings row exists for the active tenant, its ``provider`` wins
        (it always has a value — default ``mock``).
      - ``api_key`` / ``base_url`` / ``model_name`` override the env value only
        when the stored value is non-empty; otherwise the env fallback stays.
      - Any failure (no active tenant context, DB unavailable, no row) is
        swallowed and the untouched env config is returned — the environment
        remains the source of truth when settings are not configured.

    .. important:: The unconditional ``provider`` precedence above is only
       sound because **a LlmSettings row exists if and only if an admin
       explicitly saved settings** for that tenant (issue #276). Nothing may
       create the row implicitly: ``0026_add_llm_settings`` no longer seeds a
       ``provider=mock`` row, ``0056_unseed_default_llm_settings`` removes the
       pristine ones it left behind, and
       ``SettingsService.get_llm_settings`` serves reads from an *unsaved*,
       env-derived instance. A machine-created row would otherwise pin the
       provider forever and make every later ``LLM_PROVIDER`` change a silent
       no-op — the deployment would keep returning mock placeholders with no
       error anywhere.
    """
    try:
        from persistence.models import LlmSettings

        row = LlmSettings.objects.first()
        if row is None:
            return cfg

        cfg.provider_name = row.provider or cfg.provider_name
        if row.api_key:
            cfg.api_key = row.api_key
        if row.base_url:
            cfg.api_base_url = row.base_url
        if row.model_name:
            cfg.model_name = row.model_name
        return cfg
    except Exception:  # noqa: BLE001 — settings are best-effort; env is the fallback.
        logger.debug("LlmSettings lookup skipped; falling back to environment.")
        return cfg


def _read_config() -> ProviderConfig:
    """Resolve the effective ProviderConfig (DB settings over env fallback).

    REQ-L2-LLM-001: when a LlmSettings row exists for the active tenant its
    values are used; otherwise the configuration is read from environment
    variables (the pre-existing behaviour).
    """
    return _apply_db_settings(_read_env_config())


def resolve_provider_config() -> ProviderConfig:
    """Return the effective provider configuration for the active context.

    REQ-083: public accessor so out-of-request callers (Celery workers) can
    resolve the per-tenant LLM configuration explicitly after restoring the
    tenant context. With an active tenant context the persisted
    :class:`~persistence.models.LlmSettings` row wins; without one the
    environment (global ``LLM_PROVIDER`` etc.) is the fallback.

    Returns:
        The effective :class:`ProviderConfig` (tenant settings overlaid on
        environment defaults).
    """
    return _read_config()


# ---------------------------------------------------------------------------
# Prompt content embedding helpers (REQ-046)
# ---------------------------------------------------------------------------
# Security: user content is delimited to reduce prompt injection surface
# (REQ-080). Artifact titles, descriptions and requirement text are user-
# controlled; wrapping them in an unambiguous delimiter keeps them from being
# interpreted as model instructions.

_USER_CONTENT_DELIMITER = "###"

# Maximum number of characters of artifact/requirement content embedded into a
# single prompt (REQ-046). Descriptions can be arbitrarily long free text;
# without a bound a single oversized artifact would blow up prompt size,
# token cost, and — for some providers — the request itself. Content beyond
# the limit is truncated and marked with an ellipsis so the model (and any
# human reviewing the prompt) can tell the text was cut short.
MAX_PROMPT_CONTENT_CHARS = 4000

_TRUNCATION_MARKER = "... [truncated]"


def truncate_prompt_content(
    text: str, limit: int = MAX_PROMPT_CONTENT_CHARS
) -> str:
    """Truncate *text* to *limit* characters, appending an ellipsis marker.

    Applied to every piece of user-controlled content embedded into a prompt
    (artifact descriptions, requirement text, architecture element
    descriptions) so a single oversized field cannot dominate the prompt.
    Text that already fits within *limit* is returned unchanged.

    Args:
        text: The candidate text to bound.
        limit: Maximum number of characters to keep (default
            :data:`MAX_PROMPT_CONTENT_CHARS`).

    Returns:
        *text* unchanged, or its first *limit* characters followed by the
        truncation marker.
    """
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_MARKER


def _delimit_user_content(content: str) -> str:
    """Wrap user-controlled content in delimiters (REQ-080).

    The returned block clearly separates untrusted artifact/requirement text
    from the surrounding instructions so the model treats it as data, not as
    commands. This reduces the prompt-injection surface without changing the
    embedded text itself.

    Args:
        content: The user-controlled text to delimit.

    Returns:
        The content fenced between ``###`` delimiter lines.
    """
    return f"{_USER_CONTENT_DELIMITER}\n{content}\n{_USER_CONTENT_DELIMITER}"


def _format_artifact_context(
    title: Optional[str], content: Optional[str]
) -> str:
    """Render an artifact's title/content as a prompt-embeddable block (REQ-046).

    Providers previously interpolated only the opaque artifact UUID, forcing the
    model to hallucinate. This helper turns the real text supplied by the
    application layer into a labelled block appended to the prompt.

    Returns an empty string when neither title nor content is supplied, so
    id-only prompts stay byte-for-byte backward compatible.

    Args:
        title: Optional artifact title.
        content: Optional artifact body/description.

    Returns:
        A leading-newline block such as ``"\\n\\nTitle: ...\\nContent:\\n..."`` or
        ``""`` when nothing was provided.
    """
    parts: List[str] = []
    if title:
        parts.append(f"Title: {title}")
    if content:
        parts.append(f"Content:\n{truncate_prompt_content(content)}")
    if not parts:
        return ""
    # Security: delimit user-controlled content (REQ-080).
    return "\n\n" + _delimit_user_content("\n".join(parts))


def _format_artifacts_list(artifacts: Optional[List[dict]]) -> str:
    """Render a list of artifact summaries as a prompt-embeddable block (REQ-046).

    Each entry is expected to be a ``{"id", "title", "content"}`` dict. Returns
    an empty string for an empty/None list so id-only prompts stay backward
    compatible.

    Args:
        artifacts: Optional list of artifact summary dicts.

    Returns:
        A leading-newline block enumerating the artifacts, or ``""`` when empty.
    """
    if not artifacts:
        return ""
    lines: List[str] = []
    for entry in artifacts:
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("id", "")
        title = entry.get("title", "")
        content = truncate_prompt_content(entry.get("content", "") or "")
        lines.append(f"- [{identifier}] {title}: {content}")
    # Security: delimit user-controlled content (REQ-080). The "Artifacts:"
    # label stays outside the fence; the enumerated user text stays inside.
    return "\n\nArtifacts:\n" + _delimit_user_content("\n".join(lines))


# ---------------------------------------------------------------------------
# MockLlmProvider — always-available test/CI/graceful-degradation provider
# ---------------------------------------------------------------------------


class MockLlmProvider(LlmCapabilityInterface):
    """Deterministic mock provider for tests and environments without a real LLM.

    Configured by environment variables (REQ-L3-LA002-001):
        LLM_PROVIDER=mock
        MOCK_LLM_DELAY=<seconds>   — simulated latency (default 0)
        MOCK_LLM_ERROR_RATE=<0-1>  — fraction of calls that raise an error

    The mock always returns stable, predictable LlmResult objects so test
    assertions can rely on specific values without network access.

    Since Issue #196, a configured ``model_name`` (env var or DB-persisted
    ``LlmSettings`` row) overrides ``MODEL_NAME`` here too, for consistency
    with the other providers — the reported ``model`` on results may
    therefore no longer read ``"mock-model-v1"`` in deployments that set a
    model default alongside ``LLM_PROVIDER=mock`` (this is intentional: the
    same config knob behaves the same way regardless of provider).
    """

    PROVIDER_NAME = "mock"
    MODEL_NAME = "mock-model-v1"

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        self._config = config or _read_config()
        # Issue #196: a configured model_name must win over the class-level
        # MODEL_NAME default, mirroring _BaseHttpProvider's precedence
        # (issue #118) so the mock provider reports the same model it was
        # actually configured with instead of always the hardcoded default.
        self.model_name = self._config.model_name or self.MODEL_NAME

    def _simulate(self) -> None:
        """Apply configured delay and optional error simulation."""
        if self._config.mock_delay > 0:
            time.sleep(self._config.mock_delay)
        if self._config.mock_error_rate > 0:
            import random

            if random.random() < self._config.mock_error_rate:
                raise RuntimeError("MockLlmProvider: simulated error")

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmResult:
        """Return a fixed validation result for the given artifact.

        The mock returns deterministic values and builds no real prompt, so the
        ``title`` / ``content`` injected by the application layer (REQ-046) and
        the per-call ``timeout`` (REQ-084) are accepted for interface parity
        but do not alter the output.
        """
        self._simulate()
        return LlmResult(
            score=0.85,
            suggestions=[f"Mock suggestion for artifact {artifact_id}"],
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=42,
        )

    def decompose_requirement(
        self,
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Return a fixed decomposition result for the given requirement.

        ``title`` / ``content`` (REQ-046) and ``timeout`` (REQ-084) are
        accepted for interface parity but do not alter the deterministic mock
        output.
        """
        self._simulate()
        return LlmDecompositionResult(
            score=0.90,
            suggestions=[],
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=100,
            children=[
                {"id": f"{requirement_id}-child-1", "title": "Mock child 1", "type": "sub-requirement"},
                {"id": f"{requirement_id}-child-2", "title": "Mock child 2", "type": "sub-requirement"},
            ],
        )

    def check_consistency(
        self,
        workspace_id: str,
        *,
        artifacts: Optional[List[dict]] = None,
        timeout: Optional[float] = None,
    ) -> LlmConsistencyResult:
        """Return a fixed consistency result for the given workspace.

        ``artifacts`` (REQ-046) and ``timeout`` (REQ-084) are accepted for
        interface parity but do not alter the deterministic mock output.
        """
        self._simulate()
        return LlmConsistencyResult(
            score=0.95,
            suggestions=[],
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=200,
            issues=[],
        )

    def derive_requirements(
        self,
        need_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Return a fixed set of derived requirements for the given need."""
        self._simulate()
        return LlmDecompositionResult(
            score=0.92,
            suggestions=[],
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=120,
            children=[
                {"id": f"{need_id}-derived-1", "title": "Mock Derived Requirement 1", "description": "System shall do X.", "type": "SyReq"},
                {"id": f"{need_id}-derived-2", "title": "Mock Derived Requirement 2", "description": "System shall do Y.", "type": "SyReq"},
            ],
        )

    def complete(
        self,
        prompt: str,
        *,
        purpose: str = "",
        context: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Return deterministic mock JSON matching the AI-derivation flows.

        REQ-L2-AI-002: The mock never performs network I/O. The returned string
        is always valid JSON whose shape matches the ``purpose`` the caller
        declares, so :class:`AiDerivationService` can be exercised end-to-end
        without a real provider.

        Args:
            prompt: The (already formatted) prompt text. Ignored by the mock.
            purpose: One of ``need_to_sysreq``, ``sysreq_to_arch_assign`` or
                ``sysreq_decompose_next_level``.
            context: Optional structured hints. Recognised keys:
                ``n`` (int) and ``arch_element_ids`` (list of id strings).

        Returns:
            A JSON-encoded string appropriate for the declared purpose.
        """
        import json

        self._simulate()
        ctx = context or {}

        if purpose == "need_to_sysreq":
            count = max(1, int(ctx.get("n", 3)))
            return json.dumps(
                [
                    {
                        "title": f"Derived system requirement {i + 1}",
                        "description": "The system shall satisfy the stakeholder need.",
                        "rationale": "Derived from the stakeholder need by the mock provider.",
                    }
                    for i in range(count)
                ]
            )

        if purpose == "sysreq_to_arch_assign":
            arch_ids = list(ctx.get("arch_element_ids", []))
            # Suggest the first available element (empty list if none provided).
            return json.dumps(arch_ids[:1])

        if purpose == "sysreq_decompose_next_level":
            arch_ids = list(ctx.get("arch_element_ids", []))
            first = arch_ids[0] if arch_ids else None
            return json.dumps(
                [
                    {
                        "title": "Decomposed requirement 1",
                        "description": "The subsystem shall refine the parent requirement.",
                        "rationale": "Refinement produced by the mock provider.",
                        "suggested_arch_element_id": first,
                    },
                    {
                        "title": "Decomposed requirement 2",
                        "description": "The subsystem shall cover a second concern.",
                        "rationale": "Refinement produced by the mock provider.",
                        "suggested_arch_element_id": None,
                    },
                ]
            )

        if purpose == "arch_decompose_tree":
            # SysEng 2.0 N1 (architecture.decompose): deterministic, recursive
            # decomposition tree. Each node bundles a child ArchitectureElement
            # with a single derived Requirement so the N1 service can emit the
            # full internal link set (decomposes / derives-from / allocated-to).
            # ``breadth`` children per level, nested ``depth`` levels deep;
            # element_type is a descriptive tag only ("subsystem" for inner
            # nodes, "component" for leaves — the authoritative role is derived
            # from tree position, UMSETZUNGSPLAN_SYSENG_2.0.md §1.2).
            breadth = max(1, int(ctx.get("breadth", 2)))
            depth = max(1, int(ctx.get("depth", 1)))
            title_base = str(ctx.get("element_title") or "System")

            def _build(prefix: str, level: int) -> list:
                nodes = []
                for i in range(breadth):
                    label = f"{prefix}{i + 1}"
                    has_children = level < depth
                    nodes.append(
                        {
                            "title": f"{title_base} · Element {label}",
                            "description": (
                                f"Decomposed element {label} of {title_base}."
                            ),
                            "element_type": (
                                "subsystem" if has_children else "component"
                            ),
                            "requirement": {
                                "title": f"Requirement for {title_base} · {label}",
                                "description": (
                                    f"The element {label} shall fulfil its "
                                    f"allocated part of {title_base}."
                                ),
                                "rationale": (
                                    "Derived by the mock provider during "
                                    "architecture decomposition."
                                ),
                            },
                            "children": (
                                _build(f"{label}.", level + 1)
                                if has_children
                                else []
                            ),
                        }
                    )
                return nodes

            return json.dumps(_build("", 1))

        if purpose == "test_derive_from_requirement":
            # SysEng 2.0 N5 (test.derive_from_requirement): deterministic
            # single TestCase draft (title, description, steps) verifying the
            # given requirement. Unlike the array-shaped purposes above, this
            # returns a single JSON *object* —
            # AiDerivationService._parse_json_object expects that shape.
            req_title = str(ctx.get("req_title") or "Requirement")
            return json.dumps(
                {
                    "title": f"Test: {req_title}",
                    "description": (
                        f"Verifies that the system satisfies '{req_title}'."
                    ),
                    "steps": [
                        {
                            "step": "Set up preconditions for the requirement under test.",
                            "expected_result": "System is in the required initial state.",
                        },
                        {
                            "step": f"Exercise the behaviour described by '{req_title}'.",
                            "expected_result": "The system behaves as specified by the requirement.",
                        },
                    ],
                }
            )

        if purpose == "audit_ai_review":
            # SysEng 2.0 N8 (audit.ai_review): deterministic grouping of the
            # findings AiReviewService handed in via ``context["findings"]``
            # (each a dict with index/rule_id/severity/artifact_ids/scope/
            # scope_artifact_id, see AiReviewService._finding_payload). The
            # mock never invents an index — it only re-emits the 'index'
            # values it was given, grouped by (rule_id, scope_artifact_id),
            # so AiReviewService's referential-integrity resolution always
            # finds a match (§4 Phase 4b acceptance criterion).
            findings = ctx.get("findings")
            findings = findings if isinstance(findings, list) else []
            groups: Dict[tuple, List[dict]] = {}
            order: List[tuple] = []
            for entry in findings:
                if not isinstance(entry, dict):
                    continue
                key = (entry.get("rule_id"), entry.get("scope_artifact_id"))
                if key not in groups:
                    groups[key] = []
                    order.append(key)
                groups[key].append(entry)

            packages = []
            for key in order:
                rule_id, scope_artifact_id = key
                members = groups[key]
                scope_label = f" (scope: {scope_artifact_id})" if scope_artifact_id else ""
                packages.append(
                    {
                        "title": f"Refactoring package: {rule_id}{scope_label}",
                        "rationale": (
                            f"Bundles {len(members)} finding(s) for rule "
                            f"'{rule_id}'{scope_label} into one strategic "
                            "correction instead of fixing each one in isolation."
                        ),
                        "finding_indices": [
                            m.get("index") for m in members if "index" in m
                        ],
                    }
                )
            return json.dumps(packages)

        if purpose == "traceability_suggest_links":
            # SysEng 2.0 N3 (traceability.suggest_links), first stage —
            # deterministic findings-ranking, no vector search
            # (UMSETZUNGSPLAN_SYSENG_2.0.md §3.2). TraceabilitySuggestService
            # hands in ctx["findings"], each a dict with a 'finding_index'
            # and a 'candidates' array that is ALREADY keyword-overlap-
            # ranked highest-score-first (see
            # TraceabilitySuggestService._build_candidates). The mock never
            # invents a candidate_index or an artifact id — it only re-emits
            # the 'candidate_index' values it was given, preserving their
            # given order, so the service's referential-integrity
            # resolution always finds a match (§4 Phase 4b acceptance
            # criterion: "keine pgvector-Abhängigkeit im Code").
            findings = ctx.get("findings")
            findings = findings if isinstance(findings, list) else []
            suggestions = []
            for entry in findings:
                if not isinstance(entry, dict):
                    continue
                candidates = entry.get("candidates")
                candidates = candidates if isinstance(candidates, list) else []
                indices = [
                    c.get("candidate_index")
                    for c in candidates
                    if isinstance(c, dict) and "candidate_index" in c
                ]
                top_title = (
                    candidates[0].get("title")
                    if candidates and isinstance(candidates[0], dict)
                    else None
                )
                rationale = (
                    f"Highest keyword overlap with '{top_title}'."
                    if top_title
                    else "No distinguishing keyword overlap found among the candidates."
                )
                suggestions.append(
                    {
                        "finding_index": entry.get("finding_index"),
                        "ranked_candidate_indices": indices,
                        "rationale": rationale,
                    }
                )
            return json.dumps(suggestions)

        if purpose == "context_change_impact":
            # REQ-L2-MC-004 (Phase 2, Task 6: context.change_impact) —
            # deterministic ranking mock. Like ``traceability_suggest_links``
            # above, it never invents an id: it only re-emits the 'id'
            # values handed in via ``ctx["candidates"]`` (each already a
            # real trace-linked entity resolved by the MCP tool), so the
            # caller's referential-integrity merge always finds a match.
            candidates = ctx.get("candidates")
            candidates = candidates if isinstance(candidates, list) else []
            return json.dumps(
                [
                    {
                        "id": c.get("id"),
                        "likely_affected": True,
                        "rationale": (
                            "Directly linked to the changed entity via the "
                            "trace graph (mock provider — no semantic "
                            "assessment performed)."
                        ),
                    }
                    for c in candidates
                    if isinstance(c, dict) and c.get("id")
                ]
            )

        if purpose == "derive_risks_from_architecture":
            # Phase 3 (ai_derivation.derive_risks_from_architecture):
            # deterministic risk drafts for the given architecture element.
            # Mirrors the array-shaped purposes above (e.g.
            # sysreq_decompose_next_level) — always emits valid enum values
            # for probability/impact so the happy path never hits the
            # service's defensive clamp, which is instead exercised by a
            # capturing fake provider in tests.
            ae_title = str(ctx.get("ae_title") or "Architecture element")
            return json.dumps(
                [
                    {
                        "title": f"Delivery risk for {ae_title}",
                        "description": (
                            f"Risk that '{ae_title}' is not delivered on time "
                            "or does not meet its quality bar."
                        ),
                        "probability": "medium",
                        "impact": "medium",
                        "category": "technical",
                    }
                ]
            )

        if purpose == "derive_glossary_from_workspace":
            # Phase 3, Task 4 (ai_derivation.derive_glossary_from_workspace):
            # deterministic single-term draft. Never invents workspace
            # content — it just confirms a term was requested for the given
            # workspace, mirroring the shape the real prompt asks for.
            workspace_id = str(ctx.get("workspace_id") or "workspace")
            return json.dumps(
                [
                    {
                        "term": f"Term for {workspace_id}",
                        "definition": (
                            "Placeholder definition extracted from the "
                            "workspace's requirements and architecture "
                            "(mock provider — no semantic extraction "
                            "performed)."
                        ),
                        "synonyms": [],
                        "abbreviation": "",
                    }
                ]
            )

        if purpose == "goal_aggregate":
            # MainGoalService.generate_ai (Goal/MainGoal feature, fix #229):
            # unlike every other purpose above, ``goal_aggregate`` expects
            # free-form prose (2-4 sentences), not a JSON array/object — the
            # factory prompt template explicitly says "Respond with the
            # MainGoal text only" (persistence.models.PROMPT_TEMPLATE_DEFAULTS).
            # Falling through to the generic ``json.dumps([])`` fallback below
            # produced the literal string "[]" as MainGoal.content. The mock
            # never parses the prompt (context/prompt are ignored per this
            # method's docstring), so it echoes the goal titles the caller
            # already resolved into ``context["goal_titles"]`` instead of
            # inventing content.
            goal_titles = ctx.get("goal_titles")
            goal_titles = [str(t) for t in goal_titles] if isinstance(goal_titles, list) else []
            if goal_titles:
                joined = "; ".join(goal_titles)
                return (
                    f"This workspace's overarching goal is to achieve: {joined}. "
                    "It unifies the individual goals listed above into one "
                    "shared direction (mock provider — no semantic synthesis "
                    "performed)."
                )
            return (
                "This workspace's overarching goal aggregates its current "
                "goals into one shared direction (mock provider placeholder "
                "— no goals were supplied)."
            )

        if purpose == "derive_adr_from_decision":
            # Phase 3, Task 5 (ai_derivation.derive_adr_from_decision):
            # deterministic single ADR draft (title, description, context,
            # consequences) structuring the given free-text decision. Unlike
            # the array-shaped purposes above, this returns a single JSON
            # *object* — AiDerivationService._parse_json_object expects that
            # shape (mirrors "test_derive_from_requirement" above).
            decision_description = str(
                ctx.get("decision_description") or "the decision"
            )
            return json.dumps(
                {
                    "title": f"Decision: {decision_description[:60]}",
                    "description": decision_description,
                    "context": (
                        "Context extracted from the free-text decision "
                        "description (mock provider — no semantic "
                        "extraction performed)."
                    ),
                    "consequences": (
                        "Consequences not yet assessed (mock provider "
                        "placeholder)."
                    ),
                }
            )

        return json.dumps([])


# ---------------------------------------------------------------------------
# Stub provider base — common HTTP plumbing for real providers
# ---------------------------------------------------------------------------


class _BaseHttpProvider(LlmCapabilityInterface):
    """Shared HTTP request helpers for real providers.

    Subclasses must set PROVIDER_NAME and MODEL_NAME and override the three
    abstract capability methods.
    """

    PROVIDER_NAME: str = ""
    MODEL_NAME: str = ""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        # Issue #118: a configured model_name (LLM_MODEL_NAME env or the
        # DB-persisted LlmSettings row, see _apply_db_settings) must win over
        # the class-level MODEL_NAME default - subclasses must call the real
        # API with self.model_name, never self.MODEL_NAME directly.
        self.model_name = config.model_name or self.MODEL_NAME

    def _request(self, payload: dict) -> dict:
        """Execute an HTTP request with timeout handling.

        This stub is intended to be overridden by concrete providers. Real
        providers call their SDK or use requests/httpx here.

        Raises:
            TimeoutError: When the request exceeds the configured timeout.
            RuntimeError: On non-success HTTP responses.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}._request() not implemented. "
            "Install the provider SDK and override this method."
        )

    def _resilient(
        self,
        call: Callable[[], Any],
        timeout_seconds: Optional[float] = None,
    ) -> Any:
        """Run an outbound HTTP/SDK call under the resilience policy (REQ-082).

        Applies retry with exponential backoff (1s/2s/4s) on transient
        failures, no retry on permanent 4xx failures, and the per-provider
        circuit breaker. Raises
        :class:`~llm_adapter.resilient_transport.LlmTransportError` on final
        failure so the CapabilityRouter maps it to LLM_PROVIDER_ERROR.

        Args:
            call: Zero-arg callable performing the actual outbound request.
            timeout_seconds: Optional per-call timeout override (REQ-084);
                the configured provider timeout is used when omitted.

        Returns:
            The transport call's result.
        """
        # Lazy import to avoid import-time coupling to the resilience app.
        from llm_adapter.resilient_transport import resilient_call  # noqa: PLC0415

        return resilient_call(
            call,
            provider_name=self.PROVIDER_NAME,
            timeout_seconds=(
                timeout_seconds
                if timeout_seconds is not None
                else self._config.timeout
            ),
        )

    def _effective_timeout(self, timeout: Optional[float]) -> float:
        """Resolve the per-call timeout (REQ-084): override or config default."""
        return float(timeout) if timeout is not None else float(self._config.timeout)

    def _invoke_chat(
        self, prompt: str, timeout: Optional[float] = None
    ) -> tuple[str, Optional[int]]:
        """Invoke the provider's ``_chat`` transport, forwarding ``timeout``.

        The ``timeout`` keyword is only forwarded when explicitly given so
        that simplified ``_chat(prompt)`` doubles (tests, custom providers)
        keep working unchanged.
        """
        chat = getattr(self, "_chat", None)
        if chat is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} does not expose a _chat transport."
            )
        if timeout is None:
            return chat(prompt)
        return chat(prompt, timeout=timeout)

    def complete(
        self,
        prompt: str,
        *,
        purpose: str = "",
        context: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Return the raw completion text for a free-form prompt (REQ-L2-AI-002).

        Real providers derive the completion from ``self._chat`` (defined by the
        concrete OpenAI/Ollama/Azure subclasses). ``purpose`` and ``context`` are
        hints for deterministic mocks only and are ignored here. ``timeout``
        (REQ-084) is forwarded to the transport when given.

        Raises:
            NotImplementedError: If the concrete provider does not expose a
                ``_chat`` transport helper.
        """
        if getattr(self, "_chat", None) is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} does not support free-form completion."
            )
        text, _token_usage = self._invoke_chat(prompt, timeout)
        return text


# ---------------------------------------------------------------------------
# Shared parsing helper for derive_requirements (REQ-041)
# ---------------------------------------------------------------------------


def _parse_derivation_response(text: str) -> dict:
    """Parse a derive_requirements completion into a data dict.

    Some models wrap the JSON payload in markdown fences; these are stripped
    before parsing. On malformed JSON the response is wrapped into a single
    generated requirement so callers always receive a usable structure. This
    mirrors the fallback behaviour of :class:`OpenAiProvider`.

    Args:
        text: The raw completion text returned by the provider.

    Returns:
        A dict with (at least) a ``children`` key.
    """
    import json

    try:
        cleaned = text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "Provider returned invalid JSON for derive_requirements: %s", text
        )
        return {"children": [{"title": "Generated Req", "description": text}]}


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------


class AnthropicProvider(_BaseHttpProvider):
    """LLM provider backed by Anthropic Claude (REQ-L3-LA002-001).

    Requires: pip install anthropic
    Env vars: LLM_API_KEY=<your-anthropic-key>
    """

    PROVIDER_NAME = "anthropic"
    MODEL_NAME = "claude-3-opus-20240229"

    def _chat(
        self, prompt: str, timeout: Optional[float] = None
    ) -> tuple[str, Optional[int]]:
        """Send a message to the Anthropic API and return (text, token_usage).

        Provides the free-form transport used by the inherited ``complete``
        method (REQ-048) so free-form flows such as derive_requirements
        (REQ-041) work without duplicating SDK plumbing. ``timeout`` (REQ-084)
        overrides the configured provider timeout for this call.
        """
        try:
            import anthropic  # noqa: PLC0415 (lazy import intentional)
        except ImportError as exc:
            raise LlmNotConfiguredError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

        effective_timeout = self._effective_timeout(timeout)
        client = anthropic.Anthropic(
            api_key=self._config.api_key,
            base_url=self._config.api_base_url or None,
        )
        message = self._resilient(
            lambda: client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                timeout=effective_timeout,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout_seconds=effective_timeout,
        )
        text = message.content[0].text
        token_usage = (
            message.usage.input_tokens + message.usage.output_tokens
            if hasattr(message, "usage")
            else None
        )
        return text, token_usage

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmResult:
        """Call Anthropic API to validate an artifact (content embedded, REQ-046)."""
        try:
            import anthropic  # noqa: PLC0415 (lazy import intentional)

            effective_timeout = self._effective_timeout(timeout)
            client = anthropic.Anthropic(
                api_key=self._config.api_key,
                base_url=self._config.api_base_url or None,
            )
            message = self._resilient(
                lambda: client.messages.create(
                    model=self.model_name,
                    max_tokens=1024,
                    timeout=effective_timeout,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Validate the following artifact (id: {artifact_id})."
                                f"{_format_artifact_context(title, content)}\n\n"
                                "Return a JSON object with keys: score (0-1), suggestions (list of strings)."
                            ),
                        }
                    ],
                ),
                timeout_seconds=effective_timeout,
            )
            import json

            raw = message.content[0].text
            data = json.loads(raw)
            token_usage = (
                message.usage.input_tokens + message.usage.output_tokens
                if hasattr(message, "usage")
                else None
            )
            return LlmResult(
                score=float(data.get("score", 0.0)),
                suggestions=data.get("suggestions", []),
                provider=self.PROVIDER_NAME,
                model=self.model_name,
                token_usage=token_usage,
            )
        except ImportError as exc:
            raise LlmNotConfiguredError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

    def decompose_requirement(
        self,
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Call Anthropic API to decompose a requirement (content embedded, REQ-046)."""
        try:
            import anthropic  # noqa: PLC0415

            effective_timeout = self._effective_timeout(timeout)
            client = anthropic.Anthropic(
                api_key=self._config.api_key,
                base_url=self._config.api_base_url or None,
            )
            message = self._resilient(
                lambda: client.messages.create(
                    model=self.model_name,
                    max_tokens=4096,
                    timeout=effective_timeout,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Decompose the following requirement (id: {requirement_id}) "
                                f"into sub-requirements.{_format_artifact_context(title, content)}\n\n"
                                "Return JSON: {score, suggestions, children: [{id, title, type}]}"
                            ),
                        }
                    ],
                ),
                timeout_seconds=effective_timeout,
            )
            import json

            raw = message.content[0].text
            data = json.loads(raw)
            token_usage = (
                message.usage.input_tokens + message.usage.output_tokens
                if hasattr(message, "usage")
                else None
            )
            return LlmDecompositionResult(
                score=float(data.get("score", 0.0)),
                suggestions=data.get("suggestions", []),
                provider=self.PROVIDER_NAME,
                model=self.model_name,
                token_usage=token_usage,
                children=data.get("children", []),
            )
        except ImportError as exc:
            raise LlmNotConfiguredError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

    def check_consistency(
        self,
        workspace_id: str,
        *,
        artifacts: Optional[List[dict]] = None,
        timeout: Optional[float] = None,
    ) -> LlmConsistencyResult:
        """Call Anthropic API to check workspace consistency (content embedded, REQ-046)."""
        try:
            import anthropic  # noqa: PLC0415

            effective_timeout = self._effective_timeout(timeout)
            client = anthropic.Anthropic(
                api_key=self._config.api_key,
                base_url=self._config.api_base_url or None,
            )
            message = self._resilient(
                lambda: client.messages.create(
                    model=self.model_name,
                    max_tokens=4096,
                    timeout=effective_timeout,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Check consistency across the artifacts in workspace "
                                f"{workspace_id}.{_format_artifacts_list(artifacts)}\n\n"
                                "Return JSON: {score, suggestions, issues: [{id, severity, description}]}"
                            ),
                        }
                    ],
                ),
                timeout_seconds=effective_timeout,
            )
            import json

            raw = message.content[0].text
            data = json.loads(raw)
            token_usage = (
                message.usage.input_tokens + message.usage.output_tokens
                if hasattr(message, "usage")
                else None
            )
            return LlmConsistencyResult(
                score=float(data.get("score", 0.0)),
                suggestions=data.get("suggestions", []),
                provider=self.PROVIDER_NAME,
                model=self.model_name,
                token_usage=token_usage,
                issues=data.get("issues", []),
            )
        except ImportError as exc:
            raise LlmNotConfiguredError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

    def derive_requirements(
        self,
        need_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Derive System Requirements from a Stakeholder Need (REQ-041, REQ-048).

        The provider works only with the identifier it is handed; fetching the
        StakeholderNeed and rendering configured prompt templates is the
        responsibility of the application layer (AiDerivationService), which
        keeps this Layer-3 provider free of direct persistence access. The
        full artifact content is injected by that layer in REQ-046.
        """
        text = self.complete(
            f"Derive System Requirements from Stakeholder Need {need_id}. "
            "Return JSON: {score, suggestions, "
            "children: [{title, description, type}]}",
            purpose="derive_requirements",
            timeout=timeout,
        )
        data = _parse_derivation_response(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 1.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=None,
            children=data.get("children", []),
        )


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAiProvider(_BaseHttpProvider):
    """LLM provider backed by OpenAI (REQ-L3-LA002-001).

    Requires: pip install openai
    Env vars: LLM_API_KEY=<your-openai-key>
    """

    PROVIDER_NAME = "openai"
    MODEL_NAME = "gpt-4"

    def _chat(
        self, prompt: str, timeout: Optional[float] = None
    ) -> tuple[str, Optional[int]]:
        """Send a chat completion request and return (text, token_usage)."""
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise LlmNotConfiguredError(
                "openai SDK not installed. Run: pip install openai"
            ) from exc

        effective_timeout = self._effective_timeout(timeout)
        client = OpenAI(
            api_key=self._config.api_key,
            base_url=self._config.api_base_url or None,
            timeout=effective_timeout,
        )
        response = self._resilient(
            lambda: client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout_seconds=effective_timeout,
        )
        text = response.choices[0].message.content or ""
        token_usage = (
            response.usage.total_tokens if response.usage else None
        )
        return text, token_usage

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Validate the following artifact (id: {artifact_id})."
            f"{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions}",
            timeout,
        )
        data = json.loads(text)
        return LlmResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
        )

    def decompose_requirement(
        self,
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Decompose the following requirement (id: {requirement_id}) "
            f"into sub-requirements.{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions, children: [{id, title, type}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def derive_requirements(
        self,
        need_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        # The provider works only with the identifier it is handed; fetching the
        # StakeholderNeed and rendering configured prompt templates is the
        # responsibility of the application layer (AiDerivationService), which
        # keeps this Layer-3 provider free of direct persistence access (REQ-048).
        import json

        prompt_text = (
            f"Derive System Requirements from Stakeholder Need {need_id}. "
            "Return JSON: {score, suggestions, "
            "children: [{title, description, type}]}"
        )

        text, token_usage = self._invoke_chat(prompt_text, timeout)

        try:
            # Some models wrap JSON in markdown fences; strip them before parsing.
            text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(
                "OpenAI provider returned invalid JSON for derive_requirements: %s",
                text,
            )
            data = {"children": [{"title": "Generated Req", "description": text}]}

        return LlmDecompositionResult(
            score=float(data.get("score", 1.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def check_consistency(
        self,
        workspace_id: str,
        *,
        artifacts: Optional[List[dict]] = None,
        timeout: Optional[float] = None,
    ) -> LlmConsistencyResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Check consistency across the artifacts in workspace "
            f"{workspace_id}.{_format_artifacts_list(artifacts)}\n\n"
            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmConsistencyResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
            issues=data.get("issues", []),
        )


# ---------------------------------------------------------------------------
# Ollama provider (local)
# ---------------------------------------------------------------------------


class OllamaProvider(_BaseHttpProvider):
    """LLM provider backed by a local Ollama instance (REQ-L3-LA002-001).

    Env vars:
        LLM_API_BASE_URL=http://localhost:11434  (default)
        LLM_MODEL_NAME / LLM_MODEL=llama3  (overrides MODEL_NAME, optional)

    A DB-persisted ``LlmSettings.model_name`` row takes precedence over both
    of the above (see Issue #196) — env vars are only the fallback for
    unconfigured deployments.
    """

    PROVIDER_NAME = "ollama"
    MODEL_NAME = "llama3"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        if not (config.api_base_url or "").strip():
            raise LlmNotConfiguredError(
                "Ollama base_url is not configured. "
                "Set OLLAMA_BASE_URL environment variable."
            )
        self._base_url = config.api_base_url
        # Issue #196: a configured model_name (LLM_MODEL_NAME env or the
        # DB-persisted LlmSettings row) must win over the class-level
        # MODEL_NAME default. self.model_name (set by _BaseHttpProvider from
        # config.model_name or MODEL_NAME) is the canonical source - do not
        # re-derive a parallel value from os.environ here, or a DB-configured
        # model_name that never reached the process environment is silently
        # ignored (issue #118's guarantee only holds if callers actually use
        # self.model_name).

    def _chat(
        self, prompt: str, timeout: Optional[float] = None
    ) -> tuple[str, Optional[int]]:
        """POST to Ollama /api/generate endpoint."""
        import json as _json

        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "requests library not installed. Run: pip install requests"
            ) from exc

        url = f"{self._base_url}/api/generate"
        effective_timeout = self._effective_timeout(timeout)

        def _post():
            # raise_for_status inside the resilient call so 5xx responses are
            # classified (and retried) by status code (REQ-082).
            response = requests.post(
                url,
                json={"model": self.model_name, "prompt": prompt, "stream": False},
                timeout=effective_timeout,
            )
            response.raise_for_status()
            return response

        resp = self._resilient(_post, timeout_seconds=effective_timeout)
        data = resp.json()
        text = data.get("response", "")
        # Ollama does not expose token counts in the same format; use eval_count
        token_usage = data.get("eval_count") or None
        return text, token_usage

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Validate the following artifact (id: {artifact_id})."
            f"{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions}",
            timeout,
        )
        data = json.loads(text)
        return LlmResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
        )

    def decompose_requirement(
        self,
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Decompose the following requirement (id: {requirement_id}) "
            f"into sub-requirements.{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions, children: [{id, title, type}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def check_consistency(
        self,
        workspace_id: str,
        *,
        artifacts: Optional[List[dict]] = None,
        timeout: Optional[float] = None,
    ) -> LlmConsistencyResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Check consistency across the artifacts in workspace "
            f"{workspace_id}.{_format_artifacts_list(artifacts)}\n\n"
            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmConsistencyResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
            issues=data.get("issues", []),
        )

    def derive_requirements(
        self,
        need_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Derive System Requirements from a Stakeholder Need (REQ-041, REQ-048).

        Fetching the StakeholderNeed and rendering configured prompt templates
        is the responsibility of the application layer (AiDerivationService);
        the full artifact content is injected by that layer in REQ-046.
        """
        text = self.complete(
            f"Derive System Requirements from Stakeholder Need {need_id}. "
            "Return JSON: {score, suggestions, "
            "children: [{title, description, type}]}",
            purpose="derive_requirements",
            timeout=timeout,
        )
        data = _parse_derivation_response(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 1.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=None,
            children=data.get("children", []),
        )


# ---------------------------------------------------------------------------
# Azure OpenAI provider (REQ-L2-LA-007)
# ---------------------------------------------------------------------------


class AzureOpenAiProvider(_BaseHttpProvider):
    """LLM provider backed by Azure OpenAI (REQ-L2-LA-007, REQ-L3-LA002-001).

    Requires: pip install openai
    Env vars:
        LLM_API_KEY=<azure-api-key>
        LLM_API_BASE_URL=https://<resource>.openai.azure.com
        AZURE_OPENAI_DEPLOYMENT=<deployment-name>
        AZURE_OPENAI_API_VERSION=2024-02-01
    """

    PROVIDER_NAME = "azure"
    MODEL_NAME = "gpt-4"

    def _chat(
        self, prompt: str, timeout: Optional[float] = None
    ) -> tuple[str, Optional[int]]:
        """Send a chat completion request via Azure OpenAI endpoint."""
        try:
            from openai import AzureOpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise LlmNotConfiguredError(
                "openai SDK not installed. Run: pip install openai"
            ) from exc

        effective_timeout = self._effective_timeout(timeout)
        client = AzureOpenAI(
            api_key=self._config.api_key,
            azure_endpoint=self._config.api_base_url or "",
            azure_deployment=self._config.azure_deployment or "",
            api_version=self._config.azure_api_version or "2024-02-01",
            timeout=effective_timeout,
        )
        response = self._resilient(
            lambda: client.chat.completions.create(
                model=self._config.azure_deployment or self.model_name,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout_seconds=effective_timeout,
        )
        text = response.choices[0].message.content or ""
        token_usage = response.usage.total_tokens if response.usage else None
        return text, token_usage

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Validate the following artifact (id: {artifact_id})."
            f"{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions}",
            timeout,
        )
        data = json.loads(text)
        return LlmResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._config.azure_deployment or self.model_name,
            token_usage=token_usage,
        )

    def decompose_requirement(
        self,
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Decompose the following requirement (id: {requirement_id}) "
            f"into sub-requirements.{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions, children: [{id, title, type}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._config.azure_deployment or self.model_name,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def check_consistency(
        self,
        workspace_id: str,
        *,
        artifacts: Optional[List[dict]] = None,
        timeout: Optional[float] = None,
    ) -> LlmConsistencyResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Check consistency across the artifacts in workspace "
            f"{workspace_id}.{_format_artifacts_list(artifacts)}\n\n"
            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmConsistencyResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._config.azure_deployment or self.model_name,
            token_usage=token_usage,
            issues=data.get("issues", []),
        )

    def derive_requirements(
        self,
        need_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Derive System Requirements from a Stakeholder Need (REQ-041, REQ-048).

        Fetching the StakeholderNeed and rendering configured prompt templates
        is the responsibility of the application layer (AiDerivationService);
        the full artifact content is injected by that layer in REQ-046.
        """
        text = self.complete(
            f"Derive System Requirements from Stakeholder Need {need_id}. "
            "Return JSON: {score, suggestions, "
            "children: [{title, description, type}]}",
            purpose="derive_requirements",
            timeout=timeout,
        )
        data = _parse_derivation_response(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 1.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._config.azure_deployment or self.model_name,
            token_usage=None,
            children=data.get("children", []),
        )


# ---------------------------------------------------------------------------
# OpenCode Go provider (ad-hoc addition, project-owner request)
# ---------------------------------------------------------------------------


class OpencodeGoProvider(_BaseHttpProvider):
    """LLM provider backed by OpenCode Go's OpenAI-compatible endpoint.

    OpenCode Go (https://opencode.ai) exposes an OpenAI-compatible chat
    completions API, so this provider reuses the ``openai`` SDK client with a
    custom ``base_url`` instead of adding a new HTTP dependency — the same
    "SDK client + custom endpoint" shape :class:`AzureOpenAiProvider` already
    uses for Azure OpenAI (REQ-L3-LA002-001).

    Env vars:
        LLM_API_KEY=<your-opencode-go-key>
        LLM_API_BASE_URL=https://opencode.ai/zen/go/v1  (default; override to
            point at a self-hosted or alternate OpenCode Go endpoint)
        LLM_MODEL_NAME / LLM_MODEL=<model-id>  (overrides MODEL_NAME,
            optional — see https://opencode.ai/docs/providers for available
            model ids)

    A DB-persisted ``LlmSettings.model_name`` row takes precedence over both
    of the above (see Issue #196) — env vars are only the fallback for
    unconfigured deployments.
    """

    PROVIDER_NAME = "opencode_go"
    MODEL_NAME = "claude-sonnet-4-5"
    DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._base_url = (config.api_base_url or self.DEFAULT_BASE_URL).strip()
        # Issue #196: see OllamaProvider.__init__ for why the configured
        # self.model_name (set by _BaseHttpProvider) must be used here
        # instead of re-deriving the model from os.environ.

    def _chat(
        self, prompt: str, timeout: Optional[float] = None
    ) -> tuple[str, Optional[int]]:
        """Send a chat completion request to the OpenCode Go endpoint."""
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise LlmNotConfiguredError(
                "openai SDK not installed (required for the opencode_go "
                "provider, which reuses the OpenAI-compatible client). "
                "Run: pip install openai"
            ) from exc

        effective_timeout = self._effective_timeout(timeout)
        client = OpenAI(
            api_key=self._config.api_key,
            base_url=self._base_url,
            timeout=effective_timeout,
        )
        response = self._resilient(
            lambda: client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout_seconds=effective_timeout,
        )
        text = response.choices[0].message.content or ""
        token_usage = response.usage.total_tokens if response.usage else None
        return text, token_usage

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Validate the following artifact (id: {artifact_id})."
            f"{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions}",
            timeout,
        )
        data = json.loads(text)
        return LlmResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
        )

    def decompose_requirement(
        self,
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Decompose the following requirement (id: {requirement_id}) "
            f"into sub-requirements.{_format_artifact_context(title, content)}\n\n"
            "Return JSON: {score, suggestions, children: [{id, title, type}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def check_consistency(
        self,
        workspace_id: str,
        *,
        artifacts: Optional[List[dict]] = None,
        timeout: Optional[float] = None,
    ) -> LlmConsistencyResult:
        import json

        text, token_usage = self._invoke_chat(
            f"Check consistency across the artifacts in workspace "
            f"{workspace_id}.{_format_artifacts_list(artifacts)}\n\n"
            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}",
            timeout,
        )
        data = json.loads(text)
        return LlmConsistencyResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=token_usage,
            issues=data.get("issues", []),
        )

    def derive_requirements(
        self,
        need_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Derive System Requirements from a Stakeholder Need (REQ-041, REQ-048).

        Fetching the StakeholderNeed and rendering configured prompt templates
        is the responsibility of the application layer (AiDerivationService);
        the full artifact content is injected by that layer in REQ-046.
        """
        text = self.complete(
            f"Derive System Requirements from Stakeholder Need {need_id}. "
            "Return JSON: {score, suggestions, "
            "children: [{title, description, type}]}",
            purpose="derive_requirements",
            timeout=timeout,
        )
        data = _parse_derivation_response(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 1.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.model_name,
            token_usage=None,
            children=data.get("children", []),
        )


# ---------------------------------------------------------------------------
# Plugin registry — REQ-L3-LA002-003
# ---------------------------------------------------------------------------

# Dict-based registry: maps provider_name -> provider class.
# New providers can be registered without touching the CapabilityRouter.
_PROVIDER_REGISTRY: Dict[str, Type[LlmCapabilityInterface]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAiProvider,
    "ollama": OllamaProvider,
    "azure": AzureOpenAiProvider,
    "opencode_go": OpencodeGoProvider,
    "mock": MockLlmProvider,
}


def register_provider(
    name: str,
) -> Callable[[Type[LlmCapabilityInterface]], Type[LlmCapabilityInterface]]:
    """Class decorator to register a new provider (REQ-L3-LA002-003).

    Usage::

        @register_provider("custom")
        class CustomProvider(LlmCapabilityInterface):
            ...

    Args:
        name: Provider name that users set via LLM_PROVIDER env var.

    Returns:
        Decorator that registers the class and returns it unchanged.
    """

    def _decorator(cls: Type[LlmCapabilityInterface]) -> Type[LlmCapabilityInterface]:
        _PROVIDER_REGISTRY[name] = cls
        return cls

    return _decorator


def get_provider(config: Optional[ProviderConfig] = None) -> LlmCapabilityInterface:
    """Instantiate and return the configured LLM provider (IF-LA-INT-002).

    Reads LLM_PROVIDER from the environment (or uses provided config).

    Args:
        config: Optional pre-built config; if None, reads env vars.

    Returns:
        An instance of the requested LlmCapabilityInterface implementation.

    Raises:
        LlmNotConfiguredError: If LLM_PROVIDER is not set.
        LlmProviderUnknownError: If LLM_PROVIDER names an unregistered provider.
    """
    cfg = config or _read_config()

    if not cfg.provider_name:
        raise LlmNotConfiguredError(
            "LLM_PROVIDER environment variable is not set. "
            "Set LLM_PROVIDER to one of: "
            + ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        )

    provider_cls = _PROVIDER_REGISTRY.get(cfg.provider_name)
    if provider_cls is None:
        raise LlmProviderUnknownError(
            f"Unknown LLM provider: {cfg.provider_name!r}. "
            "Registered providers: " + ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        )

    return provider_cls(cfg)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class LlmNotConfiguredError(Exception):
    """Raised when no LLM provider is configured (code: LLM_NOT_CONFIGURED)."""

    code: str = LLM_NOT_CONFIGURED


class LlmProviderUnknownError(Exception):
    """Raised when LLM_PROVIDER names an unknown provider (code: LLM_PROVIDER_UNKNOWN)."""

    code: str = LLM_PROVIDER_UNKNOWN


__all__ = [
    # Public API
    "get_provider",
    "register_provider",
    "resolve_provider_config",
    "ProviderConfig",
    # Prompt content helpers (REQ-046)
    "truncate_prompt_content",
    "MAX_PROMPT_CONTENT_CHARS",
    # Provider implementations
    "MockLlmProvider",
    "AnthropicProvider",
    "OpenAiProvider",
    "OllamaProvider",
    "AzureOpenAiProvider",
    # Error codes
    "LLM_NOT_CONFIGURED",
    "LLM_PROVIDER_UNKNOWN",
    "LLM_PROVIDER_ERROR",
    # Exceptions
    "LlmNotConfiguredError",
    "LlmProviderUnknownError",
]
