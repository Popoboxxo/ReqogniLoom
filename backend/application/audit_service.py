"""
COMP-AS-AUDIT AuditService — Single-Entry-Point facade for the SE-Auditor.

leaf_id : COMP-AS-AUDIT
UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3 ("Auditor UI").

ADR-01 (Single Entry Point): the REST/MCP layer never talks to the RuleEngine
or the remediation registry directly — it goes through this Layer-2 facade,
exactly like ``BaselineFacade`` wraps ``baseline.services``. Responsibilities:

  1. run_audit(...)          — resolve the workspace's rigor tier (from the
                               preset, the acceptance criterion "filtered by the
                               workspace's active rigor preset") and run the
                               RuleEngine, returning findings + per-finding
                               remediation proposals for the dashboard.
  2. propose_remediation(...) — analyse a single finding (read-only) and return
                               its RemediationProposal (automatic or manual).
  3. remediate(...)          — apply an automatic proposal through the existing
                               validated domain services (TraceLinkService), then
                               re-audit to prove the finding is gone (the Phase 3
                               negative -> positive acceptance test).

The analysis half (which correction a finding maps to, and whether it is
unambiguous) lives in ``traceability.audit.remediation`` (Layer 1, read-only).
This service owns only the *execution* half: it translates a
:class:`RemediationProposal` into a concrete service call. Mutating a graph is
never done inside a remediation object — it happens here, through the single
entry point, so audit + tenant scoping + SE-semantics validation all apply.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.base import ServiceBase, ValidationError
from traceability.audit import (
    AuditScope,
    Finding,
    RemediationActionKind,
    RemediationProposal,
    RuleEngine,
    Severity,
    get_remediation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result DTOs (JSON-serialisable — the REST layer only calls to_dict()).
# ---------------------------------------------------------------------------


@dataclass
class AuditFindingView:
    """A finding plus its remediation proposal, ready for the dashboard.

    ``index`` is a stable position within a single audit run so the frontend
    can key rows and correlate an Adopt click back to a finding without the
    findings being persisted.
    """

    index: int
    finding: Finding
    remediation: RemediationProposal

    def to_dict(self) -> dict:
        data = self.finding.to_dict()
        data["index"] = self.index
        data["remediation"] = self.remediation.to_dict()
        return data


@dataclass
class AuditReport:
    """Full audit run for the API: tier, findings-with-remediation, counts."""

    tier: str
    scope: Optional[str]
    scope_artifact_id: Optional[str]
    findings: List[AuditFindingView] = field(default_factory=list)

    def to_dict(self) -> dict:
        blockers = sum(
            1 for fv in self.findings if fv.finding.severity is Severity.BLOCKER
        )
        warnings = sum(
            1 for fv in self.findings if fv.finding.severity is Severity.WARNING
        )
        return {
            "tier": self.tier,
            "scope": self.scope,
            "scope_artifact_id": self.scope_artifact_id,
            "counts": {
                "total": len(self.findings),
                "blockers": blockers,
                "warnings": warnings,
            },
            "findings": [fv.to_dict() for fv in self.findings],
        }


@dataclass
class RemediationResult:
    """Outcome of a remediate() call."""

    applied: bool
    proposal: RemediationProposal
    finding_resolved: Optional[bool] = None
    created_link_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
            "finding_resolved": self.finding_resolved,
            "created_link_id": self.created_link_id,
            "proposal": self.proposal.to_dict(),
        }


class AuditService(ServiceBase):
    """Single-Entry-Point facade over the SE-Auditor RuleEngine (Phase 3)."""

    def __init__(self, engine: Optional[RuleEngine] = None) -> None:
        # The RuleEngine is stateless; a single shared instance is fine, but an
        # override keeps the service test-injectable.
        self._engine = engine or RuleEngine()

    # ---------- Tier resolution ----------

    @staticmethod
    def resolve_tier(workspace_id: str | UUID) -> str:
        """Return the workspace's active rigor tier (minimal|standard|extended).

        Delegates to ``presets.services.get_preset`` — the SSOT for a
        workspace's active preset. Falls back to ``"standard"`` if the preset
        cannot be resolved (never ``"minimal"``: a lookup glitch must not
        silently disable auditing), mirroring the RuleEngine's own fallback.
        """
        try:
            from presets.services import get_preset

            return get_preset(str(workspace_id)).preset
        except Exception:
            logger.exception(
                "AuditService: preset lookup failed for ws=%s; "
                "falling back to 'standard'",
                workspace_id,
            )
            return "standard"

    # ---------- Audit run ----------

    def run_audit(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        tier: Optional[str] = None,
        scopes: Optional[Sequence[AuditScope]] = None,
    ) -> AuditReport:
        """Run the SE-Auditor for *workspace_id* and return findings + proposals.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext (tenant scoping + downstream service calls).
            tier: Rigor tier override. When ``None`` (the API default) it is
                resolved from the workspace preset (acceptance criterion:
                findings are filtered by the workspace's active rigor preset).
            scopes: Baseline scopes for scope-aware rules. Defaults to the
                workspace-wide ``project`` scope inside the RuleEngine.

        Returns:
            :class:`AuditReport` with a remediation proposal attached to every
            finding.
        """
        self._set_tenant_context(ctx)
        resolved_tier = tier or self.resolve_tier(workspace_id)
        ws_id = str(workspace_id)
        tenant_id = str(ctx.tenant_id)

        result = self._engine.run(
            tier=resolved_tier,
            workspace_id=ws_id,
            tenant_id=tenant_id,
            scopes=scopes,
        )

        primary_scope = scopes[0] if scopes else None
        report = AuditReport(
            tier=result.tier,
            scope=primary_scope.scope if primary_scope else None,
            scope_artifact_id=(
                primary_scope.artifact_id if primary_scope else None
            ),
        )
        for index, finding in enumerate(result.findings):
            proposal = self._propose_for_finding(finding, tenant_id, ws_id)
            report.findings.append(
                AuditFindingView(index=index, finding=finding, remediation=proposal)
            )
        return report

    # ---------- Remediation analysis ----------

    def propose_remediation(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        rule_id: str,
        artifact_ids: Sequence[str],
        scope: Optional[str] = None,
        scope_artifact_id: Optional[str] = None,
    ) -> RemediationProposal:
        """Return the remediation proposal for one finding (read-only)."""
        self._set_tenant_context(ctx)
        finding = self._build_finding(
            rule_id=rule_id,
            artifact_ids=artifact_ids,
            scope=scope,
            scope_artifact_id=scope_artifact_id,
        )
        return self._propose_for_finding(
            finding, str(ctx.tenant_id), str(workspace_id)
        )

    def _propose_for_finding(
        self, finding: Finding, tenant_id: str, workspace_id: str
    ) -> RemediationProposal:
        """Analyse *finding*, falling back to a manual proposal when no
        remediation is registered for its rule (every rule stays crash-free)."""
        remediation = get_remediation(finding.rule_id)
        if remediation is None:
            return RemediationProposal.manual(
                finding.rule_id,
                f"No automatic remediation is available for {finding.rule_id}; "
                "this finding requires a manual correction (Modify).",
                finding.artifact_ids,
            )
        try:
            return remediation.propose(
                finding, tenant_id=tenant_id, workspace_id=workspace_id
            )
        except Exception:
            logger.exception(
                "AuditService: remediation.propose failed for rule=%s",
                finding.rule_id,
            )
            return RemediationProposal.manual(
                finding.rule_id,
                "Automatic remediation analysis failed; apply a manual "
                "correction (Modify).",
                finding.artifact_ids,
            )

    # ---------- Remediation execution (Adopt) ----------

    def remediate(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        rule_id: str,
        artifact_ids: Sequence[str],
        scope: Optional[str] = None,
        scope_artifact_id: Optional[str] = None,
        verify: bool = True,
    ) -> RemediationResult:
        """Apply the automatic remediation for one finding (Adopt-Workflow).

        Re-derives the proposal from *current* graph state (so a stale request
        or already-fixed data is handled gracefully), and, if the proposal is
        automatic, executes it through the existing validated domain services.
        With ``verify`` (the default) it re-runs the audit afterwards and
        reports whether the originating finding is gone — the Phase 3
        negative -> positive acceptance guarantee.

        Raises:
            PermissionDeniedError: Caller lacks write permission.
            ValidationError: The finding has no automatic remediation, or the
                downstream service rejected the correction.
            NotFoundError: A referenced artifact does not exist.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        ws_id = str(workspace_id)
        tenant_id = str(ctx.tenant_id)
        finding = self._build_finding(
            rule_id=rule_id,
            artifact_ids=artifact_ids,
            scope=scope,
            scope_artifact_id=scope_artifact_id,
        )
        proposal = self._propose_for_finding(finding, tenant_id, ws_id)

        if not proposal.automatic:
            # Not a crash: a clear, structured refusal the UI turns into a
            # "Modify" prompt. Surfaced as ValidationError -> HTTP 422.
            raise ValidationError(proposal.reason)

        created_link_id = self._execute_action(proposal, ctx)

        finding_resolved: Optional[bool] = None
        if verify:
            still_present = self._finding_still_present(
                finding,
                ws_id,
                ctx,
                scope=scope,
                scope_artifact_id=scope_artifact_id,
            )
            finding_resolved = not still_present

        return RemediationResult(
            applied=True,
            proposal=proposal,
            finding_resolved=finding_resolved,
            created_link_id=created_link_id,
        )

    # ---------- Action executor (the only place proposals become mutations) --

    def _execute_action(
        self, proposal: RemediationProposal, ctx: AuthContext
    ) -> Optional[str]:
        """Dispatch an automatic proposal to the matching domain service.

        Exhaustive over :class:`RemediationActionKind`; an unknown kind is a
        programming error (a new kind was added without an executor branch).
        """
        if proposal.action_kind == RemediationActionKind.CREATE_TRACE_LINK.value:
            return self._create_trace_link(proposal, ctx)
        raise ValidationError(
            f"Unsupported remediation action kind: {proposal.action_kind!r}"
        )

    @staticmethod
    def _create_trace_link(
        proposal: RemediationProposal, ctx: AuthContext
    ) -> Optional[str]:
        """Create the proposed TraceLink via the TraceLinkService (ADR-01).

        The endpoints in the proposal are Artifact ids (every TraceLink
        endpoint is an Artifact id); ``TraceLinkService.create_trace_link``
        resolves and validates them (existence, cross-workspace, SE endpoint
        semantics) and writes an audit entry.
        """
        from application.trace_link_service import TraceLinkService

        params = proposal.params
        link = TraceLinkService().create_trace_link(
            source_id=UUID(params["source_id"]),
            target_id=UUID(params["target_id"]),
            link_type=params["link_type"],
            ctx=ctx,
        )
        return str(getattr(link, "id", "")) or None

    # ---------- Helpers ----------

    def _finding_still_present(
        self,
        finding: Finding,
        workspace_id: str,
        ctx: AuthContext,
        *,
        scope: Optional[str],
        scope_artifact_id: Optional[str],
    ) -> bool:
        """Re-run the audit and report whether *finding* is still raised.

        A finding is considered "the same" when its rule id and artifact-id set
        match — the natural identity for a non-persisted finding.
        """
        scopes = (
            [AuditScope(scope, artifact_id=scope_artifact_id)]
            if scope is not None
            else None
        )
        report = self.run_audit(workspace_id, ctx, scopes=scopes)
        target_ids = frozenset(finding.artifact_ids)
        for fv in report.findings:
            current = fv.finding
            if current.rule_id != finding.rule_id:
                continue
            if frozenset(current.artifact_ids) == target_ids:
                return True
        return False

    @staticmethod
    def _build_finding(
        *,
        rule_id: str,
        artifact_ids: Sequence[str],
        scope: Optional[str],
        scope_artifact_id: Optional[str],
    ) -> Finding:
        """Reconstruct a minimal Finding from a remediate/propose request.

        Only ``rule_id`` + ``artifact_ids`` (+ scope) are load-bearing for
        remediation; severity/message are placeholders (the remediation logic
        never reads them).
        """
        return Finding(
            rule_id=rule_id,
            severity=Severity.WARNING,
            message="",
            artifact_ids=tuple(str(a) for a in artifact_ids),
            scope=scope,
            scope_artifact_id=scope_artifact_id,
        )


__all__ = [
    "AuditService",
    "AuditReport",
    "AuditFindingView",
    "RemediationResult",
]
