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
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from django.core.cache import cache

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS as _CORE_PROMPT_TEMPLATE_DEFAULTS,
    ArchitectureElement,
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

# Human-readable language names for the explicit output-language directive
# appended to every content-generating derive prompt (issue #795: a QA
# session against a `language="de"` workspace observed
# ``derive_requirements_from_need`` answer in Chinese and
# ``decompose_requirement_next_level`` answer in English, in the same
# session with the same provider -- neither prompt ever mentioned a target
# language at all). Keyed by ``Workspace.language``'s ISO 639-1 code; any
# code not listed here -- including an empty/unset value -- falls back to
# "English", matching ``Workspace.language``'s own factory default (``"en"``).
LANGUAGE_INSTRUCTION_NAMES: Dict[str, str] = {
    "de": "German",
    "en": "English",
}

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

# Requirement Bundle Export, Plan 2 Task 1 (application.bundle_compression_service
# .PROMPT_TEMPLATE_NAME) prompt. Hardcoded for the same reason as
# ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE above. Registered here (rather than in
# bundle_compression_service.py itself) because PROMPT_TEMPLATE_DEFAULTS is
# this module's single canonical registry (see the module-level comment
# above PROMPT_TEMPLATE_DEFAULTS) -- BundleCompressionService only reads it
# via AiDerivationService._get_template_content, it never owns a copy.
BUNDLE_COMPRESSION_PROMPT_TEMPLATE = """\
You are compressing a structured export of software requirements for \
consumption by another AI system. Your ONLY job is token-efficient \
compression -- you must NOT summarize away, omit, reinterpret, or add any \
factual content. Every requirement's title, status, and core content must \
remain fully and accurately represented; you may remove purely \
presentational Markdown formatting (redundant headers, decorative \
separators) and compress verbose phrasing into denser prose, but the set \
of facts a reader could extract must be identical before and after \
compression. If you are not certain a piece of content is purely \
presentational, keep it. Do not add any commentary, headers, or content \
that was not present in the source.

Source bundle (Markdown):
{bundle_markdown}

Return only the compressed bundle content, nothing else.
"""

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

# Interview Management Engine (Task 6, spec §6 step 2) prompt. Hardcoded for
# the same reason as ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE above. Registered
# here (rather than in interview_service.py itself) for the same reason
# BUNDLE_COMPRESSION_PROMPT_TEMPLATE is registered here rather than in
# bundle_compression_service.py -- this module's PROMPT_TEMPLATE_DEFAULTS is
# the single canonical registry; InterviewService only reads it via
# AiDerivationService._get_template_content, it never owns a copy.
INTERVIEW_GROUNDING_RANK_PROMPT_TEMPLATE = """\
You are ranking candidate existing artifacts for relevance to a requirement \
currently being captured in an interview. You are given the interview's \
answers so far and a list of candidate artifacts that already passed a \
structural (title-substring) pre-filter. Score each candidate's relevance \
to the interview on a scale from 0.0 (unrelated) to 1.0 (certainly the same \
artifact, or a direct duplicate/near-duplicate of what is being captured).

Interview answers so far:
{answers_text}

Candidate artifacts (JSON):
{candidates_json}

Respond with a JSON array (no prose, no markdown fences) of objects with \
this exact shape: {"artifact_id": "<artifact_id from the candidate list, \
verbatim>", "score": <float between 0.0 and 1.0>}. Include exactly one \
entry per candidate, in any order. Do not invent artifact_ids that are not \
in the candidate list.
"""

# Interview-Management Web Widget (Task 2, spec §5) prompt -- server-side
# conversational turn generation for the web widget, which (unlike Claude
# Code/Opencode/Antigravity/Hermes) has no AI agent of its own to drive the
# interview dialogue. Registered here for the same reason
# INTERVIEW_GROUNDING_RANK_PROMPT_TEMPLATE is: this module's
# PROMPT_TEMPLATE_DEFAULTS is the single canonical registry;
# InterviewService only reads it via AiDerivationService._get_template_content,
# it never owns a copy. Not fail-open (spec §5) -- InterviewService.
# generate_chat_turn() raises ValidationError up front when no provider is
# configured, rather than calling this template against the mock.
INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE = """\
You are conducting a structured interview to help create or update a \
{artifact_type} in a requirements management system. Extract any field \
values the user's latest message clearly provides, and propose the next \
thing to say.

Do NOT guess. If a message is ambiguous or you are not confident about a \
value, leave it out of extracted_fields and ask a clarifying question in \
your reply instead -- an incorrectly recorded answer is worse than asking \
again.

Conversation so far (JSON list of {"role": ..., "text": ..., "timestamp": ...}):
{transcript_json}

Current phase instructions:
{current_phase_fragment}

Fields still needed (JSON list of {"name": ..., "type": ..., "choices": ...}):
{missing_fields_json}

Possibly related existing artifacts (JSON):
{grounding_snapshot_json}

Relevant memory from earlier sessions (may be empty):
{memory_context}

Latest user message:
{user_message}

Respond with a single JSON object (no prose, no markdown fences) with \
this exact shape: {"extracted_fields": {"<field_name>": "<value>", ...}, \
"reply": "<what to say back to the user>"}. extracted_fields may be \
empty. Only include fields from the "Fields still needed" list.
"""

# Canonical slot registry covering all 7 names this module's derive flows use
# (Phase 4, REQ-L2-PT-001). Deliberately NOT the same object as
# ``persistence.models.PROMPT_TEMPLATE_DEFAULTS`` (imported above as
# ``_CORE_PROMPT_TEMPLATE_DEFAULTS``): that dict is intentionally kept at its
# original 3 entries because it is the REST-exposed subset consumed by
# ``settings_service.py`` (``/api/v1/prompt-templates/`` only ever reads/
# writes those 3 tenant-editable slots) — it is not "not yet migrated", Layer
# 0 persistence code simply has no reason to know about the 4 Phase-3 flows
# below. This module-local dict merges that base with the 4 Phase-3 hardcoded
# prompt constants above, giving one factory-default lookup table covering
# all 7 names. This is the SINGLE canonical registry for all 7 names:
# ``mcp_server/tools/prompt_template.py`` imports it from here (rather than
# building its own copy or reaching into the 3-entry persistence dict) so
# both read paths — this service's :meth:`_get_template_content` and the MCP
# ``prompt_template.get`` tool — agree on the same factory defaults.
PROMPT_TEMPLATE_DEFAULTS: Dict[str, str] = {
    **_CORE_PROMPT_TEMPLATE_DEFAULTS,
    "testcase_derive": TESTCASE_DERIVE_PROMPT_TEMPLATE,
    "architecture_to_risk": ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE,
    "workspace_to_glossary": WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE,
    "decision_to_adr": DECISION_TO_ADR_PROMPT_TEMPLATE,
    "bundle_compression": BUNDLE_COMPRESSION_PROMPT_TEMPLATE,
    "interview.grounding_rank": INTERVIEW_GROUNDING_RANK_PROMPT_TEMPLATE,
    "interview.chat_turn": INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE,
}

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


def _is_empty_completion(text: str) -> bool:
    """Return True when a completion carries no usable content (issue #311).

    Recognises the three content-free shapes a provider can answer with: an
    empty/blank string, an empty JSON array (``[]``) and an empty JSON object
    (``{}``) — the fallback-marker prefix and Markdown fences are stripped
    first, mirroring :meth:`AiDerivationService._parse_json_list`. Anything
    that is not valid JSON is *not* treated as empty: a prose answer is real
    content for the free-form purposes (``goal_aggregate``), and for the
    JSON-shaped flows it raises a visible parse error anyway.

    Used to keep such answers out of the derivation cache. Caching one turns a
    single "the model proposed nothing" into DERIVATION_CACHE_TTL_SECONDS of
    guaranteed-empty results for that artifact, served without ever calling the
    provider again — so a retry (the obvious user reaction to an empty result)
    cannot recover, which is what issue #311 reported as "silently returns 0
    drafts". Same reasoning as the existing mock-fallback rule (REQ-105):
    degraded output must be recomputed, not pinned.
    """
    stripped = text.strip()
    if stripped.startswith(MOCK_FALLBACK_MARKER):
        stripped = stripped[len(MOCK_FALLBACK_MARKER):].strip()
    if stripped.startswith("```"):
        stripped = stripped.replace("```json", "").replace("```", "").strip()
    if not stripped:
        return True
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return False
    return parsed in ([], {})


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
        n: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Flow 1: propose system requirements for a stakeholder need.

        Args:
            ctx: Authenticated, tenant-scoped context.
            stakeholder_need_id: Source stakeholder need.
            n: Explicit upper bound for this call, overriding the workspace's
                ``max_requirements_per_need`` config variable. ``None`` (the
                default) means "use the configured value" — spec §4 turned
                this from a hard-coded 3 into catalog configuration.

        Returns:
            ``{"drafts": [{title, description, rationale,
            suggested_parent_id}], "is_mock_fallback": <bool>}``.
            ``is_mock_fallback`` is True when the drafts are mock-provider
            placeholders rather than a real LLM's proposal (see
            :meth:`_complete_json_list`).

        Raises:
            NotFoundError: The stakeholder need does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)
        count = max(1, int(n)) if n is not None else None

        need = (
            StakeholderNeed.objects.select_related("artifact")
            .filter(id=stakeholder_need_id)
            .first()
        )
        if need is None:
            raise NotFoundError(f"StakeholderNeed {stakeholder_need_id} not found")

        # Resolve `max_requirements_per_need` exactly once (workspace/tenant/
        # factory chain, `count` as the top-precedence override) and reuse the
        # same resolved int both for the rendered prompt text and for the
        # mock-provider `context` below (code-review finding on this task:
        # forwarding the raw, possibly-`None`, `count` into `context`
        # independently of what the resolver put in the prompt let
        # MockLlmProvider fall back to its own hardcoded default of 3
        # whenever `n` was omitted, disagreeing with whatever bound the
        # prompt text actually advertised). Mirrors
        # ArchitectureDecomposeService._complete_tree's established pattern
        # of resolving the config value up front and feeding the same value
        # into both the prompt and the audit/mock context.
        from application.prompt_resolver import resolve_config_values

        resolved_count = resolve_config_values(
            ctx,
            need.artifact.workspace_id,
            overrides={"max_requirements_per_need": count},
        ).get("max_requirements_per_need")

        prompt = self._resolve_and_render(
            ctx,
            "need_to_sysreq",
            need.artifact.workspace_id,
            config_overrides={"max_requirements_per_need": resolved_count},
            need_title=need.title,
            need_description=truncate_prompt_content(need.description or ""),
        )
        prompt += self._language_instruction(need.artifact.workspace_id)

        items, is_mock_fallback = self._complete_json_list(
            prompt,
            purpose="need_to_sysreq",
            artifact_id=need.artifact_id,
            context={"max_requirements_per_need": resolved_count},
        )

        drafts = [
            {
                "title": str(item.get("title", "")),
                "description": str(item.get("description", "")),
                "rationale": str(item.get("rationale", "")),
                "suggested_parent_id": str(need.id),
            }
            for item in items
        ]
        return {"drafts": drafts, "is_mock_fallback": is_mock_fallback}

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
            ``{"suggested_arch_element_ids": [<uuid-str>, ...],
            "is_mock_fallback": <bool>}``. ``is_mock_fallback`` is True when
            the suggestion came from the mock provider rather than the
            configured one (see :meth:`_complete_json_list`).

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

        template = self._get_template_content(
            ctx, "sysreq_to_arch_assign", workspace_id=workspace_id
        )
        prompt = self._render(
            template,
            req_title=req.title,
            req_description=truncate_prompt_content(req.description or ""),
            arch_elements_json=json.dumps(arch_payload),
        )

        # require_objects=False: this flow's array carries bare id strings, not
        # draft objects (see _complete_json_list).
        suggested, is_mock_fallback = self._complete_json_list(
            prompt,
            purpose="sysreq_to_arch_assign",
            artifact_id=req.artifact_id,
            context={"arch_element_ids": [entry["id"] for entry in arch_payload]},
            require_objects=False,
        )

        # Keep only ids the LLM was actually offered (defensive against
        # hallucinated identifiers).
        result_ids = [
            str(item)
            for item in suggested
            if isinstance(item, (str, int)) and str(item) in available_ids
        ]
        return {
            "suggested_arch_element_ids": result_ids,
            "is_mock_fallback": is_mock_fallback,
        }

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
            suggested_arch_element_id}], "parent_requirement_id": <uuid-str>,
            "is_mock_fallback": <bool>}``. ``is_mock_fallback`` is True when
            the drafts are mock-provider placeholders rather than a real
            LLM's proposal (see :meth:`_complete_json_list`).
            When ``drafts`` is empty an additional ``note`` key explains why
            (issue #311) — additive, present only in that case, mirroring how
            the write path only adds ``failed`` when something failed.

        Raises:
            NotFoundError: The requirement does not exist for this tenant.
            ValidationError: The requirement has no allocated architecture element.
            LlmResponseError: The provider returned non-JSON content, or an
                array from which no draft could be extracted (issue #311).
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

        template = self._get_template_content(
            ctx,
            "sysreq_decompose_next_level",
            workspace_id=req.artifact.workspace_id,
        )
        prompt = self._render(
            template,
            req_title=req.title,
            req_description=truncate_prompt_content(req.description or ""),
            arch_elements_json=json.dumps(arch_payload),
        )
        prompt += self._language_instruction(req.artifact.workspace_id)

        items, is_mock_fallback = self._complete_json_list(
            prompt,
            purpose="sysreq_decompose_next_level",
            artifact_id=req.artifact_id,
            context={"arch_element_ids": [entry["id"] for entry in arch_payload]},
        )

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
        ]
        result: Dict[str, Any] = {
            "drafts": drafts,
            "parent_requirement_id": str(req.id),
            "is_mock_fallback": is_mock_fallback,
        }
        if not drafts:
            result["note"] = self._empty_decomposition_note(req)
            logger.warning(
                "decompose_requirement_next_level produced no drafts "
                "(requirement=%s, provider response was an empty array). %s",
                req.id,
                result["note"],
            )
        return result

    @staticmethod
    def _empty_decomposition_note(req: Requirement) -> str:
        """Explain an empty ``drafts`` list to the caller (issue #311).

        Reaching this point means the provider answered with a well-formed but
        empty JSON array — no transport error, no parse error, nothing dropped
        (:meth:`_usable_entries` would have raised). The caller, typically an
        MCP agent, otherwise sees a bare ``drafts: []`` and cannot tell that
        apart from a broken pipeline, which is what issue #311 reported.

        The most common cause by far is a content-free prompt: a Requirement
        created through ``requirement.derive``/``requirement.create`` with a
        title only leaves the model nothing to decompose (the same empty
        description that issue #459 fixed on the ``derive`` path). That case is
        called out explicitly because it is actionable; otherwise the note just
        states what happened.
        """
        base = (
            "The LLM returned an empty list — no decomposition drafts were "
            "proposed. This is the provider's answer, not a failed call "
            "(a transport or parsing failure raises an error instead)."
        )
        if not (req.description or "").strip():
            return (
                f"{base} This requirement has no description, so the prompt "
                "contained only its title; add a description and retry."
            )
        return (
            f"{base} Retry, rephrase the requirement, or check the "
            "'sysreq_decompose_next_level' prompt template."
        )

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
            <uuid-str>, "is_mock_fallback": <bool>}``. ``is_mock_fallback``
            is True when the draft is a mock-provider placeholder rather than
            a real LLM's proposal (see :meth:`_complete_json_object`).

        Raises:
            NotFoundError: The requirement does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        req = self._get_requirement(requirement_id)

        template = self._get_template_content(
            ctx, "testcase_derive", workspace_id=req.artifact.workspace_id
        )
        prompt = self._render(
            template,
            req_title=req.title,
            req_description=truncate_prompt_content(req.description or ""),
        )
        prompt += self._language_instruction(req.artifact.workspace_id)

        parsed, is_mock_fallback = self._complete_json_object(
            prompt,
            purpose="test_derive_from_requirement",
            artifact_id=req.artifact_id,
            context={"req_title": req.title},
        )

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
        return {
            "draft": draft,
            "requirement_id": str(req.id),
            "is_mock_fallback": is_mock_fallback,
        }

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
            category}], "architecture_element_id": <uuid-str>,
            "is_mock_fallback": <bool>}``. ``is_mock_fallback`` is True when
            the drafts are mock-provider placeholders rather than a real
            LLM's proposal (see :meth:`_complete_json_list`).

        Raises:
            NotFoundError: The architecture element does not exist for this
                tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        ae = self._get_architecture_element(architecture_element_id)

        template = self._get_template_content(
            ctx, "architecture_to_risk", workspace_id=ae.artifact.workspace_id
        )
        prompt = self._render(
            template,
            ae_title=ae.title,
            ae_description=truncate_prompt_content(ae.description or ""),
        )
        prompt += self._language_instruction(ae.artifact.workspace_id)

        items, is_mock_fallback = self._complete_json_list(
            prompt,
            purpose="derive_risks_from_architecture",
            artifact_id=ae.artifact_id,
            context={"ae_title": ae.title},
        )

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
        ]
        return {
            "drafts": drafts,
            "architecture_element_id": str(ae.id),
            "is_mock_fallback": is_mock_fallback,
        }

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
            "workspace_id": <uuid-str>, "is_mock_fallback": <bool>}``.
            ``is_mock_fallback`` is True when the drafts are mock-provider
            placeholders rather than a real LLM's proposal (see
            :meth:`_complete_json_list`).

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

        template = self._get_template_content(
            ctx, "workspace_to_glossary", workspace_id=workspace.id
        )
        prompt = self._render(template, workspace_text=workspace_text)
        prompt += self._language_instruction(workspace.id)

        items, is_mock_fallback = self._complete_json_list(
            prompt,
            purpose="derive_glossary_from_workspace",
            artifact_id=str(workspace.id),
            context={"workspace_id": str(workspace.id)},
        )

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
        ]
        return {
            "drafts": drafts,
            "workspace_id": str(workspace.id),
            "is_mock_fallback": is_mock_fallback,
        }

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
            "consequences": str}, "workspace_id": <uuid-str>,
            "is_mock_fallback": <bool>}``. ``is_mock_fallback`` is True when
            the draft is a mock-provider placeholder rather than a real LLM's
            proposal (see :meth:`_complete_json_object`).

        Raises:
            NotFoundError: The workspace does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        workspace = self._get_workspace(workspace_id)

        template = self._get_template_content(
            ctx, "decision_to_adr", workspace_id=workspace.id
        )
        prompt = self._render(
            template,
            decision_description=truncate_prompt_content(decision_description or ""),
        )
        prompt += self._language_instruction(workspace.id)

        parsed, is_mock_fallback = self._complete_json_object(
            prompt,
            purpose="derive_adr_from_decision",
            artifact_id=str(workspace.id),
            context={"decision_description": decision_description},
        )

        draft = {
            "title": str(parsed.get("title", "")),
            "description": str(parsed.get("description", "")),
            "context": str(parsed.get("context", "")),
            "consequences": str(parsed.get("consequences", "")),
        }
        return {
            "draft": draft,
            "workspace_id": str(workspace.id),
            "is_mock_fallback": is_mock_fallback,
        }

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
        definition), as soon as no non-terminal transition remains, or once
        the intended destination is reached (see below).

        Explicit target (Phase 3, ``auto_approve_target`` in ``state_meta``):
        if the preset marks a state as the intended "auto" destination (e.g.
        ``adr_default``'s "Approved", ``risk_default``'s "Mitigated"), the
        walk stops as soon as that state is reached — crossing an approval
        gate if that is what it takes to get there — and never continues past
        it. This is what lets ``policy="auto"`` reach an entity's real steady
        state instead of stalling one hop early at the first approval gate.

        Fallback (no explicit target defined anywhere in this workflow):
        the walk stops *before* taking a transition that requires an approval
        role (see :func:`workflow.services.is_approval_gate`), exactly as
        before this preset gained explicit metadata. This fixes a bug where an actor holding
        ``approver``/``admin`` could otherwise walk a freshly-derived entity
        all the way to a business-terminal state such as ``Risk.Closed`` or
        ``Adr.Superseded`` — states that mean "this is done/superseded", not
        "this was just created". Without explicit target metadata, "auto"
        may only perform the self-service submission hops an ``editor`` could
        already do unsupervised; the first genuine approval decision (a
        transition whose ``allowed_roles`` do not include ``editor``) is left
        for a human to take explicitly, regardless of whether *ctx* actually
        holds a role that could pass it.

        Never raises: a validation failure (e.g. the caller's roles do not
        allow the next transition, or ``change_reason`` requirements are not
        met) simply stops the walk at whatever state was last reached — the
        entity stays a valid, persisted draft either way.

        Phase 5 (REQ-L2-RV-001): the walk additionally consults the
        workspace's effective ``ReviewPolicy``
        (``SettingsService.get_effective_review_policy``) before crossing any
        approval gate (``workflow.services.is_approval_gate``):

          - ``mode="auto"``: unchanged pre-Phase-5 behaviour (see above).
          - ``mode="review_all"``: never crosses an approval gate — stops at
            the first self-service hop's boundary, same as if no explicit
            ``auto_approve_target`` existed for this preset.
          - ``mode="review_changes"``: identical to "auto" for now — none of
            the current derive tools modifies a pre-existing approved
            artifact, so there is nothing to distinguish yet. Stored for
            forward compatibility (YAGNI-deferred, not silently dropped).
          - ``mode="review_high_risk"``: crosses a gate only if
            :meth:`_estimate_confidence` returns a value
            ``>= policy.min_confidence``; ``None`` (no signal) never crosses.

        Returns:
            The final workflow state name reached (``"draft"`` if no
            transition could be taken at all).
        """
        from workflow.definition_store import get_state_meta
        from workflow.models import WorkflowEngineDefinition
        from workflow.services import (
            get_available_transitions,
            is_approval_gate,
            transition,
        )
        from application.settings_service import SettingsService

        policy = SettingsService().get_effective_review_policy(
            ctx, workspace_id=workspace_id
        )
        confidence = (
            self._estimate_confidence(item_type, item_id)
            if policy.mode == "review_high_risk"
            else None
        )

        current_state = "draft"
        try:
            for _ in range(5):
                available = get_available_transitions(
                    item_id=item_id, item_type=item_type, workspace_id=workspace_id
                )
                current_state = available.current_state or current_state

                definition = WorkflowEngineDefinition.objects.filter(
                    workspace_id=workspace_id, item_type=item_type
                ).first()
                workflow_json = definition.workflow_json if definition else {}

                if get_state_meta(workflow_json, current_state).get(
                    "auto_approve_target", False
                ):
                    # Reached the preset's explicit "auto" destination — stop
                    # here regardless of what transitions remain open.
                    break

                if not available.transitions:
                    break

                has_explicit_target = any(
                    meta.get("auto_approve_target", False)
                    for meta in workflow_json.get("state_meta", {}).values()
                )

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

                if is_approval_gate(next_transition):
                    if policy.mode == "review_all":
                        # Never cross an approval gate unsupervised.
                        break
                    if policy.mode == "review_high_risk" and (
                        confidence is None or confidence < policy.min_confidence
                    ):
                        # No (or insufficient) confidence signal — leave the
                        # gate for a human.
                        break
                    if (
                        policy.mode in ("auto", "review_changes")
                        and not has_explicit_target
                    ):
                        # No explicit destination defined for this preset —
                        # fall back to the safe default: never cross an
                        # approval decision unsupervised.
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

    def _estimate_confidence(
        self, item_type: str, item_id: "UUID | str"
    ) -> "float | None":
        """Minimal v1 confidence heuristic (Phase 5, REQ-L2-RV-001).

        No LLM adapter surfaces a real confidence score today (verified: zero
        hits for ``confidence`` across ``application/ai_derivation_service.py``
        and ``llm_adapter/``). The mock provider's output is fully
        deterministic, so it is treated as maximum confidence (``1.0``);
        every real provider currently returns ``None`` ("no signal"), which
        ``_auto_approve``'s ``review_high_risk`` branch treats as always
        below threshold — the conservative default until a provider actually
        reports one.

        Args:
            item_type: Kept for a future richer heuristic (e.g. per-entity-type
                risk weighting); unused by the current placeholder.
            item_id: Kept for the same reason as ``item_type``.
        """
        from django.conf import settings as django_settings

        if getattr(django_settings, "LLM_PROVIDER", "mock") == "mock":
            return 1.0
        return None

    @staticmethod
    def _get_template_content(
        ctx: AuthContext, name: str, workspace_id: "UUID | None" = None
    ) -> str:
        """Return the effective prompt content for *name* (REQ-L2-PT-001).

        Thin delegation to :func:`application.prompt_resolver.resolve_template_content`
        — the fallback chain (workspace override -> tenant-global row ->
        factory default) now has exactly one implementation, shared with the
        MCP ``prompt_template.get`` tool and ``interview_protocol.get_protocol``.

        Kept as a staticmethod rather than deleted because 12 call sites
        across four services address it; the behaviour is unchanged except
        that an unknown slot now raises
        :class:`~application.prompt_resolver.PromptSlotNotFoundError`
        (a ``ValidationError`` subclass) instead of a bare ``KeyError``.
        """
        from application.prompt_resolver import resolve_template_content

        return resolve_template_content(name, ctx, workspace_id)

    @staticmethod
    def _render(template: str, **values: Any) -> str:
        """Substitute ``{name}`` placeholders without touching other braces.

        Delegates to :func:`application.prompt_resolver.render_template`; a
        literal ``str.format`` call would choke on JSON braces embedded in a
        user-customised prompt, so placeholders are replaced individually.
        """
        from application.prompt_resolver import render_template

        return render_template(template, **values)

    @staticmethod
    def _language_instruction(workspace_id: "UUID | str | None") -> str:
        """Return an explicit output-language directive for *workspace_id*.

        Issue #795: none of this module's content-generating derive prompts
        ever referenced ``Workspace.language`` -- the provider was free to
        answer in whatever language it happened to pick. Every such flow
        below appends this directive to its fully rendered prompt so the
        output language is pinned explicitly instead of left to chance, for
        every configured language *including* English: the observed drift
        (the same ``de`` workspace producing a Chinese answer from one flow
        and an English answer from another) shows an uninstructed provider
        cannot be trusted to default to English on its own either.

        Looked up fresh per call rather than threaded through as a
        parameter: most call sites only hold a bare workspace id (a foreign
        key column access, not a fetched ``Workspace`` row), so one
        lightweight primary-key lookup here is simpler than special-casing
        the couple of flows that already hold the row.

        Args:
            workspace_id: The workspace whose ``language`` should govern the
                response. ``None`` (no resolvable workspace) falls back to
                English, same as an unset/unknown language code.

        Returns:
            Directive text to append to a rendered prompt (leading blank
            line included, so it reads as its own paragraph regardless of
            what the template body ends with).
        """
        language_code = "en"
        if workspace_id is not None:
            language_code = (
                Workspace.objects.filter(id=workspace_id)
                .values_list("language", flat=True)
                .first()
                or "en"
            )
        language_name = LANGUAGE_INSTRUCTION_NAMES.get(language_code, "English")
        return (
            f"\n\nRespond in {language_name}. All generated titles, "
            f"descriptions and other free-text content must be written in "
            f"{language_name}."
        )

    @staticmethod
    def _resolve_and_render(
        ctx: AuthContext,
        name: str,
        workspace_id: "UUID | None" = None,
        *,
        config_overrides: "Dict[str, Any] | None" = None,
        **data_kwargs: Any,
    ) -> str:
        """Resolve *name* and render it with catalog config + data values.

        Preferred over the ``_get_template_content`` + ``_render`` pair for
        new flows: every ``config`` variable of the active tenant/workspace is
        injected automatically, so an admin-created variable becomes usable in
        this prompt without a code change (spec §3.2).
        """
        from application.prompt_resolver import resolve_and_render

        return resolve_and_render(
            name,
            ctx,
            workspace_id,
            config_overrides=config_overrides,
            **data_kwargs,
        )

    def _complete(
        self,
        prompt: str,
        *,
        purpose: str,
        artifact_id: UUID | str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Optional[str]]:
        """Run the configured provider's free-form completion (cached).

        Falls back to the credential-free mock provider when no provider is
        configured, so the flows degrade to deterministic output instead of
        failing hard (REQ-L2-AI-002; default provider is ``mock``).

        Genuine provider answers are cached in the shared cache backend keyed by
        provider, *purpose* (capability), *artifact_id* and a prompt hash
        (REQ-105). Mock-fallback results are never cached — they are degraded
        placeholders that must be recomputed once a real provider is available.

        Unlike the three capability-shaped flows (``validate_artifact``,
        ``decompose_requirement``, ``check_consistency``), the eight
        Draft/Accept flows in this service call ``provider.complete()``
        directly instead of going through ``CapabilityRouter`` (that router's
        capability set does not model these free-form prompts). To still get
        the same cost/audit/timeout guarantees as the router-routed
        capabilities, this method independently applies the per-tenant daily
        token limit (REQ-106), the hard sync timeout (REQ-084) and an audit
        log entry (REQ-L3-LA004-001) around the provider call (fix #115).
        Provider/transport failures are mapped to :class:`LlmResponseError`
        instead of escaping raw (fix #116) so every MCP tool in
        ``mcp_server.tools.ai_derivation`` — which already catches
        ``LlmResponseError`` — reports a clean ``INTERNAL_ERROR`` instead of a
        500 / transport fault.

        Returns:
            A ``(text, cache_key)`` tuple. *cache_key* is the cache-backend
            key this call read from or wrote to — the caller passes it back
            into :meth:`_discard_cached_completion` if it later decides the
            answer is unusable. It is ``None`` when the call degraded to the
            mock fallback before any cache key could be computed (no
            configured provider at all).

            This value used to be stashed on ``self._last_cache_key`` as a
            per-call "output parameter" instead of being returned. That is
            safe only when a fresh :class:`AiDerivationService` is built per
            request, as ``rest_api/views.py`` does — but the MCP transport
            shares ONE service instance across concurrently handled requests
            (``mcp_server/tool_registry.py`` builds the tool group once as a
            process-level singleton, and ``mcp_server/views.py`` dispatches
            requests onto a thread pool), so two interleaved calls on the
            same instance could overwrite each other's cache key: one
            request's failed parse would then evict the *other* request's
            still-valid cache entry (see issue #552 code review finding B2).
            Returning the key instead of storing it makes each call's key
            local to that call again.
        """
        from django.conf import settings

        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import (
            approximate_token_count,
            is_over_daily_limit,
            record_token_usage,
        )
        from persistence.tenancy import TenantContext, TenantContextNotSetError

        provider_name = getattr(settings, "LLM_PROVIDER", "unknown")

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
            # Fallback output is intentionally not cached (REQ-105); no cache
            # key was ever computed for it either.
            return f"{MOCK_FALLBACK_MARKER}{result}", None

        # fix #122: namespace the cache key by the *effective* provider
        # (`get_provider()` resolves the per-tenant LlmSettings override on top
        # of the env default — see providers._apply_db_settings) and by the
        # active tenant, not by the static env-configured LLM_PROVIDER name.
        # Keying on `provider_name` alone let one tenant's real-provider
        # response be cached under (and served back from) the same bucket as
        # every other tenant still on the "mock" default, and survived a
        # provider switch for the same tenant since the key never changed.
        effective_provider_name = getattr(provider, "PROVIDER_NAME", provider_name)
        try:
            cache_tenant_id = str(TenantContext.get_tenant())
        except TenantContextNotSetError:
            cache_tenant_id = "no-tenant"
        cache_key = _derivation_cache_key(
            f"{effective_provider_name}:{cache_tenant_id}",
            purpose,
            str(artifact_id),
            prompt,
        )

        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(
                "LLM derivation cache hit (purpose=%s, artifact=%s)",
                purpose,
                artifact_id,
            )
            return cached, cache_key

        audit_logger = LlmAuditLogger()

        # REQ-106: per-tenant daily token budget, enforced here because these
        # free-form flows bypass CapabilityRouter (fix #115). Fail-open by
        # design (is_over_daily_limit never raises) — only a real limit hit
        # blocks the call.
        if is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=purpose,
                artifact_id=str(artifact_id),
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise LlmResponseError(
                "Daily LLM token limit exceeded for this tenant. "
                "Try again later or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        try:
            # REQ-084: hard sync timeout, same setting CapabilityRouter uses
            # for its own sync calls, so this free-form path never blocks the
            # request thread longer than a router-routed call could.
            # Issue #342: resolved per *purpose* — workspace-wide prompts
            # (derive_glossary_from_workspace) get the longer cap, every
            # single-artifact flow keeps the tight REQ-084 default.
            timeout = resolve_timeout_seconds(purpose)
            result = provider.complete(
                prompt, purpose=purpose, context=context, timeout=timeout
            )
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            # Provider became unavailable for this specific call (e.g. the SDK
            # import failed lazily inside _chat) — degrade the same way as a
            # missing provider at construction time.
            logger.warning(
                "LLM provider %s failed mid-call, falling back to mock. Error: %s",
                provider_name,
                error,
            )
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=purpose,
                artifact_id=str(artifact_id),
                token_usage=None,
                success=False,
                error=str(error),
            )
            result = MockLlmProvider().complete(
                prompt, purpose=purpose, context=context
            )
            # This fallback is never cached (REQ-105) either, but the key was
            # already computed above so it is still returned — harmless for
            # eviction (nothing was ever written under it), and keeps the
            # returned key consistent with every other post-computation path.
            return f"{MOCK_FALLBACK_MARKER}{result}", cache_key
        except Exception as error:  # noqa: BLE001 — see fix #116 docstring note above
            # fix #116: circuit-breaker/timeout failures (LlmTransportError),
            # missing-SDK / SDK errors (RuntimeError) and any other provider
            # exception (rate limits, malformed SDK responses, ...) must not
            # escape this method uncaught — map them onto the one exception
            # type every ai_derivation MCP tool already handles.
            logger.warning(
                "LLM provider %s call failed (purpose=%s, artifact=%s): %s",
                provider_name,
                purpose,
                artifact_id,
                error,
            )
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=purpose,
                artifact_id=str(artifact_id),
                token_usage=None,
                success=False,
                error=str(error),
            )
            raise LlmResponseError(
                f"LLM provider '{provider_name}' call failed: {error}"
            ) from error

        # REQ-106: best-effort usage record; provider.complete() only returns
        # text (no token counts), so this call is logged with a real audit
        # entry but without an exact token count — still closing the "zero
        # audit trail" gap called out by fix #115.
        audit_logger.log_llm_call(
            provider=provider_name,
            capability=purpose,
            artifact_id=str(artifact_id),
            token_usage=None,
            success=True,
            error=None,
        )
        # Systemaudit 2026-08-27 item 14: this used to hardcode
        # ``input_tokens=0``, which made the per-tenant daily budget checked
        # by ``is_over_daily_limit()`` above structurally blind to this whole
        # sync path — the limit aggregates TokenUsageRecord rows, so rows that
        # are always 0 can never move it, and no amount of sync free-form
        # spend could ever trip a configured limit. The prompt and the
        # completion are estimated client-side instead (see
        # ``approximate_token_count``: a ~4-chars-per-token heuristic, not a
        # real tokenizer) so the budget sees an order-of-magnitude-correct
        # figure rather than a guaranteed zero.
        record_token_usage(
            provider=provider_name,
            capability=purpose,
            input_tokens=approximate_token_count(prompt),
            output_tokens=approximate_token_count(result),
        )

        # Never cache a fallback-marked (degraded) response (REQ-105), and
        # never cache a content-free one (issue #311, see
        # _is_empty_completion): both must be recomputed on the next call.
        if _is_empty_completion(result):
            logger.warning(
                "LLM returned an empty response (purpose=%s, artifact=%s, "
                "provider=%s); not cached so the next call retries.",
                purpose,
                artifact_id,
                effective_provider_name,
            )
        elif not result.startswith(MOCK_FALLBACK_MARKER):
            cache.set(cache_key, result, DERIVATION_CACHE_TTL_SECONDS)
        return result, cache_key

    def _complete_retrying(
        self,
        prompt: str,
        *,
        purpose: str,
        artifact_id: UUID | str,
        context: Optional[Dict[str, Any]],
        max_retries: int,
        parse: Callable[[str], Any],
    ) -> Tuple[Any, str, bool]:
        """Shared complete+parse retry loop behind the two ``_complete_json_*``
        methods (issue #311, #652).

        Calls :meth:`_complete` then *parse(raw)*. :meth:`_complete` caches
        the raw text *before* any flow can judge it, so on
        :class:`LlmResponseError` the cache entry is evicted (an immediate
        retry — the obvious reaction to the error — must actually reach the
        provider, not replay the same rejected text) and the call is retried
        up to *max_retries* times before re-raising, so a cold-start empty
        completion or transient truncation is recovered automatically
        instead of failing hard.

        Returns:
            ``(parsed, cache_key, is_mock_fallback)``.

            *cache_key* is returned so a caller can evict on a *later*,
            non-retriable validation failure (e.g. :meth:`_usable_entries`)
            using the same key.

            *is_mock_fallback* is True when :meth:`_complete` degraded to
            :class:`MockLlmProvider` for the attempt whose answer is being
            returned — i.e. the drafts built from it are deterministic
            placeholders, not a real LLM's proposal. The signal is read off
            the ``MOCK_FALLBACK_MARKER`` prefix here, *before* handing the
            text to *parse*, because both parsers strip that prefix before
            ``json.loads()``-ing the payload and would otherwise discard the
            only evidence that the answer was degraded (Systemaudit
            2026-08-27 item 11). Detecting it per attempt (rather than once
            up front) is what makes the flag describe the attempt that
            actually succeeded: a first attempt may fall back to the mock and
            fail to parse while the retry reaches the real provider, or vice
            versa. A cache hit is never marked — fallback answers are never
            cached (REQ-105).

        Raises:
            LlmResponseError: *parse* kept failing through the last attempt.
        """
        last_error: Optional[LlmResponseError] = None
        for attempt in range(max_retries + 1):
            raw, cache_key = self._complete(
                prompt, purpose=purpose, artifact_id=artifact_id, context=context
            )
            is_mock_fallback = bool(raw) and raw.startswith(MOCK_FALLBACK_MARKER)
            try:
                return parse(raw), cache_key, is_mock_fallback
            except LlmResponseError as exc:
                last_error = exc
                self._discard_cached_completion(
                    cache_key, purpose=purpose, artifact_id=artifact_id
                )
                if attempt < max_retries:
                    continue
                raise
        raise last_error  # pragma: no cover - unreachable, satisfies static analysis

    def _complete_json_list(
        self,
        prompt: str,
        *,
        purpose: str,
        artifact_id: UUID | str,
        context: Optional[Dict[str, Any]] = None,
        require_objects: bool = True,
        max_retries: int = 1,
    ) -> Tuple[List[Any], bool]:
        """Run a completion and return its JSON array (issue #311, #652).

        The single entry point for every array-shaped flow: it chains
        :meth:`_complete_retrying` (parsing via :meth:`_parse_json_list`)
        and — unless *require_objects* is False, as for the id-list flow
        :meth:`suggest_architecture_for_requirement` — :meth:`_usable_entries`.

        Args:
            prompt: The rendered prompt.
            purpose: Capability name (cache namespace, audit entry, log text).
            artifact_id: Source artifact of this derivation (cache namespace).
            context: Optional structured hints for the provider.
            require_objects: Whether the array must carry JSON objects.
            max_retries: Number of extra attempts after the first failure.

        Returns:
            ``(items, is_mock_fallback)``. *items* is the parsed array — only
            its object entries when *require_objects*. *is_mock_fallback* is
            True only when :meth:`_complete` *unexpectedly* degraded to
            MockLlmProvider (the configured/resolved provider raised or the
            call itself failed mid-flight) — NOT when ``LLM_PROVIDER=mock``
            was deliberately configured and answered without error; every
            flow surfaces it under the same ``is_mock_fallback`` response key
            so a caller can tell a real proposal from an unplanned degraded
            placeholder (Systemaudit 2026-08-27 item 11).

            SA-27 (Systemaudit 2026-08-27 AP-6) note: this is a narrower
            definition than ``BundleCompressionService.CompressionResult.
            is_mock_fallback``, which (issue #442) flags a *successfully
            resolved* mock provider too — deliberately, because that flow's
            output is cached for an hour and served without any human review
            step, so a deployment's default ``LLM_PROVIDER=mock`` placeholder
            must never be mistaken for a genuine compression. The
            draft-then-review flows in this module (N1/N3/N8/MainGoal) have
            the opposite need: a deliberately-configured mock during
            dev/demo is expected and not itself noteworthy, so only an
            *unplanned* degradation is worth flagging to the reviewer. Both
            definitions are intentional and independently tested — do not
            "fix" one to match the other without re-reading both rationales.

        Raises:
            LlmResponseError: The response was not a usable JSON array.
        """
        items, cache_key, is_mock_fallback = self._complete_retrying(
            prompt,
            purpose=purpose,
            artifact_id=artifact_id,
            context=context,
            max_retries=max_retries,
            parse=self._parse_json_list,
        )
        if require_objects:
            try:
                items = self._usable_entries(items, purpose=purpose)
            except LlmResponseError:
                # Data-quality rejection, not a parse error — no retry
                # (see test_does_not_retry_on_valid_json_with_wrong_structure),
                # but the raw answer must still be evicted so an immediate
                # caller-driven retry reaches the provider instead of
                # replaying the same unusable array from cache.
                self._discard_cached_completion(
                    cache_key, purpose=purpose, artifact_id=artifact_id
                )
                raise
        return items, is_mock_fallback

    def _complete_json_object(
        self,
        prompt: str,
        *,
        purpose: str,
        artifact_id: UUID | str,
        context: Optional[Dict[str, Any]] = None,
        max_retries: int = 1,
    ) -> Tuple[Dict[str, Any], bool]:
        """Object-shaped sibling of :meth:`_complete_json_list` (issue #311, #652).

        Used by the single-draft flows (``derive_testcase_from_requirement``,
        ``derive_adr_from_decision``) and evicts the cached answer on the same
        grounds: a response the flow cannot parse must not be replayed from the
        cache for the rest of the TTL.

        Returns:
            ``(obj, is_mock_fallback)`` — see :meth:`_complete_json_list` for
            the meaning of the flag.

        Raises:
            LlmResponseError: The response was not a JSON object.
        """
        obj, _cache_key, is_mock_fallback = self._complete_retrying(
            prompt,
            purpose=purpose,
            artifact_id=artifact_id,
            context=context,
            max_retries=max_retries,
            parse=self._parse_json_object,
        )
        return obj, is_mock_fallback

    def _discard_cached_completion(
        self, cache_key: Optional[str], *, purpose: str, artifact_id: UUID | str
    ) -> None:
        """Drop the cache entry of the completion that produced *cache_key*.

        *cache_key* is the value :meth:`_complete` returned for the call
        whose answer the caller just rejected — passed in explicitly rather
        than read off a ``self`` attribute, so this stays correct even when
        the MCP transport shares one :class:`AiDerivationService` instance
        across concurrently handled requests (see :meth:`_complete`'s
        docstring / issue #552 finding B2: a shared instance attribute let
        one request's failed parse evict a *different*, still-valid
        in-flight request's cache entry).

        No-op when *cache_key* is ``None`` (the mock-fallback path never
        computes one). Never raises — failing to evict must not replace the
        caller's real error with a cache-backend one.
        """
        if cache_key is None:
            return
        try:
            cache.delete(cache_key)
        except Exception:  # pragma: no cover - defensive; cache backend down
            logger.warning(
                "Failed to evict unusable cached LLM response "
                "(purpose=%s, artifact=%s)",
                purpose,
                artifact_id,
                exc_info=True,
            )
            return
        logger.warning(
            "Evicted an unusable cached LLM response (purpose=%s, artifact=%s) "
            "so the next call retries the provider.",
            purpose,
            artifact_id,
        )

    @staticmethod
    def _parse_json_list(raw: str) -> List[Any]:
        """Parse *raw* into a JSON list, tolerating Markdown code fences.

        Raises:
            LlmResponseError: When *raw* is empty, not valid JSON, or not a list.
        """
        text = raw.strip() if raw else ""
        if not text:
            raise LlmResponseError(
                "The LLM response was empty completion (cold-start or truncation)."
            )
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
    def _usable_entries(items: List[Any], *, purpose: str) -> List[Dict[str, Any]]:
        """Return the object entries of a parsed LLM array (issue #311).

        Every list-shaped Draft/Accept flow builds its drafts from the JSON
        objects in the provider's array and has to skip anything else — a
        model that answers ``["Sub-requirement one", ...]`` instead of
        ``[{"title": ...}, ...]`` must not crash the flow with an
        ``AttributeError`` on ``item.get``.

        Silently dropping *all* of them, however, made a structurally
        unusable answer look exactly like a model that legitimately proposed
        nothing: both returned ``drafts: []`` with no error and no log line
        (issue #311). So the two cases are separated here:

        * array non-empty, no object in it → the extraction failed, raise
          :class:`LlmResponseError` (mapped to ``INTERNAL_ERROR`` by every
          ``mcp_server.tools.ai_derivation`` handler and to a 5xx by the REST
          views, i.e. a *visible* failure);
        * array with a mix → keep the usable entries, WARN about the dropped
          ones, since a partial answer is still worth showing the user;
        * empty array → returned unchanged. An empty list stays a legal
          answer ("nothing to propose") and several callers/tests rely on
          that, so it is never an error here — the decompose flow annotates
          it for the caller instead (see
          :meth:`decompose_requirement_next_level`).

        Args:
            items: The already parsed JSON array (see :meth:`_parse_json_list`).
            purpose: Capability name of the calling flow, for the log/error text.

        Returns:
            The subset of *items* that are dicts.

        Raises:
            LlmResponseError: *items* is non-empty but contains no object.
        """
        entries = [item for item in items if isinstance(item, dict)]
        if items and not entries:
            raise LlmResponseError(
                f"The LLM response for '{purpose}' was a JSON array of "
                f"{len(items)} entries, but none of them was an object with "
                "the expected draft fields — nothing could be extracted."
            )
        if len(entries) != len(items):
            logger.warning(
                "Dropped %d of %d non-object entries from the LLM response "
                "(purpose=%s).",
                len(items) - len(entries),
                len(items),
                purpose,
            )
        return entries

    @staticmethod
    def _parse_json_object(raw: str) -> Dict[str, Any]:
        """Parse *raw* into a JSON object, tolerating Markdown code fences.

        Sibling of :meth:`_parse_json_list` for flows whose LLM response is a
        single JSON object rather than an array (SysEng 2.0 N5).

        Raises:
            LlmResponseError: When *raw* is empty, not valid JSON, or not an object.
        """
        text = raw.strip() if raw else ""
        if not text:
            raise LlmResponseError(
                "The LLM response was empty completion (cold-start or truncation)."
            )
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
    "BUNDLE_COMPRESSION_PROMPT_TEMPLATE",
    "INTERVIEW_GROUNDING_RANK_PROMPT_TEMPLATE",
    "INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE",
    "invalidate_derivation_cache",
]
