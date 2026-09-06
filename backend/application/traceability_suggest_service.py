"""
COMP-AS-N3 TraceabilitySuggestService — KI-Copilot N3 (`traceability.suggest_links`), first stage.

UMSETZUNGSPLAN_SYSENG_2.0.md §3.2 + §4 Phase 4b. First-stage N3, verbatim
from §3.2: "Da der Auditor (Abschnitt 2) fehlende Links bereits
deterministisch findet (z.B. TRACE-P1b: Requirement ohne
derives-from-Upstream), könnte N3 in einer ersten Ausbaustufe primär die
Auditor-Findings ranken und erklären (welches der mehreren plausiblen
Ziel-Artefakte ist am wahrscheinlichsten gemeint), statt eine unabhängige
Vektorsuche über den gesamten Artefaktbestand zu betreiben." This module is
exactly that. It never queries a vector index and never depends on
``pgvector`` — a deferred, explicitly out-of-scope spike per §3.2/§4 ("Das
verschiebt die pgvector-Entscheidung auf eine spätere, optionale
Ausbaustufe."). Instead it:

  1. Runs the Phase-3 SE-Auditor (via ``AuditService.run_audit``, like N8)
     and filters findings that name a *missing* trace link — TRACE-P1,
     TRACE-P1b, TRACE-P2 (see ``_SUPPORTED_RULE_IDS``). All three name the
     Requirement missing the link as ``finding.artifact_ids[0]``
     (``traceability/audit/rules/trace_derivation_allocation.py``).
  2. For each such finding, deterministically computes a bounded candidate
     list of type-compatible, workspace-scoped artifacts — StakeholderNeed
     for TRACE-P1, StakeholderNeed + other Requirements for TRACE-P1b,
     ArchitectureElement for TRACE-P2 — ranked by a plain keyword-overlap
     heuristic over title/description text. No embeddings, no vector
     column, no similarity index.
  3. Hands the finding + its candidate pool to the LLM adapter, asking it
     to rank the candidates ("which is the most likely intended target,
     and why") — mirrors ``AiReviewService``'s prompt-with-context pattern.
  4. Resolves the LLM's ranking back against the real finding + the real
     candidate pool this service computed (never an id the LLM invents) —
     the same referential-integrity gate N8 uses
     (``AiReviewService._build_packages``): an index the provider
     hallucinates (out of range, wrong type, duplicate) is dropped rather
     than surfaced as a fake suggestion.

Referential-integrity guarantee (acceptance criterion, §4 Phase 4b: "N3
(Erststufe): Ranking-Ausgabe referenziert existierende Findings, keine
pgvector-Abhängigkeit im Code"): a suggestion's ``finding_index`` is only
ever accepted if it matches an index from the *actual*
``AuditReport.findings`` of the current run, and every ``ranked_candidates``
entry is only ever accepted if it is one of the *actual* candidates this
service computed for that finding — never an artifact id or title taken
verbatim from the LLM response.

Architecture: Layer-2 facade (ADR-01) wrapping ``AuditService`` (Phase 3) +
``llm_adapter.providers`` (mock default, graceful degradation on provider
failure — mirrors ``AiReviewService._complete``, the N8 precedent for this
LLM-completion-with-mock-fallback pattern in this layer).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.audit_service import AuditFindingView, AuditService
from application.base import ServiceBase
from traceability.audit import AuditScope
from traceability.audit.registry import TRACE_P1, TRACE_P1B, TRACE_P2

logger = logging.getLogger(__name__)

# Rules this first stage covers: all three name a *missing* link and a
# single Requirement "source" (finding.artifact_ids[0]) whose plausible
# link targets can be enumerated deterministically from the workspace graph
# (see module docstring). TRACE-P3/-P4/... are out of scope for this stage
# (no single-source "missing link" shape to rank candidates for).
_SUPPORTED_RULE_IDS = frozenset({TRACE_P1, TRACE_P1B, TRACE_P2})

_DEFAULT_MAX_CANDIDATES = 5

_WORD_RE = re.compile(r"[a-zA-ZäöüÄÖÜß0-9]+")


def _keywords(text: str) -> frozenset:
    """Lower-cased word set for a plain keyword-overlap heuristic.

    This is the entire "similarity" computation in this module — no
    embeddings, no vector index, no ``pgvector`` (§3.2 first-stage
    acceptance criterion).
    """
    return frozenset(w.lower() for w in _WORD_RE.findall(text or ""))


# Prompt template for the llm_adapter capability purpose
# ``traceability_suggest_links``. Kept as a module constant, mirroring the
# N8 precedent (AI_REVIEW_PROMPT_TEMPLATE): the mock provider ignores the
# prose and ranks deterministically from the structured
# ``context["findings"]`` list.
SUGGEST_LINKS_PROMPT_TEMPLATE = (
    "You are a systems-engineering traceability assistant. Below is a JSON "
    "array of audit findings, each describing a Requirement that is missing "
    "an upstream derivation or allocation link, with a 'finding_index', the "
    "'rule_id', the 'source_title', and a 'candidates' array (each with a "
    "'candidate_index', 'title' and 'artifact_type' — a deterministic, "
    "keyword-overlap-ranked shortlist, NOT a vector search). Rank the "
    "candidates for each finding from most to least likely the correct "
    "link target and give a short rationale for the top choice. Respond "
    "with a JSON array of objects, each with 'finding_index' (echoed from "
    "the input), 'ranked_candidate_indices' (the 'candidate_index' values "
    "for that finding, most likely first — and ONLY values from that "
    "finding's 'candidates' list; never invent one), and 'rationale' (why "
    "the top candidate is the most likely target).\n\nFindings:\n{findings_json}"
)


# Prompt purpose name — must stay in the workspace-wide set of
# ``llm_adapter.timeouts.WORKSPACE_WIDE_PURPOSES`` (issue #342).
_SUGGEST_LINKS_PURPOSE = "traceability_suggest_links"


class SuggestLinksResponseError(RuntimeError):
    """Raised when the LLM call fails or returns unparseable content.

    Sibling of ``application.ai_review_service.AiReviewResponseError``: the
    request itself was valid, but the provider misbehaved. Maps to HTTP 500
    in the REST layer and to an INTERNAL_ERROR ToolResult in the MCP layer.

    Issue #342: this also covers *transport* failures (timeout, open circuit
    breaker, SDK error). They used to escape ``_complete`` raw as an
    ``LlmTransportError`` and reached the MCP/REST boundary as an unhandled
    exception; now every caller gets the same catchable error type with an
    actionable message.
    """


# ---------------------------------------------------------------------------
# Result DTOs (JSON-serialisable — the REST/MCP layer only calls to_dict()).
# ---------------------------------------------------------------------------


@dataclass
class LinkCandidate:
    """One deterministic, type-compatible candidate target for a finding.

    ``score`` is the plain keyword-overlap count between the source
    Requirement's title+description and this candidate's title+description
    — the "simple deterministic heuristic" the first N3 stage uses instead
    of a vector search (§3.2).
    """

    artifact_id: str
    title: str
    artifact_type: str
    score: int

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "title": self.title,
            "artifact_type": self.artifact_type,
            "score": self.score,
        }


@dataclass
class LinkSuggestion:
    """One ranked-candidate suggestion for a single, real audit finding.

    ``finding_index`` always matches an index from the real
    ``AuditReport.findings`` and ``ranked_candidates`` is always a
    (sub)list of the real candidate pool this service computed for that
    finding — see the module docstring's referential-integrity guarantee.
    """

    finding_index: int
    rule_id: str
    source_artifact_id: str
    ranked_candidates: List[LinkCandidate] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "finding_index": self.finding_index,
            "rule_id": self.rule_id,
            "source_artifact_id": self.source_artifact_id,
            "ranked_candidates": [c.to_dict() for c in self.ranked_candidates],
            "rationale": self.rationale,
        }


@dataclass
class SuggestLinksResult:
    """Full N3 run: tier/provider metadata plus the ranked suggestions.

    ``truncated`` / ``total_findings_available`` (BUG-15 follow-up M2):
    ``suggest_links()`` reads ``report.findings`` from
    ``AuditService.run_audit``, which caps at
    ``AuditService.MAX_REPORT_FINDINGS`` — so ``total_findings`` here is the
    *returned* (possibly capped) count, same convention as
    ``AuditReport.counts.total``. Propagated straight from the underlying
    ``AuditReport`` so an MCP/REST caller can tell a capped run apart from a
    genuinely complete one instead of the signal being dropped at this layer.
    """

    tier: str
    provider: str
    degraded: bool
    total_findings: int = 0
    eligible_findings: int = 0
    truncated: bool = False
    total_findings_available: int = 0
    suggestions: List[LinkSuggestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "provider": self.provider,
            "degraded": self.degraded,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "truncated": self.truncated,
            "total_findings_available": self.total_findings_available,
            "counts": {
                "total_findings": self.total_findings,
                "eligible_findings": self.eligible_findings,
                "suggestions": len(self.suggestions),
            },
        }


class TraceabilitySuggestService(ServiceBase):
    """Single-Entry-Point facade for the N3 ``traceability.suggest_links`` copilot.

    First stage only (§3.2): ranks and explains candidates for findings the
    SE-Auditor already raises. No independent vector search.
    """

    def __init__(self, audit_service: Optional[AuditService] = None) -> None:
        self._audit = audit_service or AuditService()

    def suggest_links(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        tier: Optional[str] = None,
        scopes: Optional[Sequence[AuditScope]] = None,
        max_candidates: int = _DEFAULT_MAX_CANDIDATES,
    ) -> SuggestLinksResult:
        """Rank plausible link targets for missing-link SE-Auditor findings.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Authenticated, tenant-scoped context.
            tier: Rigor tier override, forwarded to ``AuditService.run_audit``
                (defaults to the workspace's active preset).
            scopes: Baseline scopes, forwarded to ``AuditService.run_audit``.
            max_candidates: Upper bound on the candidate shortlist handed to
                the LLM per finding (deterministic heuristic, not a hard
                domain limit).

        Returns:
            :class:`SuggestLinksResult` — zero suggestions (not an error)
            when there are no missing-link findings, or when every such
            finding has an empty candidate pool (e.g. no StakeholderNeed
            exists yet).

        Raises:
            NotFoundError: The workspace does not exist for this tenant.
            SuggestLinksResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        report = self._audit.run_audit(workspace_id, ctx, tier=tier, scopes=scopes)
        findings = report.findings

        eligible = [
            fv
            for fv in findings
            if fv.finding.rule_id in _SUPPORTED_RULE_IDS and fv.finding.artifact_ids
        ]
        if not eligible:
            return SuggestLinksResult(
                tier=report.tier,
                provider="mock",
                degraded=False,
                total_findings=len(findings),
                eligible_findings=0,
                truncated=report.truncated,
                total_findings_available=report.total_findings_available,
            )

        tenant_id = str(ctx.tenant_id)
        ws_id = str(workspace_id)

        candidates_by_index: Dict[int, List[LinkCandidate]] = {}
        finding_payloads: List[Dict[str, Any]] = []
        for fv in eligible:
            source_id = fv.finding.artifact_ids[0]
            source_title, source_text = self._source_lookup(source_id, tenant_id, ws_id)
            candidates = self._build_candidates(
                fv.finding.rule_id,
                source_id=source_id,
                source_text=source_text,
                tenant_id=tenant_id,
                workspace_id=ws_id,
                limit=max_candidates,
            )
            if not candidates:
                # No plausible target exists yet (e.g. workspace has no
                # StakeholderNeed at all) — nothing to rank for this finding.
                continue
            candidates_by_index[fv.index] = candidates
            finding_payloads.append(self._finding_payload(fv, source_title, candidates))

        if not finding_payloads:
            return SuggestLinksResult(
                tier=report.tier,
                provider="mock",
                degraded=False,
                total_findings=len(findings),
                eligible_findings=0,
                truncated=report.truncated,
                total_findings_available=report.total_findings_available,
            )

        raw, provider_name, degraded = self._complete(finding_payloads, workspace_id=ws_id)
        proposed = self._parse_suggestions(raw)

        by_index: Dict[int, AuditFindingView] = {fv.index: fv for fv in findings}
        suggestions = self._build_suggestions(proposed, by_index, candidates_by_index)

        return SuggestLinksResult(
            tier=report.tier,
            provider=provider_name,
            degraded=degraded,
            total_findings=len(findings),
            eligible_findings=len(finding_payloads),
            truncated=report.truncated,
            total_findings_available=report.total_findings_available,
            suggestions=suggestions,
        )

    # ------------------------------------------------------------------
    # Internal — deterministic candidate search (no embeddings/pgvector)
    # ------------------------------------------------------------------

    @staticmethod
    def _source_lookup(
        source_id: str, tenant_id: str, workspace_id: str
    ) -> Tuple[str, str]:
        """Return ``(title, "title description")`` for the source Requirement.

        All three supported rules (TRACE-P1/-P1b/-P2) name a Requirement as
        ``finding.artifact_ids[0]`` — see
        ``traceability/audit/rules/trace_derivation_allocation.py``.
        """
        from persistence.models import Requirement

        row = (
            Requirement.unscoped.filter(
                tenant_id=tenant_id,
                artifact__workspace_id=workspace_id,
                artifact_id=source_id,
            )
            .values_list("title", "description")
            .first()
        )
        if row is None:
            return "", ""
        title, description = row
        return title, f"{title} {description}"

    @staticmethod
    def _candidate_pool(
        rule_id: str, source_id: str, tenant_id: str, workspace_id: str
    ) -> Dict[str, Tuple[str, str, str]]:
        """Return ``{artifact_id: (title, description, artifact_type)}`` for
        the type-compatible candidate pool of *rule_id* (workspace-scoped,
        active/non-deleted, excluding the source itself).

        Mirrors the endpoint-type legality each rule itself enforces
        (``traceability/audit/rules/trace_derivation_allocation.py``):
        TRACE-P1 only accepts a StakeholderNeed target; TRACE-P1b accepts
        either a StakeholderNeed or another Requirement; TRACE-P2 only
        accepts an ArchitectureElement.
        """
        from persistence.models import (
            ArchitectureElement,
            Requirement,
            StakeholderNeed,
        )
        from workflow import state_reader
        from workflow.services import outdated_item_ids

        pool: Dict[str, Tuple[str, str, str]] = {}

        def _add(qs, artifact_type: str, item_type: "str | None" = None) -> None:
            """Add every row of *qs* to *pool*, keyed by artifact_id.

            *item_type* given: *qs* is not yet outdated-filtered — resolved
            through WorkflowItemState (batched, Datenmodell-Konsolidierung
            Phase 1). Task 12: the ``status`` column is dropped, so a row
            never wired into one falls back to *item_type*'s preset initial
            state instead (documented, reviewed data-loss tradeoff, see Task
            12 report Finding 2). *item_type* ``None``: *qs* is already fully
            filtered (e.g. ArchitectureElement's ``outdated_item_ids``
            exclude, which has no status column to fall back to), so rows are
            added as-is.
            """
            if item_type is None:
                for artifact_id, title, description in qs.values_list(
                    "artifact_id", "title", "description"
                ):
                    aid = str(artifact_id)
                    if aid == source_id:
                        continue
                    pool[aid] = (title, description, artifact_type)
                return

            rows = list(
                qs.values_list("id", "artifact_id", "title", "description")
            )
            # This service, like the SE-Auditor rules, is called outside a
            # request-scoped TenantContext in some paths -- the explicit
            # tenant_id= keeps the lookup correct regardless (N1).
            states = state_reader.current_states(
                item_type, (row[0] for row in rows), tenant_id=tenant_id
            )
            item_type_initial_state = state_reader.initial_state(item_type)
            for row_id, artifact_id, title, description in rows:
                if (states.get(str(row_id)) or item_type_initial_state) == "outdated":
                    continue
                aid = str(artifact_id)
                if aid == source_id:
                    continue
                pool[aid] = (title, description, artifact_type)

        if rule_id in (TRACE_P1, TRACE_P1B):
            needs = StakeholderNeed.unscoped.filter(
                tenant_id=tenant_id, artifact__workspace_id=workspace_id
            )
            _add(needs, "stakeholder_need", "StakeholderNeed")
        if rule_id == TRACE_P1B:
            reqs = Requirement.unscoped.filter(
                tenant_id=tenant_id, artifact__workspace_id=workspace_id
            )
            _add(reqs, "requirement", "Requirement")
        if rule_id == TRACE_P2:
            # ArchitectureElement has no status mirror — outdate() only writes
            # WorkflowItemState (see workflow.services.outdated_item_ids).
            arch = ArchitectureElement.unscoped.filter(
                tenant_id=tenant_id, artifact__workspace_id=workspace_id
            ).exclude(id__in=outdated_item_ids("ArchitectureElement", tenant_id=tenant_id))
            _add(arch, "architecture_element")
        return pool

    def _build_candidates(
        self,
        rule_id: str,
        *,
        source_id: str,
        source_text: str,
        tenant_id: str,
        workspace_id: str,
        limit: int,
    ) -> List[LinkCandidate]:
        """Score + sort the candidate pool by keyword overlap (deterministic).

        Sort key: highest overlap score first; ties broken by title then id
        so the shortlist (and therefore the LLM prompt) is reproducible
        across runs against the same data.
        """
        pool = self._candidate_pool(rule_id, source_id, tenant_id, workspace_id)
        source_kw = _keywords(source_text)

        scored: List[Tuple[int, str, str, str]] = []
        for artifact_id, (title, description, artifact_type) in pool.items():
            score = len(source_kw & _keywords(f"{title} {description}"))
            scored.append((score, title, artifact_id, artifact_type))
        scored.sort(key=lambda row: (-row[0], row[1], row[2]))

        return [
            LinkCandidate(
                artifact_id=artifact_id,
                title=title,
                artifact_type=artifact_type,
                score=score,
            )
            for score, title, artifact_id, artifact_type in scored[:limit]
        ]

    @staticmethod
    def _finding_payload(
        fv: AuditFindingView, source_title: str, candidates: List[LinkCandidate]
    ) -> Dict[str, Any]:
        """Render one eligible finding as the dict handed to the LLM as context."""
        return {
            "finding_index": fv.index,
            "rule_id": fv.finding.rule_id,
            "source_artifact_id": fv.finding.artifact_ids[0],
            "source_title": source_title,
            "candidates": [
                {
                    "candidate_index": i,
                    "artifact_id": c.artifact_id,
                    "title": c.title,
                    "artifact_type": c.artifact_type,
                    "score": c.score,
                }
                for i, c in enumerate(candidates)
            ],
        }

    # ------------------------------------------------------------------
    # Internal — suggestion construction (the referential-integrity gate)
    # ------------------------------------------------------------------

    def _build_suggestions(
        self,
        proposed: list,
        by_index: Dict[int, AuditFindingView],
        candidates_by_index: Dict[int, List[LinkCandidate]],
    ) -> List[LinkSuggestion]:
        """Resolve the LLM's proposed rankings against the real findings/candidates.

        ``finding_index`` is looked up in *by_index* (built from the actual
        :class:`~application.audit_service.AuditReport`), and every
        ``ranked_candidate_indices`` entry is looked up in
        *candidates_by_index* (built from this service's own deterministic
        candidate search) — never from the LLM output. An index that does
        not resolve — out of range, wrong type, or a repeat — is dropped. A
        suggestion left with zero valid candidates after filtering is
        dropped entirely rather than returned as an empty, non-actionable
        shell.
        """
        suggestions: List[LinkSuggestion] = []
        for item in proposed:
            if not isinstance(item, dict):
                continue
            finding_index = self._coerce_index(item.get("finding_index"))
            if finding_index is None or finding_index not in by_index:
                continue
            if finding_index not in candidates_by_index:
                continue

            fv = by_index[finding_index]
            real_candidates = candidates_by_index[finding_index]

            raw_ranking = item.get("ranked_candidate_indices")
            if not isinstance(raw_ranking, list):
                continue

            ranked: List[LinkCandidate] = []
            seen = set()
            for raw_idx in raw_ranking:
                idx = self._coerce_index(raw_idx)
                if idx is None or idx in seen or idx < 0 or idx >= len(real_candidates):
                    continue
                seen.add(idx)
                ranked.append(real_candidates[idx])

            if not ranked:
                continue

            suggestions.append(
                LinkSuggestion(
                    finding_index=finding_index,
                    rule_id=fv.finding.rule_id,
                    source_artifact_id=fv.finding.artifact_ids[0],
                    ranked_candidates=ranked,
                    rationale=str(item.get("rationale", "")),
                )
            )
        return suggestions

    @staticmethod
    def _coerce_index(raw_idx: Any) -> Optional[int]:
        """Best-effort int coercion for a single proposed index, or None."""
        if isinstance(raw_idx, bool):
            return None
        try:
            return int(raw_idx)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Internal — LLM plumbing (mirrors AiReviewService._complete)
    # ------------------------------------------------------------------

    def _complete(
        self, finding_payloads: List[Dict[str, Any]], *, workspace_id: str
    ) -> Tuple[str, str, bool]:
        """Call the LLM provider for a candidate ranking (graceful degradation).

        Returns ``(raw_completion, provider_name, degraded)``. On any
        provider configuration error it degrades to the credential-free
        deterministic mock so the suggest-links flow never crashes
        (REQ-L2-AI-002; default provider is ``mock``).

        Issue #342: the prompt spans every finding in the workspace, so the
        call runs under the workspace-wide timeout resolved by
        :func:`llm_adapter.timeouts.resolve_timeout_seconds` instead of the
        provider's 30s config default. Transport failures (timeout, open
        circuit breaker) are mapped to :class:`SuggestLinksResponseError`
        rather than escaping as an unhandled ``LlmTransportError``.

        Code review finding: this call bypassed REQ-106 (per-tenant daily LLM
        token budget) and the LlmAuditLog trail entirely -- neither an
        is_over_daily_limit() check beforehand nor a
        LlmAuditLogger.log_llm_call()/record_token_usage() call afterward,
        unlike every other free-form LLM flow in this codebase. Both are now
        applied here, mirroring AiDerivationService._complete /
        BundleCompressionService._call_provider.

        Raises:
            SuggestLinksResponseError: The provider call failed outright.
            LlmResponseError: The tenant's daily LLM token budget is already
                exceeded (checked before the real-provider call only; the
                mock-fallback path is exempt, ADR-02).
        """
        from django.conf import settings

        from application.ai_derivation_service import LlmResponseError
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

        prompt = SUGGEST_LINKS_PROMPT_TEMPLATE.format(
            findings_json=json.dumps(finding_payloads)
        )
        context = {"findings": finding_payloads}
        provider_name = getattr(settings, "LLM_PROVIDER", "mock")
        audit_logger = LlmAuditLogger()
        degraded = False
        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            logger.warning(
                "traceability.suggest_links: provider %s unavailable, using mock. %s",
                provider_name,
                error,
            )
            provider = MockLlmProvider()
            provider_name = "mock"
            degraded = True

        if not degraded and is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=_SUGGEST_LINKS_PURPOSE,
                artifact_id=workspace_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise LlmResponseError(
                "Daily LLM token limit exceeded for this tenant. "
                "Try again later or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        timeout = resolve_timeout_seconds(_SUGGEST_LINKS_PURPOSE)
        try:
            raw = provider.complete(
                prompt,
                purpose=_SUGGEST_LINKS_PURPOSE,
                context=context,
                timeout=timeout,
            )
        except Exception as error:  # noqa: BLE001 — see class docstring (#342)
            logger.warning(
                "traceability.suggest_links: provider %s call failed "
                "(timeout=%ss): %s",
                provider_name,
                timeout,
                error,
            )
            if not degraded:
                audit_logger.log_llm_call(
                    provider=provider_name,
                    capability=_SUGGEST_LINKS_PURPOSE,
                    artifact_id=workspace_id,
                    token_usage=None,
                    success=False,
                    error=str(error),
                )
            raise SuggestLinksResponseError(
                f"The LLM provider '{provider_name}' did not answer the "
                f"suggest_links request within {timeout:.0f}s ({error}). "
                "Narrow the request (scope=document) or raise "
                "LLM_LONG_RUNNING_TIMEOUT."
            ) from error

        if not degraded:
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=_SUGGEST_LINKS_PURPOSE,
                artifact_id=workspace_id,
                token_usage=None,
                success=True,
                error=None,
            )
            # SA-26: this used to hardcode input_tokens=0, leaving the daily
            # budget (is_over_daily_limit above) blind to this call's real
            # spend. Estimate both sides client-side, matching every other
            # free-form path (see ``approximate_token_count``).
            record_token_usage(
                provider=provider_name,
                capability=_SUGGEST_LINKS_PURPOSE,
                input_tokens=approximate_token_count(prompt),
                output_tokens=approximate_token_count(raw),
            )
        return raw, provider_name, degraded

    @staticmethod
    def _parse_suggestions(raw: str) -> list:
        """Parse *raw* into a JSON list, tolerating Markdown fences / mock-fallback marker."""
        from application.ai_derivation_service import MOCK_FALLBACK_MARKER

        text = (raw or "").strip()
        if text.startswith(MOCK_FALLBACK_MARKER):
            text = text[len(MOCK_FALLBACK_MARKER):].strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise SuggestLinksResponseError(
                "The LLM suggest_links response was not valid JSON."
            ) from exc
        if not isinstance(parsed, list):
            raise SuggestLinksResponseError(
                "The LLM suggest_links response was not a JSON array as expected."
            )
        return parsed


__all__ = [
    "TraceabilitySuggestService",
    "SuggestLinksResult",
    "LinkSuggestion",
    "LinkCandidate",
    "SuggestLinksResponseError",
    "SUGGEST_LINKS_PROMPT_TEMPLATE",
]
