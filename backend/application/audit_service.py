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
from datetime import datetime
from typing import List, Optional, Sequence
from uuid import UUID

from django.utils import timezone

from auth_tenancy.context import AuthContext

from application.base import (
    PermissionDeniedError,
    ServiceBase,
    SuppressionExpiredError,
    ValidationError,
    WaiverFindingNotBlockingError,
    WaiverReasonPolicyViolation,
)
from baseline.exceptions import GovernanceAuthorityError, GovernanceReasonError
from baseline.waivers import (
    BlockerWaiverRequest,
    SuppressionRecord,
    assert_gate_waiver_authority,
    canonical_artifact_ids,
    finding_key,
    load_suppressions,
    record_waiver,
    suppression_applies,
    validate_waiver_reason,
)
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

#: Baseline scopes a suppression request may name for its existence check
#: (#569/C1). ``scope=None`` (the default) keeps the RuleEngine's project
#: default; naming a scope selects it for the engine run only — the persisted
#: scope still comes from the matched finding.
_ALLOWED_SUPPRESSION_SCOPES = frozenset({"document", "project", "global"})


# ---------------------------------------------------------------------------
# Result DTOs (JSON-serialisable — the REST layer only calls to_dict()).
# ---------------------------------------------------------------------------


@dataclass
class AuditFindingView:
    """A finding plus its remediation proposal, ready for the dashboard.

    ``index`` is a stable position within a single audit run so the frontend
    can key rows and correlate an Adopt click back to a finding without the
    findings being persisted.

    ``finding_key`` (issue #1021) is the finding's *run-independent* identity:
    ``baseline.waivers.finding_key`` rendered over the rule id, the sorted
    artifact ids and the finding's scope — the same function that decides which
    ``BaselineGateWaiver`` row (GH-821) a finding matches, so a waiver, a
    remediation request and a re-audit all agree on what "the same finding"
    means. ``index`` cannot serve that purpose: it is a position in one run's
    finding list and shifts as soon as any other finding appears or disappears.
    """

    index: int
    finding: Finding
    remediation: RemediationProposal
    #: #569: whether an active suppression covers this finding. Additive with
    #: defaults, so every pre-#569 construction keeps working. A suppressed
    #: finding is *not hidden* — it stays in ``findings`` and is marked
    #: (``include_suppressed`` default ``True``, O3).
    suppressed: bool = False
    #: Expiry of the matching suppression (``None`` = unbounded), if any.
    suppressed_until: Optional[datetime] = None
    #: Justification of the matching suppression, if any.
    suppression_reason: Optional[str] = None
    #: Id of the matching ``BaselineGateWaiver`` row, if any.
    suppression_id: Optional[UUID] = None

    @property
    def finding_key(self) -> str:
        """Canonical, run-independent identity of the wrapped finding."""
        return finding_key(
            self.finding.rule_id, self.finding.artifact_ids, self.finding.scope
        )

    def to_dict(self) -> dict:
        data = self.finding.to_dict()
        data["index"] = self.index
        data["finding_key"] = self.finding_key
        data["suppressed"] = self.suppressed
        data["suppressed_until"] = (
            self.suppressed_until.isoformat() if self.suppressed_until else None
        )
        data["suppression_reason"] = self.suppression_reason
        data["suppression_id"] = (
            str(self.suppression_id) if self.suppression_id else None
        )
        data["remediation"] = self.remediation.to_dict()
        return data


@dataclass
class SuppressionView:
    """API view of one persisted suppression (#569).

    ``finding_key`` is the *persisted*, scope-less key (GH-821); ``identity_key``
    is the display/correlation rendering that includes the scope
    (``finding_key(rule_id, artifact_ids, scope)``). ``state`` is derived at
    read time (``"active"|"expired"``) — there is no persisted state column.

    Built by :class:`AuditService`; the REST/MCP layer only calls
    :meth:`to_dict`.
    """

    waiver_id: UUID
    finding_key: str
    identity_key: str
    rule_id: str
    artifact_ids: tuple[str, ...]
    scope: str
    scope_artifact_id: str
    reason: str
    granted_by: str
    created_at: datetime
    expires_at: Optional[datetime]
    state: str

    def to_dict(self) -> dict:
        return {
            "waiver_id": str(self.waiver_id),
            "finding_key": self.finding_key,
            "identity_key": self.identity_key,
            "rule_id": self.rule_id,
            "artifact_ids": list(self.artifact_ids),
            "scope": self.scope,
            "scope_artifact_id": self.scope_artifact_id,
            "reason": self.reason,
            "granted_by": self.granted_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "state": self.state,
        }

    @classmethod
    def from_record(
        cls, record: SuppressionRecord, *, state: str
    ) -> "SuppressionView":
        """Build a view from a loaded :class:`SuppressionRecord`."""
        return cls(
            waiver_id=record.id,
            finding_key=record.finding_key,
            identity_key=finding_key(
                record.rule_id, record.artifact_ids, record.scope or None
            ),
            rule_id=record.rule_id,
            artifact_ids=record.artifact_ids,
            scope=record.scope,
            scope_artifact_id=record.scope_artifact_id,
            reason=record.reason,
            granted_by=record.granted_by,
            created_at=record.created_at,
            expires_at=record.expires_at,
            state=state,
        )


@dataclass
class AuditReport:
    """Full audit run for the API: tier, findings-with-remediation, counts.

    ``truncated`` / ``total_findings_available`` / ``total_blockers_available``
    / ``total_warnings_available`` (BUG-15, SYSTEMAUDIT_2026-08-18 §4/§8): a
    workspace with many untraced artifacts can produce a four-figure finding
    count (4,440 in the audit's 300-requirement stress scenario) — returning
    all of them in one response risks multi-MB payloads.
    ``AuditService.run_audit`` caps the *returned* findings at
    :data:`AuditService.MAX_REPORT_FINDINGS`; these fields tell the caller a
    cap was applied and how many findings/blockers/warnings exist in total,
    without changing the meaning of any pre-existing field (``counts.total``
    /``counts.blockers``/``counts.warnings`` still describe the *returned*
    (possibly capped) findings — additive-only change, see
    AuditService.run_audit docstring for the compatibility rationale).

    Code review finding (BUG-15 follow-up M3): the dashboard's count badges
    used to be computed client-side from the (possibly capped) findings
    array, so a workspace with 4,440 real blockers showed "500" with no
    indication that was a partial count. ``total_blockers_available`` /
    ``total_warnings_available`` give the frontend the true totals to show
    instead, while ``counts.blockers``/``counts.warnings`` keep describing
    what is actually in ``findings`` (e.g. for the Adopt-workflow's live,
    shrink-on-resolve badge behaviour when the run was not truncated).
    """

    tier: str
    scope: Optional[str]
    scope_artifact_id: Optional[str]
    findings: List[AuditFindingView] = field(default_factory=list)
    truncated: bool = False
    total_findings_available: int = 0
    total_blockers_available: int = 0
    total_warnings_available: int = 0
    #: #622: starting position of `findings` within the full run. 0 for every
    #: pre-#622 caller (default `run_audit(limit=None)`); only meaningful
    #: together with `truncated` when a caller passed an explicit `limit`,
    #: to compute the next window's offset (`offset + len(findings)`).
    offset: int = 0
    #: #569: whether the returned window still contains suppressed findings
    #: (O3 default ``True`` — nothing is hidden by default).
    include_suppressed: bool = True
    #: #569: number of suppressed findings in the full, uncapped run (additive;
    #: ``counts.*`` stays descriptive of the returned window, M5).
    total_suppressed_available: int = 0
    #: #569: of :attr:`total_suppressed_available`, the BLOCKER-severity ones.
    total_suppressed_blockers_available: int = 0
    #: #569: how many findings the ``include_suppressed=False`` filter removed
    #: from the returned ``findings`` (0 when the filter is off). Explains the
    #: ``counts.total`` vs ``total_findings_available`` difference (m7).
    suppressed_filtered: int = 0

    def to_dict(self) -> dict:
        # All three descriptive counters come from the *same* ``self.findings``
        # list, and ``Severity`` has exactly two members (BLOCKER/WARNING), so
        # ``blockers + warnings == total`` is an unconditional identity — never
        # assert an intra-counts inequality (#569/R3-01).
        blockers = sum(
            1 for fv in self.findings if fv.finding.severity is Severity.BLOCKER
        )
        warnings = sum(
            1 for fv in self.findings if fv.finding.severity is Severity.WARNING
        )
        suppressed = sum(1 for fv in self.findings if fv.suppressed)
        suppressed_blockers = sum(
            1
            for fv in self.findings
            if fv.suppressed and fv.finding.severity is Severity.BLOCKER
        )
        return {
            "tier": self.tier,
            "scope": self.scope,
            "scope_artifact_id": self.scope_artifact_id,
            "counts": {
                "total": len(self.findings),
                "blockers": blockers,
                "warnings": warnings,
                # #569, additive: counts.* stays descriptive of `findings` (M5).
                "suppressed": suppressed,
                "suppressed_blockers": suppressed_blockers,
            },
            "truncated": self.truncated,
            "total_findings_available": self.total_findings_available,
            "total_blockers_available": self.total_blockers_available,
            "total_warnings_available": self.total_warnings_available,
            # #569, additive: absolute (pre-cap, pre-filter) suppression totals.
            "total_suppressed_available": self.total_suppressed_available,
            "total_suppressed_blockers_available": (
                self.total_suppressed_blockers_available
            ),
            "suppressed_filtered": self.suppressed_filtered,
            "offset": self.offset,
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

    #: Hard cap on findings returned by a single run_audit() call (BUG-15,
    #: SYSTEMAUDIT_2026-08-18 §4/§8). A workspace with many untraced
    #: artifacts can produce a four-figure finding count (4,440 findings /
    #: ~2.5 MB in the audit's 300-requirement stress scenario) — this bounds
    #: both the JSON payload and the per-finding remediation-analysis cost
    #: (one extra query pass per finding, see blocking_findings' docstring).
    #:
    #: Deliberately NOT DRF PageNumberPagination: the REST/MCP consumers of
    #: this report (AuditDashboard.tsx, audit.ai_review) both need the *whole*
    #: result set at once to group findings by rule id and compute live
    #: blocker/warning counts — a page-based envelope would fragment rule
    #: groups across pages and break that UX, and would be a breaking
    #: response-shape change for every existing consumer (count/next/
    #: previous/results wrapper instead of a bare "findings" list). A
    #: truncation cap keeps the existing shape (additive-only fields, see
    #: AuditReport) while still bounding worst-case payload size; 500
    #: findings is ~280 KB at the audit's observed ~560 bytes/finding
    #: average, which is workable for both a browser render and an LLM
    #: prompt context (audit.ai_review).
    MAX_REPORT_FINDINGS: int = 500

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

    # ---------- Gate support (SE-conformance lever 2) ----------

    def _run_engine_uncapped(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        tier: Optional[str] = None,
        scopes: Optional[Sequence[AuditScope]] = None,
    ):
        """Run the RuleEngine directly and return the raw, uncapped result.

        Shared by :meth:`blocking_findings` (gate decisions) and
        :meth:`_finding_still_present` (Adopt re-verification) — both need a
        definitive answer over the *complete* finding set, never the
        :data:`MAX_REPORT_FINDINGS`-capped view :meth:`run_audit` returns for
        the dashboard (BUG-15 follow-up H1: verifying "is this finding still
        present?" against a truncated report can silently report a finding
        as resolved when it still exists but fell outside the cap — exactly
        the >500-finding workspaces BUG-15 is about). Also skips remediation
        analysis (:meth:`_propose_for_finding`), which neither caller needs.
        """
        self._set_tenant_context(ctx)
        return self._engine.run(
            tier=tier or self.resolve_tier(workspace_id),
            workspace_id=str(workspace_id),
            tenant_id=str(ctx.tenant_id),
            scopes=scopes,
        )

    def blocking_findings(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        tier: Optional[str] = None,
        scopes: Optional[Sequence[AuditScope]] = None,
    ) -> List[Finding]:
        """Return only the BLOCKER-severity findings for *workspace_id*.

        The gate counterpart of :meth:`run_audit`: same RuleEngine, same
        tier resolution, but no remediation analysis. Remediation proposals
        cost one extra analysis pass (and several queries) per finding and are
        only meaningful for the dashboard — a caller that just needs a
        yes/no decision (e.g. :meth:`application.baseline_facade.BaselineFacade
        .create_baseline`) must not pay for them.

        Tier awareness is inherited unchanged from the RuleEngine: the Minimal
        tier maps to an empty rule set in
        ``traceability.audit.registry.RULE_PRESET_MAP`` (structurally enforced),
        so this returns ``[]`` without issuing a single query there.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext (tenant scoping).
            tier: Rigor tier override; resolved from the preset when ``None``.
            scopes: Baseline scopes for scope-aware rules.

        Returns:
            All findings whose tier-resolved severity is
            :attr:`Severity.BLOCKER`, in rule/scope order.
        """
        result = self._run_engine_uncapped(
            workspace_id, ctx, tier=tier, scopes=scopes
        )
        return [f for f in result.findings if f.severity is Severity.BLOCKER]

    # ---------- Suppression surface (#569) ----------

    def suppress_finding(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        rule_id: str,
        artifact_ids: Sequence[str],
        scope: Optional[str] = None,
        scope_artifact_id: Optional[str] = None,
        reason: str,
        expires_at: Optional[datetime] = None,
    ) -> tuple[SuppressionView, bool]:
        """Persist a per-finding suppression and return ``(view, created)``.

        The standalone Auditor counterpart of the gate's ``waived_findings``
        (GH-821): the same ``BaselineGateWaiver`` row, but reachable without a
        baseline build, with an optional expiry and its own audit entry. It does
        not remove the finding from the world — it takes away its blocker effect
        and keeps the decision (who, what, why, until when) visible.

        Steps (#569 §3.3):

        1. authority — the shared SSOT choke point
           :func:`baseline.waivers.assert_gate_waiver_authority`
           (Admin/Approver *and*, for API keys, the ADMIN tier, #865), remapped
           to ``PermissionDeniedError`` (403).
        2. author — ``granted_by`` comes only from ``AuthContext`` (never the
           request body); an unresolvable author is refused (403).
        3. reason — the shared policy
           :func:`baseline.waivers.validate_waiver_reason`, remapped to
           ``WaiverReasonPolicyViolation`` (400 ``WAIVER_REASON_REJECTED``).
        4. ``expires_at`` guard (D2/E3): naive or already-past timestamps are
           refused (400 ``VALIDATION_ERROR``) before anything is persisted —
           this precedence also wins over the m1 409 below (R3-07).
        5. existence check (C1) against the **uncapped** run over the requested
           scope (``None`` keeps the engine's ``project`` default);
           ``scope="document"`` requires ``scope_artifact_id``.
        6. blocker-only (O2): only ``Severity.BLOCKER`` findings are matchable.
        7. the persisted ``scope``/``scope_artifact_id`` come from the matched
           finding, never the client (a scope-agnostic finding yields ``""``).
        8. persist via ``record_waiver``; if only an **expired** row exists for
           the key, raise ``SuppressionExpiredError`` (409) instead of a silent
           200 no-op (m1). A newly created row gets exactly one
           ``baseline.waiver_create`` audit entry.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext (tenant scoping + author).
            rule_id: SE-Auditor rule id being suppressed.
            artifact_ids: Artifacts the finding concerns.
            scope: Optional baseline scope used *only* for the engine run
                (``document`` | ``project`` | ``global``).
            scope_artifact_id: Document root; required when ``scope="document"``.
            reason: Mandatory written justification.
            expires_at: Optional expiry; ``None`` = unbounded.

        Returns:
            ``(SuppressionView, created)`` — ``created`` is ``False`` when an
            identical active suppression was already on file (idempotent).

        Raises:
            PermissionDeniedError: No approval authority, or an unresolvable
                author (403).
            WaiverReasonPolicyViolation: Justification fails the policy (400).
            ValidationError: Invalid scope, missing document root, or a naive /
                already-past ``expires_at`` (400).
            WaiverFindingNotBlockingError: No matching BLOCKER finding (400).
            SuppressionExpiredError: Only an expired row exists for the key
                (409).
        """
        self._set_tenant_context(ctx)

        try:
            assert_gate_waiver_authority(ctx)
        except GovernanceAuthorityError as exc:
            raise PermissionDeniedError(str(exc)) from exc

        granted_by = str(getattr(ctx, "user_id", "") or "").strip()
        if not granted_by:
            raise PermissionDeniedError(
                "Permission denied: a suppression has to name its author, and "
                "the authenticated context carries no resolvable user id."
            )

        try:
            cleaned_reason = validate_waiver_reason(
                reason, label="suppression justification"
            )
        except GovernanceReasonError as exc:
            raise WaiverReasonPolicyViolation(str(exc)) from exc

        decision_now = timezone.now()
        if expires_at is not None:
            if timezone.is_naive(expires_at):
                raise ValidationError(
                    "The suppression expiry must be a timezone-aware timestamp "
                    "(ISO-8601 with an offset or 'Z')."
                )
            if expires_at <= decision_now:
                raise ValidationError(
                    "The suppression expiry must be in the future; a waiver "
                    "that is already expired would never suppress anything."
                )

        normalized_scope = str(scope).strip() if scope is not None else None
        if normalized_scope and normalized_scope not in _ALLOWED_SUPPRESSION_SCOPES:
            raise ValidationError(
                f"Unknown baseline scope {normalized_scope!r}; expected one of "
                f"{sorted(_ALLOWED_SUPPRESSION_SCOPES)}."
            )
        normalized_scope_artifact = (
            str(scope_artifact_id).strip() if scope_artifact_id is not None else None
        )
        if normalized_scope == "document" and not normalized_scope_artifact:
            raise ValidationError(
                "scope_artifact_id is required when scope is 'document' (the "
                "root artifact whose subtree is being audited)."
            )

        audit_scopes = (
            [
                AuditScope(
                    normalized_scope, artifact_id=normalized_scope_artifact
                )
            ]
            if normalized_scope
            else None
        )
        result = self._run_engine_uncapped(workspace_id, ctx, scopes=audit_scopes)
        blockers = [f for f in result.findings if f.severity is Severity.BLOCKER]
        target_key = finding_key(rule_id, artifact_ids)
        matched = self._select_suppression_candidate(
            [
                finding
                for finding in blockers
                if finding_key(finding.rule_id, finding.artifact_ids) == target_key
            ],
            normalized_scope=normalized_scope,
            normalized_scope_artifact=normalized_scope_artifact,
        )
        if matched is None:
            raise WaiverFindingNotBlockingError(
                "No blocking finding matches "
                f"{target_key!r}. Suppressions may only accept deviations the "
                "SE-Auditor currently reports as BLOCKER findings — re-run the "
                "auditor and suppress a finding it reports."
            )

        request = BlockerWaiverRequest(
            rule_id=matched.rule_id,
            artifact_ids=canonical_artifact_ids(matched.artifact_ids),
            reason=cleaned_reason,
            expires_at=expires_at,
        )
        row, created = record_waiver(
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            request=request,
            rule_id=matched.rule_id,
            scope=matched.scope,
            scope_artifact_id=matched.scope_artifact_id,
            granted_by=granted_by,
            expires_at=expires_at,
        )

        if not created and row.expires_at is not None and row.expires_at <= decision_now:
            # m1: get_or_create is idempotent and never renews, so an existing
            # expired row would make this a silent no-op (200 without effect).
            raise SuppressionExpiredError(
                "A suppression for this finding exists but has expired; "
                "re-granting is a separate governance act that is not "
                "supported yet (revoke/re-grant decision pending). The finding "
                "currently blocks the baseline gate."
            )

        if created:
            self._audit(
                ctx=ctx,
                operation="baseline.waiver_create",
                entity_type="BaselineGateWaiver",
                entity_id=row.id,
                change_reason=cleaned_reason,
                details={
                    "finding_key": row.finding_key,
                    "workspace_id": str(workspace_id),
                    "rule_id": row.rule_id,
                    "artifact_ids": list(row.artifact_ids or ()),
                    "scope": row.scope,
                    "scope_artifact_id": row.scope_artifact_id,
                    "expires_at": (
                        row.expires_at.isoformat() if row.expires_at else None
                    ),
                    "granted_by": row.granted_by,
                },
            )
            logger.warning(
                "AuditService: blocking finding %s suppressed for ws=%s by "
                "user=%s; reason: %s",
                row.rule_id,
                workspace_id,
                granted_by,
                cleaned_reason,
            )

        return SuppressionView.from_record(
            self._record_from_row(row), state="active"
        ), created

    def list_suppressions(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        state: str = "active",
        now: Optional[datetime] = None,
    ) -> List[SuppressionView]:
        """List the workspace's suppressions filtered by lifecycle *state*.

        ``state`` accepts ``"active"`` (default), ``"expired"`` or ``"all"``;
        anything else raises ``ValidationError`` (400). State is *derived* at
        read time from ``expires_at`` vs the evaluation instant — there is no
        persisted state column (#569/D3).
        """
        if state not in ("active", "expired", "all"):
            raise ValidationError(
                f"Unknown suppression state {state!r}; expected 'active', "
                "'expired' or 'all'."
            )
        self._set_tenant_context(ctx)
        all_records = load_suppressions(
            workspace_id, ctx.tenant_id, include_expired=True, now=now
        )
        active_ids = {
            record.id
            for record in load_suppressions(
                workspace_id, ctx.tenant_id, include_expired=False, now=now
            )
        }
        views: List[SuppressionView] = []
        for record in all_records:
            record_state = "active" if record.id in active_ids else "expired"
            if state != "all" and record_state != state:
                continue
            views.append(
                SuppressionView.from_record(record, state=record_state)
            )
        return views

    @staticmethod
    def _match_suppression(
        records: Sequence[SuppressionRecord],
        finding: Finding,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[SuppressionRecord]:
        """Return the first suppression that applies to *finding*, if any.

        Uses the single matcher :func:`baseline.waivers.suppression_applies`
        (R1–R3) so the report and the gate agree on "suppressed" (#569 §8 risk 2).
        """
        for record in records:
            if suppression_applies(
                record,
                finding.rule_id,
                finding.artifact_ids,
                finding.scope,
                finding.scope_artifact_id,
                now=now,
            ):
                return record
        return None

    @staticmethod
    def _select_suppression_candidate(
        candidates: Sequence[Finding],
        *,
        normalized_scope: Optional[str],
        normalized_scope_artifact: Optional[str],
    ) -> Optional[Finding]:
        """Pick the finding to suppress among same-key BLOCKER candidates.

        When several findings share the scope-less key in different scopes, a
        named scope selects the scope-equal one (for ``document``, the exact
        document); otherwise the first candidate wins (#569 step 6).
        """
        if not candidates:
            return None
        if normalized_scope:
            for finding in candidates:
                if (finding.scope or "") != normalized_scope:
                    continue
                if normalized_scope == "document" and str(
                    finding.scope_artifact_id or ""
                ) != str(normalized_scope_artifact or ""):
                    continue
                return finding
        return candidates[0]

    @staticmethod
    def _record_from_row(row) -> SuppressionRecord:
        """Build a :class:`SuppressionRecord` from a persisted waiver row."""
        return SuppressionRecord(
            id=row.id,
            finding_key=row.finding_key,
            rule_id=row.rule_id,
            artifact_ids=tuple(str(a) for a in (row.artifact_ids or ())),
            scope=row.scope or "",
            scope_artifact_id=row.scope_artifact_id or "",
            reason=row.reason,
            granted_by=row.granted_by or "",
            created_at=row.created_at,
            expires_at=row.expires_at,
        )

    # ---------- Audit run ----------

    def run_audit(
        self,
        workspace_id: str | UUID,
        ctx: AuthContext,
        *,
        tier: Optional[str] = None,
        scopes: Optional[Sequence[AuditScope]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        include_suppressed: bool = True,
        now: Optional[datetime] = None,
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
            limit: #622 — when given, returns a plain sequential window
                (``result.findings[offset:offset+limit]``, in the engine's
                own stable order) instead of the default BLOCKER-preferred
                cap, so a caller can walk the *entire* result set in chunks
                past :data:`MAX_REPORT_FINDINGS`. ``None`` (the default)
                preserves the exact pre-#622 behaviour for every existing
                caller (AuditDashboard.tsx, audit.ai_review) — see
                ``MAX_REPORT_FINDINGS``'s docstring for why that single-shot,
                grouped-by-rule shape is kept as the default. Capped at
                ``MAX_REPORT_FINDINGS`` regardless of the requested value, for
                the same payload-size reason.
            offset: #622 — starting position within the full (pre-cap) run,
                only meaningful when ``limit`` is given. Out-of-range values
                (negative, or past the end) yield an empty ``findings`` list
                rather than an error.
            include_suppressed: #569 (O3) — ``True`` (default) keeps suppressed
                findings in ``findings`` and marks them with ``suppressed`` +
                reason/expiry/id (nothing is hidden by default). ``False``
                filters them out; ``counts.*`` then describes the filtered
                window while ``total_*_available`` still describes the full,
                unfiltered, uncapped run, and ``suppressed_filtered`` explains
                the difference (m7).
            now: Injectable decision instant (#569/D3) for expiry evaluation of
                persisted suppressions; ``None`` uses the current time.

        Returns:
            :class:`AuditReport` with a remediation proposal attached to every
            *returned* finding. When the run produces more than
            :data:`MAX_REPORT_FINDINGS`, the report is capped
            (``truncated=True``, ``total_findings_available`` /
            ``total_blockers_available`` / ``total_warnings_available`` hold
            the real, pre-cap counts) — see the class-level docstring on
            ``MAX_REPORT_FINDINGS`` for the BUG-15 rationale. BLOCKER findings
            are kept in preference to WARNING findings when a cap is applied
            (blockers gate baseline creation and must stay visible even in a
            truncated view); ``index`` stays a stable position within the
            *full* (pre-cap) run so a finding's identity does not shift
            across page-less re-runs. When ``limit`` is given, ``truncated``
            instead means "more findings exist past this window"
            (``offset + len(findings) < total_findings_available``), so a
            client can tell whether to request the next window.
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
        total_findings = len(result.findings)
        # Full (pre-cap) severity totals for the dashboard's count badges
        # (BUG-15 follow-up M3) — computed once here over the uncapped
        # engine result, not over the (possibly capped) report.findings.
        total_blockers = sum(
            1 for f in result.findings if f.severity is Severity.BLOCKER
        )
        total_warnings = total_findings - total_blockers

        # #569: evaluate suppressions at decision time (D3) — no persisted state,
        # no background job. The full (uncapped) run is the basis for both the
        # marking and the absolute suppression totals.
        suppression_records = load_suppressions(
            workspace_id, tenant_id, include_expired=True, now=now
        )
        suppression_by_index: dict[int, SuppressionRecord] = {}
        total_suppressed = 0
        total_suppressed_blockers = 0
        for index, finding in enumerate(result.findings):
            record = self._match_suppression(suppression_records, finding, now=now)
            if record is None:
                continue
            suppression_by_index[index] = record
            total_suppressed += 1
            if finding.severity is Severity.BLOCKER:
                total_suppressed_blockers += 1

        indexed = list(enumerate(result.findings))
        suppressed_filtered = 0
        if not include_suppressed:
            # Filter before cap/window so a caller hiding suppressed findings
            # still gets up to MAX_REPORT_FINDINGS *visible* ones.
            kept: List[tuple[int, Finding]] = []
            for pair in indexed:
                if pair[0] in suppression_by_index:
                    suppressed_filtered += 1
                    continue
                kept.append(pair)
            indexed = kept

        report_offset = 0
        visible_total = total_findings - suppressed_filtered
        if limit is not None:
            # #622: plain sequential window, engine order preserved — lets a
            # client page through the *entire* result set deterministically.
            window_limit = min(max(limit, 0), self.MAX_REPORT_FINDINGS)
            window_start = max(offset, 0)
            indexed = indexed[window_start : window_start + window_limit]
            truncated = (window_start + len(indexed)) < visible_total
            report_offset = window_start
        else:
            truncated = len(indexed) > self.MAX_REPORT_FINDINGS
            if truncated:
                # Stable-sort BLOCKER findings first (Python's sort is stable,
                # so ties keep the engine's original rule/scope order), then
                # cap. Re-sort the kept subset back to index order so display
                # order still follows the engine's rule/scope grouping.
                indexed.sort(key=lambda pair: pair[1].severity is not Severity.BLOCKER)
                indexed = indexed[: self.MAX_REPORT_FINDINGS]
                indexed.sort(key=lambda pair: pair[0])

        report = AuditReport(
            tier=result.tier,
            scope=primary_scope.scope if primary_scope else None,
            scope_artifact_id=(
                primary_scope.artifact_id if primary_scope else None
            ),
            truncated=truncated,
            total_findings_available=total_findings,
            total_blockers_available=total_blockers,
            total_warnings_available=total_warnings,
            offset=report_offset,
            include_suppressed=include_suppressed,
            total_suppressed_available=total_suppressed,
            total_suppressed_blockers_available=total_suppressed_blockers,
            suppressed_filtered=suppressed_filtered,
        )

        for index, finding in indexed:
            proposal = self._propose_for_finding(finding, tenant_id, ws_id)
            record = suppression_by_index.get(index)
            report.findings.append(
                AuditFindingView(
                    index=index,
                    finding=finding,
                    remediation=proposal,
                    suppressed=record is not None,
                    suppressed_until=record.expires_at if record else None,
                    suppression_reason=record.reason if record else None,
                    suppression_id=record.id if record else None,
                )
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

        A finding is considered "the same" when its canonical identity — rule
        id plus the sorted artifact-id set (:func:`baseline.waivers.finding_key`,
        without the scope: the re-audit below may resolve a different scope for
        a scope-aware rule than the caller passed in, and the scope-less form is
        the one the gate's waivers are matched with, #1021) — matches.

        Uses :meth:`_run_engine_uncapped`, NOT :meth:`run_audit` (BUG-15
        follow-up H1): the Phase 3 "negative -> positive acceptance
        guarantee" this backs (see :meth:`remediate`'s docstring) must hold
        in every workspace, including the >500-finding ones run_audit()
        truncates for the dashboard. Checking against the capped report
        would let a still-present finding outside the cap read as resolved.
        """
        scopes = (
            [AuditScope(scope, artifact_id=scope_artifact_id)]
            if scope is not None
            else None
        )
        result = self._run_engine_uncapped(workspace_id, ctx, scopes=scopes)
        target_key = finding_key(finding.rule_id, finding.artifact_ids)
        for current in result.findings:
            if finding_key(current.rule_id, current.artifact_ids) == target_key:
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
    "SuppressionView",
]
