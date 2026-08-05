"""
COMP-AS-N8 AiReviewService — KI-Copilot N8 (`audit.ai_review`).

UMSETZUNGSPLAN_SYSENG_2.0.md §3.2 + §4 Phase 4b. N8 reads every SE-Auditor
finding for a workspace (via the Phase-3 :class:`~application.audit_service.
AuditService` facade) and asks the LLM adapter to bundle related findings
into strategic refactoring packages — e.g. "all TRACE-P2 findings for
subsystem X" get one package with a combined recommendation, instead of the
user working through the flat findings list one row at a time.

Draft/Accept style (REQ-L2-AI-001): nothing is persisted here. A package is
advisory text plus a set of finding references; applying an individual
finding's fix still goes through the existing ``AuditService.remediate()``
Adopt-Workflow (Phase 3).

Referential-integrity guarantee (acceptance criterion, §4 Phase 4b:
"N8: Refactoring-Pakete referenzieren reale, existierende Findings-IDs aus
Phase-3-Dashboard"): a package's ``finding_refs`` are never taken verbatim
from the LLM response. The provider (mock or real) only ever proposes
*indices* into the finding list this service handed it as prompt context;
every index is resolved back against the *actual*
``AuditReport.findings`` from the current audit run before it is returned
to the caller. An index the provider hallucinates (out of range, wrong
type, duplicate) is silently dropped rather than surfaced as a fake finding
reference — so a generated package can only ever point at findings that
genuinely exist in the Phase-3 dashboard for this run.

Architecture: Layer-2 facade (ADR-01) wrapping ``AuditService`` (Phase 3) +
``llm_adapter.providers`` (mock default, graceful degradation on provider
failure — mirrors ``ArchitectureDecomposeService._complete_tree``, the N1
precedent for LLM-completion-with-mock-fallback in this layer).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.audit_service import AuditFindingView, AuditService
from application.base import ServiceBase
from traceability.audit import AuditScope

logger = logging.getLogger(__name__)

# Prompt template for the llm_adapter capability purpose ``audit_ai_review``.
# Kept as a module constant rather than a per-tenant PromptTemplate slot,
# mirroring the N1 precedent (ARCH_DECOMPOSE_PROMPT_TEMPLATE in
# architecture_decompose_service.py): the mock provider ignores the prose and
# groups deterministically from the structured ``context["findings"]`` list.
AI_REVIEW_PROMPT_TEMPLATE = (
    "You are a systems-engineering auditor assistant. Below is a JSON array "
    "of audit findings for this workspace, each with an 'index', 'rule_id', "
    "'severity', 'artifact_ids' and 'scope'. Group related findings into "
    "strategic refactoring packages (e.g. all findings for the same rule "
    "and subsystem belong in one package with a combined recommendation). "
    "Respond with a JSON array of objects, each with a 'title' (short "
    "package name), a 'rationale' (why these findings belong together and "
    "what to do about them), and a 'finding_indices' array (the 'index' "
    "values — and ONLY the 'index' values — of the findings this package "
    "covers, taken from the list below; never invent an index that is not "
    "in the list).\n\nFindings:\n{findings_json}"
)


# Prompt purpose name — must stay in the workspace-wide set of
# ``llm_adapter.timeouts.WORKSPACE_WIDE_PURPOSES`` (issue #342).
_AI_REVIEW_PURPOSE = "audit_ai_review"


class AiReviewResponseError(RuntimeError):
    """Raised when the LLM call fails or returns unparseable content.

    Sibling of ``application.ai_derivation_service.LlmResponseError``: the
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
class RefactoringPackage:
    """One strategic refactoring package: a title/rationale plus its findings.

    ``finding_refs`` entries are always resolved from the real audit report
    (never copied verbatim from the LLM) — see the module docstring's
    referential-integrity guarantee.
    """

    title: str
    rationale: str
    finding_refs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "rationale": self.rationale,
            "finding_refs": self.finding_refs,
        }


@dataclass
class AiReviewResult:
    """Full N8 run: tier/provider metadata plus the generated packages."""

    tier: str
    provider: str
    degraded: bool
    total_findings: int = 0
    packages: List[RefactoringPackage] = field(default_factory=list)

    def to_dict(self) -> dict:
        packaged = sum(len(p.finding_refs) for p in self.packages)
        return {
            "tier": self.tier,
            "provider": self.provider,
            "degraded": self.degraded,
            "packages": [p.to_dict() for p in self.packages],
            "counts": {
                "total_findings": self.total_findings,
                "packaged_findings": packaged,
                "packages": len(self.packages),
            },
        }


class AiReviewService(ServiceBase):
    """Single-Entry-Point facade for the N8 ``audit.ai_review`` copilot."""

    def __init__(self, audit_service: Optional[AuditService] = None) -> None:
        self._audit = audit_service or AuditService()

    def review(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        tier: Optional[str] = None,
        scopes: Optional[Sequence[AuditScope]] = None,
    ) -> AiReviewResult:
        """Run the SE-Auditor and bundle its findings into refactoring packages.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Authenticated, tenant-scoped context.
            tier: Rigor tier override, forwarded to ``AuditService.run_audit``
                (defaults to the workspace's active preset).
            scopes: Baseline scopes, forwarded to ``AuditService.run_audit``.

        Returns:
            :class:`AiReviewResult` — zero packages (not an error) when the
            audit run itself has zero findings.

        Raises:
            NotFoundError: The workspace does not exist for this tenant.
            AiReviewResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        report = self._audit.run_audit(workspace_id, ctx, tier=tier, scopes=scopes)
        findings = report.findings

        if not findings:
            return AiReviewResult(
                tier=report.tier, provider="mock", degraded=False, total_findings=0
            )

        findings_payload = [self._finding_payload(fv) for fv in findings]

        raw, provider_name, degraded = self._complete(findings_payload)
        proposed = self._parse_packages(raw)

        by_index: Dict[int, AuditFindingView] = {fv.index: fv for fv in findings}
        packages = self._build_packages(proposed, by_index)

        return AiReviewResult(
            tier=report.tier,
            provider=provider_name,
            degraded=degraded,
            total_findings=len(findings),
            packages=packages,
        )

    # ------------------------------------------------------------------
    # Internal — package construction (the referential-integrity gate)
    # ------------------------------------------------------------------

    @staticmethod
    def _finding_payload(fv: AuditFindingView) -> Dict[str, Any]:
        """Render one finding as the compact dict handed to the LLM as context."""
        return {
            "index": fv.index,
            "rule_id": fv.finding.rule_id,
            "severity": fv.finding.severity.value,
            "artifact_ids": list(fv.finding.artifact_ids),
            "scope": fv.finding.scope,
            "scope_artifact_id": fv.finding.scope_artifact_id,
        }

    def _build_packages(
        self,
        proposed: list,
        by_index: Dict[int, AuditFindingView],
    ) -> List[RefactoringPackage]:
        """Resolve the LLM's proposed packages against the real findings.

        Every ``finding_indices`` entry is looked up in *by_index* (built
        from the actual :class:`AuditReport`, not from the LLM output). An
        index that does not resolve — out of range, wrong type, or a repeat
        within the same package — is dropped. A package left with zero valid
        references after filtering is dropped entirely rather than returned
        as an empty, non-actionable shell.
        """
        packages: List[RefactoringPackage] = []
        for item in proposed:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            raw_indices = item.get("finding_indices")
            if not isinstance(raw_indices, list):
                continue

            refs, seen = [], set()
            for raw_idx in raw_indices:
                idx = self._coerce_index(raw_idx)
                if idx is None or idx in seen or idx not in by_index:
                    continue
                seen.add(idx)
                refs.append(self._finding_payload(by_index[idx]))

            if not refs:
                continue
            packages.append(
                RefactoringPackage(
                    title=title,
                    rationale=str(item.get("rationale", "")),
                    finding_refs=refs,
                )
            )
        return packages

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
    # Internal — LLM plumbing (mirrors ArchitectureDecomposeService._complete_tree)
    # ------------------------------------------------------------------

    def _complete(
        self, findings_payload: List[Dict[str, Any]]
    ) -> Tuple[str, str, bool]:
        """Call the LLM provider for a package grouping (graceful degradation).

        Returns ``(raw_completion, provider_name, degraded)``. On any
        provider configuration error it degrades to the credential-free
        deterministic mock so the review flow never crashes (REQ-L2-AI-002;
        default provider is ``mock``).

        Issue #342: the prompt spans every finding in the workspace, so the
        call runs under the workspace-wide timeout resolved by
        :func:`llm_adapter.timeouts.resolve_timeout_seconds` instead of the
        provider's 30s config default. Transport failures (timeout, open
        circuit breaker) are mapped to :class:`AiReviewResponseError` rather
        than escaping as an unhandled ``LlmTransportError``.

        Raises:
            AiReviewResponseError: The provider call failed outright.
        """
        from django.conf import settings

        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )
        from llm_adapter.timeouts import resolve_timeout_seconds

        prompt = AI_REVIEW_PROMPT_TEMPLATE.format(
            findings_json=json.dumps(findings_payload)
        )
        context = {"findings": findings_payload}
        provider_name = getattr(settings, "LLM_PROVIDER", "mock")
        degraded = False
        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            logger.warning(
                "audit.ai_review: provider %s unavailable, using mock. %s",
                provider_name,
                error,
            )
            provider = MockLlmProvider()
            provider_name = "mock"
            degraded = True

        timeout = resolve_timeout_seconds(_AI_REVIEW_PURPOSE)
        try:
            raw = provider.complete(
                prompt,
                purpose=_AI_REVIEW_PURPOSE,
                context=context,
                timeout=timeout,
            )
        except Exception as error:  # noqa: BLE001 — see class docstring (#342)
            logger.warning(
                "audit.ai_review: provider %s call failed (timeout=%ss): %s",
                provider_name,
                timeout,
                error,
            )
            raise AiReviewResponseError(
                f"The LLM provider '{provider_name}' did not answer the "
                f"ai_review request within {timeout:.0f}s ({error}). "
                "Narrow the request (scope=document) or raise "
                "LLM_LONG_RUNNING_TIMEOUT."
            ) from error
        return raw, provider_name, degraded

    @staticmethod
    def _parse_packages(raw: str) -> list:
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
            raise AiReviewResponseError(
                "The LLM ai_review response was not valid JSON."
            ) from exc
        if not isinstance(parsed, list):
            raise AiReviewResponseError(
                "The LLM ai_review response was not a JSON array as expected."
            )
        return parsed


__all__ = [
    "AiReviewService",
    "AiReviewResult",
    "RefactoringPackage",
    "AiReviewResponseError",
    "AI_REVIEW_PROMPT_TEMPLATE",
]
