"""
COMP-AS-021 AiDerivationService — LLM-backed draft generation (REQ-L2-AI-001/002).

This service implements three *explicit, user-triggered* AI derivation flows.
Every flow follows the **Draft/Accept** pattern (REQ-L2-AI-001):

  * The service only ever returns proposed data ("drafts"). Nothing is
    persisted here.
  * "Accepting" a draft is the client's responsibility — it re-uses the
    existing create/update REST endpoints to persist whichever drafts the
    user selected.

Flows (REQ-L2-AI-002):
  1. :meth:`derive_requirements_from_need` — StakeholderNeed -> SystemRequirements
  2. :meth:`suggest_architecture_for_requirement` — Requirement -> ArchitectureElement ids
  3. :meth:`decompose_requirement_next_level` — Requirement -> next-level requirement drafts
  4. :meth:`derive_testcase_from_requirement` — Requirement -> TestCase draft
     (SysEng 2.0 N5, ``test.derive_from_requirement``). Standard feature, no
     RuleEngine/preset gate — unlike the architecture-decompose copilot (N1)
     this flow has no rigor-preset dependency.
  5. :meth:`derive_risks_from_architecture` — ArchitectureElement -> Risk
     drafts (Phase 3, ``ai_derivation.derive_risks_from_architecture``).
     Standard feature, no rigor-preset gate, same shape as flow 4.
  6. :meth:`derive_glossary_from_workspace` — Workspace -> GlossaryTerm
     drafts (Phase 3, ``ai_derivation.derive_glossary_from_workspace``).
     Standard feature, no rigor-preset gate. Unlike flows 1-5, the write
     path creates NO trace link back to the source (a bare Workspace id is
     not a resolvable TraceLinkService source, see
     :meth:`_write_glossary_term_draft`).
  7. :meth:`derive_adr_from_decision` — free-text Decision -> Adr draft
     (Phase 3, Task 5, ``ai_derivation.derive_adr_from_decision``). Standard
     feature, no rigor-preset gate. The INPUT is raw free text (no source
     entity id at all — there is nothing to fetch), so — like flow 6 — the
     write path creates NO trace link. Unlike flow 6, this is NOT because
     the target type cannot be linked (an ``Adr`` has a real backing
     ``Artifact`` and is a perfectly resolvable TraceLink endpoint); it is
     because there is no *source* entity to link it from in the first
     place. See :meth:`_write_adr_draft`.

LLM access goes through the ``llm_adapter`` provider registry. The default
provider is ``mock`` (credential-free, deterministic) so the flows and their
tests run without network access. Prompt text is sourced from the tenant's
:class:`~persistence.models.PromptTemplate` row, falling back to the module-level
``PROMPT_TEMPLATE_DEFAULTS`` when no row exists yet.

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    L2_ApplicationServiceSystem_Architecture.md (ADR-AS-01, single entry point)
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from django.core.cache import cache

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS,
    ArchitectureElement,
    PromptTemplate,
    Requirement,
    StakeholderNeed,
    TraceLink,
    Workspace,
)
from traceability.types import LinkType

from application.base import NotFoundError, ServiceBase, ValidationError
from application.glossary_service import GlossaryService
from application.models import Risk
from llm_adapter.providers import truncate_prompt_content
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

# Prefix stamped onto completions that were served by the mock provider after a
# real provider failed (REQ-078). Callers can test for it to warn the user that
# the content is a deterministic placeholder, not a genuine LLM answer.
MOCK_FALLBACK_MARKER = "[MOCK FALLBACK] "

# SysEng 2.0 N5 (test.derive_from_requirement) prompt. Hardcoded rather than a
# PromptTemplate slot: the flow is a standard feature (no rigor-preset gate),
# and — mirroring the N1 precedent in architecture_decompose_service.py — a
# new per-tenant editable slot would require a model field + migration for no
# behavioural benefit while the default provider is the purpose-keyed mock.
TESTCASE_DERIVE_PROMPT_TEMPLATE = (
    "You are a test engineer. Derive one test case that verifies the "
    "following requirement.\n\n"
    "Requirement title: {req_title}\n"
    "Requirement description: {req_description}\n\n"
    "Respond with a single JSON object (no prose, no markdown fences) with "
    'this exact shape: {"title": "<test case title>", "description": '
    '"<short description>", "steps": [{"step": "<action>", '
    '"expected_result": "<expected outcome>"}, ...]}. '
    "Provide at least 2 and at most 6 steps."
)

# Phase 3 (Architecture -> Risk derive pair) prompt. Hardcoded rather than a
# PromptTemplate slot for the same reason as TESTCASE_DERIVE_PROMPT_TEMPLATE
# above: this is a new slot not among the 3 existing tenant-editable slots,
# and adding per-tenant CRUD for it is Phase 4's job (PromptTemplate model +
# migration), not this flow's.
ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE = (
    "You are a systems engineer performing risk identification. Given the "
    "following architecture element, propose realistic risks that could "
    "threaten its successful delivery or operation.\n\n"
    "Architecture element title: {ae_title}\n"
    "Architecture element description: {ae_description}\n\n"
    "Respond with a JSON array (no prose, no markdown fences) of objects "
    'with this exact shape: {"title": "<risk title>", "description": '
    '"<short description>", "probability": "<low|medium|high>", '
    '"impact": "<low|medium|high>", "category": '
    '"<technical|operational|organizational|business>"}. '
    "'probability' and 'impact' MUST be exactly one of 'low', 'medium' or "
    "'high' — no other values are valid."
)

# Phase 3 (Workspace -> Glossary derive pair, Task 4) prompt. Hardcoded for
# the same reason as ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE above.
WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE = (
    "You are a systems engineer extracting a project glossary. Given the "
    "following requirement and architecture element titles/descriptions from "
    "a workspace, extract domain-specific terms and their definitions.\n\n"
    "Workspace content:\n{workspace_text}\n\n"
    "Respond with a JSON array (no prose, no markdown fences) of objects "
    'with this exact shape: {"term": "<term>", "definition": '
    '"<short definition>", "synonyms": ["<synonym>", ...], "abbreviation": '
    '"<abbreviation or empty string>"}. Only extract terms that are actually '
    "domain-specific (not generic English words)."
)

# Phase 3 (Decision -> ADR derive pair, Task 5) prompt. Hardcoded for the same
# reason as ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE above.
DECISION_TO_ADR_PROMPT_TEMPLATE = (
    "You are a systems engineer documenting an architecture decision. Given "
    "the following free-text description of a decision, structure it into "
    "an Architecture Decision Record.\n\n"
    "Decision description:\n{decision_description}\n\n"
    "Respond with a single JSON object (no prose, no markdown fences) with "
    'this exact shape: {"title": "<short ADR title>", "description": '
    '"<what was decided>", "context": "<the problem/forces that led to this '
    'decision>", "consequences": "<what becomes easier or harder as a '
    'result>"}.'
)

# ---------------------------------------------------------------------------
# LLM derivation response caching (REQ-105, DEEP_SYSTEM_ANALYSIS.md F5.1)
#
# Identical derivation requests (same provider, capability, source artifact and
# rendered prompt) previously re-invoked the LLM on every call. Results are now
# cached in the shared Django cache backend (Redis, REQ-033) keyed by a prompt
# hash. Only genuine provider answers are cached — mock-fallback and error
# results are always recomputed.
# ---------------------------------------------------------------------------

# Cache time-to-live for a derivation result, in seconds (1 hour).
DERIVATION_CACHE_TTL_SECONDS = 3600

# Shared-cache key namespace for cached derivation results.
_DERIVATION_CACHE_PREFIX = "llm_derivation"

# Namespace for the per-artifact cache-generation counter used to invalidate
# every cached derivation of an artifact in O(1) (see _derivation_version).
_DERIVATION_VERSION_PREFIX = "llm_derivation_ver"


def _derivation_version(artifact_id: str) -> int:
    """Return the current cache-generation counter for *artifact_id*.

    The counter is folded into the cache key so bumping it (on artifact update)
    orphans every previously cached derivation for that artifact in O(1); the
    orphaned entries then expire naturally via their TTL. This pattern is used
    because the built-in ``RedisCache`` backend offers no pattern deletion.
    """
    version_key = f"{_DERIVATION_VERSION_PREFIX}:{artifact_id}"
    version = cache.get(version_key)
    if version is None:
        version = 1
        # No expiry: the counter must outlive the results it namespaces.
        cache.set(version_key, version, None)
    return int(version)


def _derivation_cache_key(
    provider: str, capability: str, artifact_id: str, prompt: str
) -> str:
    """Build the shared-cache key for a derivation result.

    Format: ``llm_derivation:{sha256(provider:capability:artifact_id:prompt_hash)}``
    with the artifact's cache-generation counter folded into the hashed material
    so invalidation can orphan stale entries.
    """
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    version = _derivation_version(artifact_id)
    material = f"{provider}:{capability}:{artifact_id}#v{version}:{prompt_hash}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{_DERIVATION_CACHE_PREFIX}:{digest}"


def invalidate_derivation_cache(artifact_id: UUID | str | None) -> None:
    """Invalidate every cached LLM derivation for *artifact_id*.

    Bumps the artifact's cache-generation counter so all previously cached
    entries become unreachable. Never raises: invalidation must not break the
    write that triggered it.

    Args:
        artifact_id: Source artifact primary key (UUID or string). ``None`` is
            a no-op.
    """
    if artifact_id is None:
        return
    version_key = f"{_DERIVATION_VERSION_PREFIX}:{artifact_id}"
    try:
        cache.incr(version_key)
    except ValueError:
        # Counter absent (nothing cached yet) — start past the default
        # generation so any concurrently written entry is superseded.
        cache.set(version_key, 2, None)
    except Exception:  # pragma: no cover - defensive; cache backend down
        logger.warning(
            "Failed to invalidate derivation cache for artifact %s",
            artifact_id,
            exc_info=True,
        )


class LlmResponseError(RuntimeError):
    """Raised when the LLM returns a response that cannot be parsed as JSON.

    Maps to HTTP 500 in the REST layer and to an INTERNAL_ERROR ToolResult in
    the MCP layer — the request itself was valid, but the provider misbehaved.
    """


class AiDerivationService(ServiceBase):
    """LLM-backed, draft-only derivation flows (REQ-L2-AI-001, REQ-L2-AI-002)."""

    # ------------------------------------------------------------------
    # Public flows
    # ------------------------------------------------------------------

    def derive_requirements_from_need(
        self,
        ctx: AuthContext,
        stakeholder_need_id: UUID | str,
        n: int = 3,
    ) -> Dict[str, Any]:
        """Flow 1: propose ``n`` system requirements for a stakeholder need.

        Args:
            ctx: Authenticated, tenant-scoped context.
            stakeholder_need_id: Source stakeholder need.
            n: Number of requirement drafts to request (clamped to >= 1).

        Returns:
            ``{"drafts": [{title, description, rationale, suggested_parent_id}]}``.

        Raises:
            NotFoundError: The stakeholder need does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)
        count = max(1, int(n))

        need = (
            StakeholderNeed.objects.select_related("artifact")
            .filter(id=stakeholder_need_id)
            .first()
        )
        if need is None:
            raise NotFoundError(f"StakeholderNeed {stakeholder_need_id} not found")

        template = self._get_slot(ctx, "need_to_sysreq")
        prompt = self._render(
            template,
            n=count,
            need_title=need.title,
            need_description=truncate_prompt_content(need.description or ""),
        )

        raw = self._complete(
            prompt,
            purpose="need_to_sysreq",
            artifact_id=need.artifact_id,
            context={"n": count},
        )
        items = self._parse_json_list(raw)

        drafts = [
            {
                "title": str(item.get("title", "")),
                "description": str(item.get("description", "")),
                "rationale": str(item.get("rationale", "")),
                "suggested_parent_id": str(need.id),
            }
            for item in items
            if isinstance(item, dict)
        ]
        return {"drafts": drafts}

    def suggest_architecture_for_requirement(
        self,
        ctx: AuthContext,
        requirement_id: UUID | str,
    ) -> Dict[str, Any]:
        """Flow 2: suggest architecture elements to satisfy a requirement.

        Only meaningful while the requirement is unassigned: if an
        ``allocated-to`` link already exists a :class:`ValidationError` is
        raised (mapped to HTTP 400).

        Args:
            ctx: Authenticated, tenant-scoped context.
            requirement_id: Requirement to find responsible elements for.

        Returns:
            ``{"suggested_arch_element_ids": [<uuid-str>, ...]}``.

        Raises:
            NotFoundError: The requirement does not exist for this tenant.
            ValidationError: The requirement is already allocated.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        req = self._get_requirement(requirement_id)

        if self._allocated_target_ids(req):
            raise ValidationError(
                "Requirement is already assigned to an architecture element."
            )

        workspace_id = req.artifact.workspace_id
        arch_elements = list(
            ArchitectureElement.objects.select_related("artifact").filter(
                artifact__workspace_id=workspace_id
            )
        )
        arch_payload = [
            {
                "id": str(ae.id),
                "name": ae.title,
                "description": truncate_prompt_content(ae.description or ""),
            }
            for ae in arch_elements
        ]
        available_ids = {entry["id"] for entry in arch_payload}

        template = self._get_slot(ctx, "sysreq_to_arch_assign")
        prompt = self._render(
            template,
            req_title=req.title,
            req_description=truncate_prompt_content(req.description or ""),
            arch_elements_json=json.dumps(arch_payload),
        )

        raw = self._complete(
            prompt,
            purpose="sysreq_to_arch_assign",
            artifact_id=req.artifact_id,
            context={"arch_element_ids": [entry["id"] for entry in arch_payload]},
        )
        suggested = self._parse_json_list(raw)

        # Keep only ids the LLM was actually offered (defensive against
        # hallucinated identifiers).
        result_ids = [
            str(item)
            for item in suggested
            if isinstance(item, (str, int)) and str(item) in available_ids
        ]
        return {"suggested_arch_element_ids": result_ids}

    def decompose_requirement_next_level(
        self,
        ctx: AuthContext,
        requirement_id: UUID | str,
    ) -> Dict[str, Any]:
        """Flow 3: propose next-level requirement drafts for a requirement.

        Requires at least one ``allocated-to`` architecture element; otherwise a
        :class:`ValidationError` is raised (mapped to HTTP 400).

        Args:
            ctx: Authenticated, tenant-scoped context.
            requirement_id: Parent requirement to decompose.

        Returns:
            ``{"drafts": [{title, description, rationale,
            suggested_arch_element_id}], "parent_requirement_id": <uuid-str>}``.

        Raises:
            NotFoundError: The requirement does not exist for this tenant.
            ValidationError: The requirement has no allocated architecture element.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        req = self._get_requirement(requirement_id)

        target_ids = self._allocated_target_ids(req)
        if not target_ids:
            raise ValidationError(
                "Requirement must be assigned to at least one architecture "
                "element before it can be decomposed."
            )

        arch_elements = list(
            ArchitectureElement.objects.filter(artifact_id__in=target_ids)
        )
        arch_payload = [
            {
                "id": str(ae.id),
                "name": ae.title,
                "description": truncate_prompt_content(ae.description or ""),
            }
            for ae in arch_elements
        ]

        template = self._get_slot(ctx, "sysreq_decompose_next_level")
        prompt = self._render(
            template,
            req_title=req.title,
            req_description=truncate_prompt_content(req.description or ""),
            arch_elements_json=json.dumps(arch_payload),
        )

        raw = self._complete(
            prompt,
            purpose="sysreq_decompose_next_level",
            artifact_id=req.artifact_id,
            context={"arch_element_ids": [entry["id"] for entry in arch_payload]},
        )
        items = self._parse_json_list(raw)

        drafts = [
            {
                "title": str(item.get("title", "")),
                "description": str(item.get("description", "")),
                "rationale": str(item.get("rationale", "")),
                "suggested_arch_element_id": (
                    str(item["suggested_arch_element_id"])
                    if item.get("suggested_arch_element_id") is not None
                    else None
                ),
            }
            for item in items
            if isinstance(item, dict)
        ]
        return {
            "drafts": drafts,
            "parent_requirement_id": str(req.id),
        }

    def derive_testcase_from_requirement(
        self,
        ctx: AuthContext,
        requirement_id: UUID | str,
    ) -> Dict[str, Any]:
        """Flow 4 (SysEng 2.0 N5): propose a TestCase draft for a requirement.

        Standard feature — unlike :meth:`decompose_requirement_next_level`
        this flow has no rigor-preset / RuleEngine gate and works on any
        requirement regardless of allocation state.

        Follows the same Draft/Accept contract as the other flows: nothing is
        persisted here. The caller (REST view / MCP tool) returns the draft to
        the client, which persists it — after user review — via the existing
        ``TestService.create_test_case`` path.

        Args:
            ctx: Authenticated, tenant-scoped context.
            requirement_id: Source requirement to derive a test case for.

        Returns:
            ``{"draft": {"title": str, "description": str, "steps":
            [{"step": str, "expected_result": str}, ...]}, "requirement_id":
            <uuid-str>}``.

        Raises:
            NotFoundError: The requirement does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        req = self._get_requirement(requirement_id)

        prompt = self._render(
            TESTCASE_DERIVE_PROMPT_TEMPLATE,
            req_title=req.title,
            req_description=truncate_prompt_content(req.description or ""),
        )

        raw = self._complete(
            prompt,
            purpose="test_derive_from_requirement",
            artifact_id=req.artifact_id,
            context={"req_title": req.title},
        )
        parsed = self._parse_json_object(raw)

        raw_steps = parsed.get("steps")
        steps = [
            {
                "step": str(step.get("step", "")),
                "expected_result": str(step.get("expected_result", "")),
            }
            for step in raw_steps
            if isinstance(step, dict)
        ] if isinstance(raw_steps, list) else []

        draft = {
            "title": str(parsed.get("title", "")),
            "description": str(parsed.get("description", "")),
            "steps": steps,
        }
        return {"draft": draft, "requirement_id": str(req.id)}

    def derive_risks_from_architecture(
        self,
        ctx: AuthContext,
        architecture_element_id: UUID | str,
    ) -> Dict[str, Any]:
        """Flow 5 (Phase 3): propose risk drafts for an architecture element.

        Standard feature — like :meth:`derive_testcase_from_requirement`, this
        flow has no rigor-preset / RuleEngine gate and works on any
        architecture element regardless of its position in the tree.

        Follows the same Draft/Accept contract as the other flows: nothing is
        persisted here. ``probability``/``impact`` are exactly the enum
        fields :meth:`application.risk_service.RiskService.create_risk`
        requires — the LLM is instructed to only emit valid enum values, but
        the parsed response is still defensively clamped to a valid value
        (falling back to ``"medium"``) rather than trusting the provider, so
        a misbehaving/hallucinating provider can never crash this flow or
        produce a draft ``create_risk`` would reject.

        Args:
            ctx: Authenticated, tenant-scoped context.
            architecture_element_id: Source architecture element to derive
                risk drafts for.

        Returns:
            ``{"drafts": [{title, description, probability, impact,
            category}], "architecture_element_id": <uuid-str>}``.

        Raises:
            NotFoundError: The architecture element does not exist for this
                tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        ae = self._get_architecture_element(architecture_element_id)

        prompt = self._render(
            ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE,
            ae_title=ae.title,
            ae_description=truncate_prompt_content(ae.description or ""),
        )

        raw = self._complete(
            prompt,
            purpose="derive_risks_from_architecture",
            artifact_id=ae.artifact_id,
            context={"ae_title": ae.title},
        )
        items = self._parse_json_list(raw)

        drafts = [
            {
                "title": str(item.get("title", "")),
                "description": str(item.get("description", "")),
                "probability": self._clamp_choice(
                    item.get("probability"), Risk.Probability.values, "medium"
                ),
                "impact": self._clamp_choice(
                    item.get("impact"), Risk.Impact.values, "medium"
                ),
                "category": self._clamp_choice(
                    item.get("category"), Risk.Category.values, "technical"
                ),
            }
            for item in items
            if isinstance(item, dict)
        ]
        return {"drafts": drafts, "architecture_element_id": str(ae.id)}

    def derive_glossary_from_workspace(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
    ) -> Dict[str, Any]:
        """Flow 6 (Phase 3, Task 4): propose glossary term drafts for a workspace.

        Standard feature — like :meth:`derive_testcase_from_requirement` and
        :meth:`derive_risks_from_architecture`, this flow has no rigor-preset
        / RuleEngine gate. Unlike those two, the source is not a single
        artifact but every Requirement and ArchitectureElement currently in
        the workspace: their titles and descriptions are collected into one
        block of text and handed to the LLM to extract domain terms from.
        This intentionally reuses only a lightweight, direct query — not the
        full context-assembly machinery of the N1 architecture-decompose
        copilot, which this flow does not need.

        Follows the same Draft/Accept contract as the other flows: nothing is
        persisted here.

        Args:
            ctx: Authenticated, tenant-scoped context.
            workspace_id: Workspace to scan for candidate terms.

        Returns:
            ``{"drafts": [{term, definition, synonyms, abbreviation}],
            "workspace_id": <uuid-str>}``.

        Raises:
            NotFoundError: The workspace does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        workspace = self._get_workspace(workspace_id)

        fragments: List[str] = []
        requirements = Requirement.objects.filter(
            artifact__workspace_id=workspace.id
        )
        for req in requirements:
            fragments.append(
                f"Requirement: {req.title}\n"
                f"{truncate_prompt_content(req.description or '')}"
            )
        arch_elements = ArchitectureElement.objects.filter(
            artifact__workspace_id=workspace.id
        )
        for ae in arch_elements:
            fragments.append(
                f"Architecture element: {ae.title}\n"
                f"{truncate_prompt_content(ae.description or '')}"
            )
        workspace_text = "\n\n".join(fragments) or (
            "(workspace has no requirements or architecture elements yet)"
        )

        prompt = self._render(
            WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE, workspace_text=workspace_text
        )

        raw = self._complete(
            prompt,
            purpose="derive_glossary_from_workspace",
            artifact_id=str(workspace.id),
            context={"workspace_id": str(workspace.id)},
        )
        items = self._parse_json_list(raw)

        drafts = [
            {
                "term": str(item.get("term", "")),
                "definition": str(item.get("definition", "")),
                "synonyms": (
                    [str(s) for s in item["synonyms"]]
                    if isinstance(item.get("synonyms"), list)
                    else []
                ),
                "abbreviation": str(item.get("abbreviation", "")),
            }
            for item in items
            if isinstance(item, dict)
        ]
        return {"drafts": drafts, "workspace_id": str(workspace.id)}

    def derive_adr_from_decision(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        decision_description: str,
    ) -> Dict[str, Any]:
        """Flow 7 (Phase 3, Task 5): structure a free-text decision into an ADR draft.

        Standard feature — like :meth:`derive_testcase_from_requirement`,
        :meth:`derive_risks_from_architecture` and
        :meth:`derive_glossary_from_workspace`, this flow has no rigor-preset
        / RuleEngine gate. Unlike all of those, the source is not an existing
        artifact at all: ``decision_description`` is raw free text supplied by
        the caller, so there is no id to fetch and no ``NotFoundError`` path
        for the source (only ``workspace_id`` — the target workspace the ADR
        will be created in on write — is validated to exist).

        Follows the same Draft/Accept contract as the other flows: nothing is
        persisted here.

        Args:
            ctx: Authenticated, tenant-scoped context.
            workspace_id: Workspace the resulting ADR draft would belong to
                (validated so ``mode="preview"`` fails fast on a bad
                workspace id rather than only on the later write call).
            decision_description: Free-text description of the decision to
                structure.

        Returns:
            ``{"draft": {"title": str, "description": str, "context": str,
            "consequences": str}, "workspace_id": <uuid-str>}``.

        Raises:
            NotFoundError: The workspace does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        workspace = self._get_workspace(workspace_id)

        prompt = self._render(
            DECISION_TO_ADR_PROMPT_TEMPLATE,
            decision_description=truncate_prompt_content(decision_description or ""),
        )

        raw = self._complete(
            prompt,
            purpose="derive_adr_from_decision",
            artifact_id=str(workspace.id),
            context={"decision_description": decision_description},
        )
        parsed = self._parse_json_object(raw)

        draft = {
            "title": str(parsed.get("title", "")),
            "description": str(parsed.get("description", "")),
            "context": str(parsed.get("context", "")),
            "consequences": str(parsed.get("consequences", "")),
        }
        return {"draft": draft, "workspace_id": str(workspace.id)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_requirement(self, requirement_id: UUID | str) -> Requirement:
        """Return a tenant-scoped Requirement or raise NotFoundError."""
        req = (
            Requirement.objects.select_related("artifact")
            .filter(id=requirement_id)
            .first()
        )
        if req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        return req

    def _get_stakeholder_need(
        self, stakeholder_need_id: UUID | str
    ) -> StakeholderNeed:
        """Return a tenant-scoped StakeholderNeed or raise NotFoundError.

        Mirrors :meth:`_get_requirement`; used by the write-mode path (Phase
        3) to resolve the source need's workspace before persisting a
        derived Requirement.
        """
        need = (
            StakeholderNeed.objects.select_related("artifact")
            .filter(id=stakeholder_need_id)
            .first()
        )
        if need is None:
            raise NotFoundError(f"StakeholderNeed {stakeholder_need_id} not found")
        return need

    def _get_architecture_element(
        self, architecture_element_id: UUID | str
    ) -> ArchitectureElement:
        """Return a tenant-scoped ArchitectureElement or raise NotFoundError.

        Mirrors :meth:`_get_requirement` / :meth:`_get_stakeholder_need`; used
        by :meth:`derive_risks_from_architecture` (Phase 3).
        """
        ae = (
            ArchitectureElement.objects.select_related("artifact")
            .filter(id=architecture_element_id)
            .first()
        )
        if ae is None:
            raise NotFoundError(
                f"ArchitectureElement {architecture_element_id} not found"
            )
        return ae

    def _get_workspace(self, workspace_id: UUID | str) -> Workspace:
        """Return a tenant-scoped Workspace or raise NotFoundError.

        Mirrors :meth:`_get_requirement` / :meth:`_get_architecture_element`;
        used by :meth:`derive_glossary_from_workspace` (Phase 3, Task 4).
        """
        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace

    @staticmethod
    def _clamp_choice(value: Any, valid_values: List[str], default: str) -> str:
        """Return *value* if it is one of *valid_values*, else *default*.

        Defensive guard against a hallucinating/misbehaving LLM response
        (:meth:`derive_risks_from_architecture`): ``RiskService.create_risk``
        requires ``probability``/``impact``/``category`` to be exact enum
        values, so an invalid or missing value must never propagate as far
        as that call.
        """
        return value if value in valid_values else default

    @staticmethod
    def _allocated_target_ids(req: Requirement) -> List[UUID]:
        """Return the artifact ids this requirement is ``allocated-to``."""
        links = TraceLink.objects.filter(
            source_id=req.artifact_id,
            link_type=LinkType.ALLOCATED_TO.value,
        ).values_list("target_id", flat=True)
        return list(links)

    # ------------------------------------------------------------------
    # Write-mode helpers (Phase 3, REQ-L2-AI-003) — shared by the three
    # AiDerivationToolGroup tools when invoked with mode="write". Every
    # write flow still starts from the same draft the mode="preview" path
    # returns; only the persistence step is new here.
    # ------------------------------------------------------------------

    @atomic_transaction
    def _write_derived_entity(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        create_fn: Callable[[], Any],
        source_entity_id: UUID | str,
        source_item_type: str,
        link_type: str,
        policy: str = "manual",
        new_entity_is_link_source: bool = False,
    ) -> Dict[str, Any]:
        """Persist one derived draft entity and link it back to its source.

        Shared by all four derive tools' write path: ``create_fn`` is a
        zero-arg closure the caller builds (e.g. a bound
        ``RequirementService().create_requirement(...)`` call) that persists
        exactly one derived entity. This helper then:

          1. Calls ``create_fn()`` to create the entity.
          2. Creates a ``link_type`` TraceLink between *source_entity_id* and
             the new entity (REQ-L2-AS-010, via TraceLinkService). By default
             *source_entity_id* is the link source and the new entity is the
             target (e.g. ``derives-from``: ChildReq --derives-from--> ParentReq
             uses ``source_entity_id=parent``, ``created=child`` — so the link
             is created with source=source_entity_id, target=created, which
             reads backwards from the SE convention documented in
             ``TraceLinkService.propagate_suspect_status`` but matches how the
             existing derive tools built their links pre-Phase-3). When
             ``new_entity_is_link_source=True`` the direction is reversed
             (source=created, target=source_entity_id) — required for link
             types whose SE endpoint semantics fix the *new* entity as the
             source, e.g. ``verifies``: TestCase --verifies--> Requirement
             (``traceability.types.SE_LINK_SEMANTICS``).
          3. When ``policy == "auto"``, walks the new entity forward through
             its real workflow transitions via :meth:`_auto_approve`.

        The whole body runs inside a single ``transaction.atomic()`` block
        (via :func:`~persistence.transactions.atomic_transaction`): if trace
        link creation fails (e.g. an invalid link type or an SE-mode
        semantics violation), the just-created entity is rolled back too —
        no orphaned, un-linked entity is left behind (REQ-L3-PL003-002).

        Args:
            ctx: Authenticated, tenant-scoped context (also the actor
                recorded on the trace link and any auto-transitions).
            workspace_id: Workspace the derived entity belongs to.
            item_type: Workflow ``item_type`` of the newly created entity
                (e.g. ``"Requirement"``) — used only for ``policy="auto"``.
            create_fn: Zero-arg closure that persists and returns the new
                entity (must expose ``.id`` and ``.artifact_id`` attributes).
            source_entity_id: Id of the entity the new one was derived from.
            source_item_type: Workflow ``item_type`` of *source_entity_id*
                (kept for caller-side documentation/audit — TraceLinkService
                resolves the concrete artifact type on its own).
            link_type: One of ``traceability.types.LinkType`` (e.g.
                ``"derives-from"``).
            policy: ``"manual"`` (default, leaves the entity in its initial
                "draft" state) or ``"auto"`` (best-effort auto-approval).
            new_entity_is_link_source: ``False`` (default) creates the link as
                source=*source_entity_id*, target=new entity. ``True`` reverses
                it — see point 2 above. Needed because
                ``TraceLinkService._resolve_artifact_id`` does not know how to
                resolve a bare ``TestCase`` id, so the new entity's own
                ``artifact_id`` is always used instead of its primary key when
                building the link (see below).

        Returns:
            ``{"id": <uuid-str>, "status": <final status string>,
            "trace_link_id": <uuid-str>}``.
        """
        self._set_tenant_context(ctx)

        created = create_fn()
        # TraceLinkService._resolve_artifact_id only resolves bare
        # Artifact/Requirement/ArchitectureElement/Adr ids, not e.g. TestCase
        # ids — use the artifact backing every derived entity directly so
        # this helper works for any item_type.
        created_ref = created.artifact_id

        from application.trace_link_service import TraceLinkService

        if new_entity_is_link_source:
            link_source, link_target = created_ref, source_entity_id
        else:
            link_source, link_target = source_entity_id, created_ref

        link = TraceLinkService().create_trace_link(
            source_id=link_source,
            target_id=link_target,
            link_type=link_type,
            ctx=ctx,
        )

        status = "draft"
        if policy == "auto":
            status = self._auto_approve(item_type, created.id, workspace_id, ctx)

        return {
            "id": str(created.id),
            "status": status,
            "trace_link_id": str(link.id),
        }

    @atomic_transaction
    def _write_glossary_term_draft(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        term: str,
        definition: str,
        synonyms: List[str],
        abbreviation: str,
        policy: str = "manual",
    ) -> Dict[str, Any]:
        """Persist one derived GlossaryTerm draft (Phase 3, Task 4).

        Deliberately NOT built on :meth:`_write_derived_entity`, unlike every
        other write-mode helper in this class. Two things that helper relies
        on do not hold for this pair:

          1. ``_write_derived_entity`` links the new entity back to its
             source via ``TraceLinkService.create_trace_link``, which resolves
             its ``source_id``/``target_id`` through
             ``_resolve_artifact_id`` — that only accepts a bare
             Artifact/Requirement/ArchitectureElement/Adr id, never a
             Workspace id (verified by reading the method directly). So no
             trace link back to the source Workspace can ever be created for
             this flow. Decision -> ADR (:meth:`_write_adr_draft`) also
             creates no trace link, but for a different reason: there the
             *target* type (``Adr``) is a perfectly resolvable TraceLink
             endpoint — there simply is no source entity id at all, since
             the flow's input is raw free text, not an existing artifact.
          2. ``_write_derived_entity`` also assumes the created entity exposes
             ``.artifact_id`` (used as the trace-link endpoint even when no
             link involves it) — ``GlossaryTerm`` has no backing Artifact at
             all (unlike Requirement/Risk/ArchitectureElement), so that
             assumption does not hold either.

        ``policy="auto"`` still reuses :meth:`_auto_approve`: unlike the
        trace-link machinery this flow genuinely doesn't need,
        ``GlossaryTerm`` *does* have its own real design/review/approve/retire
        workflow (``glossary_term_default``, see
        ``workflow/management/commands/provision_workflow_definitions.py``),
        so best-effort auto-advancement is still meaningful here.

        ``GlossaryService.create`` already raises :class:`ValidationError`
        for a colliding ``(workspace, term)`` pair (REQ-L1-044's
        ``unique_together`` constraint) via its own pre-check — the caller
        (``AiDerivationToolGroup``) catches that the same way it already
        catches ``ValidationError`` from every other write-mode helper, so no
        extra handling is needed here.

        Returns:
            ``{"id": <uuid-str>, "term": str, "status": <final status string>}``.
        """
        self._set_tenant_context(ctx)

        created = GlossaryService().create(
            ctx=ctx,
            workspace_id=workspace_id,
            term=term,
            definition=definition,
            synonyms=synonyms,
            abbreviation=abbreviation,
        )

        status = "draft"
        if policy == "auto":
            status = self._auto_approve(
                "GlossaryTerm", created.id, workspace_id, ctx
            )

        return {"id": str(created.id), "term": created.term, "status": status}

    @atomic_transaction
    def _write_adr_draft(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        title: str,
        description: str,
        context: str,
        consequences: str,
        policy: str = "manual",
    ) -> Dict[str, Any]:
        """Persist one derived Adr draft (Phase 3, Task 5).

        Deliberately NOT built on :meth:`_write_derived_entity`, like
        :meth:`_write_glossary_term_draft` — but for a different reason.
        ``Adr`` *does* have a backing ``Artifact`` (unlike ``GlossaryTerm``)
        and its own primary key is directly resolvable by
        ``TraceLinkService._resolve_artifact_id`` (it is explicitly listed
        there alongside Artifact/Requirement/ArchitectureElement, see
        :meth:`_write_derived_entity`'s docstring) — so, unlike the Workspace
        -> Glossary pair, nothing about *this* target type rules out a trace
        link.

        The reason no trace link is created here is entirely on the *source*
        side: :meth:`derive_adr_from_decision`'s input, ``decision_description``,
        is raw free text supplied by the caller — there is no existing
        artifact id to link from at all, resolvable or not. Every other
        write-mode helper in this class is handed a real ``source_entity_id``;
        this is the one flow in this phase whose entire premise (a Decision is
        not a persisted entity) rules that out structurally, not because of a
        resolution limitation.

        ``policy="auto"`` still reuses :meth:`_auto_approve`: ``Adr`` has its
        own real design/review/approve/retire workflow
        (``adr_default``, see
        ``workflow/management/commands/provision_workflow_definitions.py``),
        so best-effort auto-advancement is meaningful here exactly as it is
        for the other write-mode helpers.

        Args:
            ctx: Authenticated, tenant-scoped context.
            workspace_id: Workspace the new ADR belongs to.
            title: ADR title (``AdrService.create_adr`` validates length).
            description: ADR description.
            context: ADR context section.
            consequences: ADR consequences section.
            policy: ``"manual"`` (default) or ``"auto"``.

        Returns:
            ``{"id": <uuid-str>, "status": <final state string>}`` — no
            ``trace_link_id`` key (see above).

        Raises:
            NotFoundError: The workspace (or tenant) does not exist.
            ValidationError: ``title``/``description`` fail
                ``AdrService.create_adr``'s own validation.
        """
        self._set_tenant_context(ctx)

        from application.adr_service import AdrService

        created = AdrService().create_adr(
            workspace_id=workspace_id,
            title=title,
            description=description,
            ctx=ctx,
            context=context,
            consequences=consequences,
        )

        status = "draft"
        if policy == "auto":
            status = self._auto_approve("Adr", created.id, workspace_id, ctx)

        return {"id": str(created.id), "status": status}

    def _auto_approve(
        self,
        item_type: str,
        item_id: UUID | str,
        workspace_id: UUID | str,
        ctx: AuthContext,
    ) -> str:
        """Best-effort: walk *item_id* forward through its real transitions.

        Takes one hop at a time (via ``workflow.services.get_available_transitions``
        / ``transition``), always preferring the first available transition
        whose target state is not flagged ``is_outdated_equivalent`` in the
        workflow definition's ``state_meta`` (Phase 0) — an "auto-approve"
        policy must never auto-reject/auto-deprecate the entity it just
        created. Stops after 5 hops (defends against a pathological cyclic
        definition) or as soon as no non-terminal transition remains.

        Never raises: a validation failure (e.g. the caller's roles do not
        allow the next transition, or ``change_reason`` requirements are not
        met) simply stops the walk at whatever state was last reached — the
        entity stays a valid, persisted draft either way.

        Returns:
            The final workflow state name reached (``"draft"`` if no
            transition could be taken at all).
        """
        from workflow.definition_store import get_state_meta
        from workflow.models import WorkflowEngineDefinition
        from workflow.services import get_available_transitions, transition

        current_state = "draft"
        try:
            for _ in range(5):
                available = get_available_transitions(
                    item_id=item_id, item_type=item_type, workspace_id=workspace_id
                )
                current_state = available.current_state or current_state
                if not available.transitions:
                    break

                definition = WorkflowEngineDefinition.objects.filter(
                    workspace_id=workspace_id, item_type=item_type
                ).first()
                workflow_json = definition.workflow_json if definition else {}

                next_transition = next(
                    (
                        t
                        for t in available.transitions
                        if not get_state_meta(workflow_json, t.to_state).get(
                            "is_outdated_equivalent", False
                        )
                    ),
                    None,
                )
                if next_transition is None:
                    break

                result = transition(
                    item_id=item_id,
                    target_state=next_transition.to_state,
                    change_reason=f"auto-approved via AI-Derivation ({item_type})",
                    ctx=ctx,
                    item_type=item_type,
                    workspace_id=workspace_id,
                )
                current_state = result.new_state
        except Exception:  # noqa: BLE001 — auto-approve must never break a write
            logger.warning(
                "Auto-approve stopped for %s %s at state %s",
                item_type,
                item_id,
                current_state,
                exc_info=True,
            )
        return current_state

    @staticmethod
    def _get_slot(ctx: AuthContext, slot: str) -> str:
        """Return the tenant's prompt content for *slot* (or the factory default).

        The default manager is already tenant-scoped by the active
        TenantContext, so a plain ``.filter().first()`` is sufficient.
        """
        row = PromptTemplate.objects.filter(tenant_id=ctx.tenant_id).first()
        if row is not None:
            return row.get_slot(slot)
        return PROMPT_TEMPLATE_DEFAULTS[slot]

    @staticmethod
    def _render(template: str, **values: Any) -> str:
        """Substitute ``{name}`` placeholders without touching other braces.

        A literal ``str.format`` call would choke on JSON braces embedded in a
        user-customised prompt, so placeholders are replaced individually.
        """
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        return rendered

    def _complete(
        self,
        prompt: str,
        *,
        purpose: str,
        artifact_id: UUID | str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Run the configured provider's free-form completion (cached).

        Falls back to the credential-free mock provider when no provider is
        configured, so the flows degrade to deterministic output instead of
        failing hard (REQ-L2-AI-002; default provider is ``mock``).

        Genuine provider answers are cached in the shared cache backend keyed by
        provider, *purpose* (capability), *artifact_id* and a prompt hash
        (REQ-105). Mock-fallback results are never cached — they are degraded
        placeholders that must be recomputed once a real provider is available.
        """
        from django.conf import settings

        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )

        provider_name = getattr(settings, "LLM_PROVIDER", "unknown")
        cache_key = _derivation_cache_key(
            provider_name, purpose, str(artifact_id), prompt
        )

        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(
                "LLM derivation cache hit (purpose=%s, artifact=%s)",
                purpose,
                artifact_id,
            )
            return cached

        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            # Silent degradation hides that the caller is looking at mock output
            # instead of a real LLM answer (REQ-078). Emit a WARNING and tag the
            # response so downstream code / the UI can flag it to the user.
            logger.warning(
                "LLM provider %s failed, falling back to mock. Error: %s",
                provider_name,
                error,
            )
            result = MockLlmProvider().complete(
                prompt, purpose=purpose, context=context
            )
            # Fallback output is intentionally not cached (REQ-105).
            return f"{MOCK_FALLBACK_MARKER}{result}"

        result = provider.complete(prompt, purpose=purpose, context=context)
        # Never cache a fallback-marked (degraded) response (REQ-105).
        if not result.startswith(MOCK_FALLBACK_MARKER):
            cache.set(cache_key, result, DERIVATION_CACHE_TTL_SECONDS)
        return result

    @staticmethod
    def _parse_json_list(raw: str) -> List[Any]:
        """Parse *raw* into a JSON list, tolerating Markdown code fences.

        Raises:
            LlmResponseError: When *raw* is not valid JSON or not a list.
        """
        text = raw.strip()
        # Strip the mock-fallback marker (REQ-078) so a degraded response still
        # parses; the marker is only a user-facing signal, not part of the JSON.
        if text.startswith(MOCK_FALLBACK_MARKER):
            text = text[len(MOCK_FALLBACK_MARKER):].strip()
        if text.startswith("```"):
            # Strip a leading ```json / ``` fence and the trailing ```.
            text = text.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LlmResponseError(
                "The LLM response was not valid JSON."
            ) from exc
        if not isinstance(parsed, list):
            raise LlmResponseError(
                "The LLM response was not a JSON array as expected."
            )
        return parsed

    @staticmethod
    def _parse_json_object(raw: str) -> Dict[str, Any]:
        """Parse *raw* into a JSON object, tolerating Markdown code fences.

        Sibling of :meth:`_parse_json_list` for flows whose LLM response is a
        single JSON object rather than an array (SysEng 2.0 N5).

        Raises:
            LlmResponseError: When *raw* is not valid JSON or not an object.
        """
        text = raw.strip()
        if text.startswith(MOCK_FALLBACK_MARKER):
            text = text[len(MOCK_FALLBACK_MARKER):].strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LlmResponseError(
                "The LLM response was not valid JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise LlmResponseError(
                "The LLM response was not a JSON object as expected."
            )
        return parsed


__all__ = [
    "AiDerivationService",
    "LlmResponseError",
    "MOCK_FALLBACK_MARKER",
    "DERIVATION_CACHE_TTL_SECONDS",
    "TESTCASE_DERIVE_PROMPT_TEMPLATE",
    "WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE",
    "DECISION_TO_ADR_PROMPT_TEMPLATE",
    "invalidate_derivation_cache",
]
