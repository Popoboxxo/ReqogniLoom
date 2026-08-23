"""
COMP-AS-006 BaselineFacade — Orchestrates baseline lifecycle.

leaf_id : COMP-AS-006
req_id  : REQ-L1-018, REQ-L2-AS-006, REQ-L2-AS-007

Delegates to baseline.services (build/diff/get/list_baselines/get_item_at_baseline)
and orchestrates preset-scope validation + audit via ServiceBase helpers.

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: create_baseline, diff_baselines, get_baseline,
                       list_baselines, get_item_at_baseline
  IF-AS-INT-006     — outbound: PresetPolicyService.is_scope_allowed()

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-006_BaselineFacade/
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover - typing only
    # Import-time only: ``traceability`` (Layer 1) is loaded lazily inside the
    # gate methods so this Layer-2 facade keeps its light import graph.
    from traceability.audit import Finding

from auth_tenancy.context import AuthContext

# Backward-compat alias used by tests that patch 'application.baseline_facade.TenantContext'
TenantContext = AuthContext

from application.base import (
    BaselineGateBlockedError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.event_bus import DomainEvent
from application.preset_policy_service import get_preset_policy_service

logger = logging.getLogger(__name__)

#: Minimum length of an SE-Auditor gate override justification (GH-513).
#: A waiver is a governance record that outlives the person who granted it —
#: "ok" or "later" is not one. The bar is deliberately low enough to type in
#: one line and high enough to force an actual sentence.
MIN_OVERRIDE_REASON_LENGTH = 10


class BaselineFacade(ServiceBase):
    """Orchestrating facade for Baseline operations.

    COMP-AS-006 (IF-AS-EXT-IN-001, IF-AS-INT-006).

    Usage::

        facade = BaselineFacade()
        baseline_id = facade.create_baseline(
            scope="project",
            workspace_id=ws_id,
            name="v1.0-baseline",
            ctx=auth_ctx,
        )
    """

    # ---------- Public API ----------

    def create_baseline(
        self,
        scope: str,
        workspace_id: UUID | str,
        name: str,
        ctx: AuthContext,
        description: Optional[str] = None,
        document_id: Optional[UUID | str] = None,
        override_reason: Optional[str] = None,
    ) -> UUID:
        """Create an immutable baseline after preset-scope validation.

        REQ-L3-AS006-001 (scope gate), REQ-L3-AS006-002 (event + audit).

        Args:
            scope: "document" | "project" | "global"
            workspace_id: Target workspace UUID.
            name: Human-readable baseline name (unique per workspace).
            ctx: Fully resolved AuthContext.
            description: Optional description.
            document_id: Required when scope="document".
            override_reason: Written justification for waiving the SE-Auditor
                gate (GH-513). Only consulted when the gate actually reports
                BLOCKER findings; requires approval authority (Admin or
                Approver) and is recorded in the audit log and on the baseline.

        Returns:
            UUID of the newly created baseline.

        Raises:
            PermissionDeniedError: Caller lacks write permission, or lacks
                approval authority for an override.
            BaselineGateBlockedError: SE-Auditor BLOCKERs and no accepted
                override (subclass of ValidationError).
            ValidationError: Scope not allowed by preset, duplicate name, a
                missing ``document_id`` for scope="document", an unusable
                override justification, or an unevaluable gate.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        ws_id = UUID(str(workspace_id))

        # IF-AS-INT-006: scope gate via PresetPolicyService
        self._check_scope_allowed(str(ws_id), scope)

        doc_id: Optional[UUID] = (
            UUID(str(document_id)) if document_id is not None else None
        )

        # GH-715: scope="document" requires a root artifact to resolve the
        # subtree against (see baseline.services.resolve_scope_item_ids). This
        # MUST be validated here, before the SE-Auditor gate is evaluated —
        # AuditContext.scope_item_ids resolves lazily via the same helper and
        # raises a bare ValueError when document_id/artifact_id is missing,
        # which _enforce_audit_gate's fail-closed handler (GH-400) would
        # otherwise catch and re-wrap as an opaque "internal error", hiding a
        # simple, callable-side validation problem behind a governance-gate
        # failure message.
        if scope == "document" and doc_id is None:
            raise ValidationError(
                "Baseline cannot be created: document_id is required when "
                "scope='document' (the root artifact whose subtree is being "
                "baselined)."
            )

        # SE-conformance gate: no baseline over known-broken traceability —
        # unless the blockers are explicitly and traceably waived (GH-513).
        waived = self._enforce_audit_gate(
            workspace_id=ws_id,
            scope=scope,
            document_id=doc_id,
            ctx=ctx,
            override_reason=override_reason,
        )
        effective_description = (
            _annotate_override(description, waived, override_reason or "")
            if waived
            else description
        )

        # Delegate to baseline.services (IF-BL-EXT-IN-001)
        from baseline.services import build as baseline_build

        try:
            baseline_id = baseline_build(
                scope=scope,
                workspace_id=ws_id,
                name=name,
                tenant_id=ctx.tenant_id,
                description=effective_description,
                created_by=str(ctx.user_id),
                document_id=doc_id,
            )
        except Exception as exc:
            # Remap baseline-domain exceptions to application layer
            _remap_baseline_exc(exc)

        # Audit
        details: dict = {"scope": scope, "name": name, "workspace_id": str(ws_id)}
        if waived:
            # The append-only audit log is the authoritative waiver record:
            # who waived what, when, and why (REQ-L2-AL-001).
            details.update(
                {
                    "audit_gate_override": True,
                    "waived_blocker_count": len(waived),
                    "waived_rule_ids": sorted({f.rule_id for f in waived}),
                    "override_reason": (override_reason or "").strip(),
                }
            )
        self._audit(
            ctx=ctx,
            operation="baseline.create",
            entity_type="Baseline",
            entity_id=baseline_id,
            change_reason=(override_reason or "").strip() if waived else None,
            details=details,
        )

        # Domain event (IF-AS-INT-009: BaselineCreated)
        self._emit_event(
            self._make_event(
                event_type="BaselineCreated",
                entity_id=baseline_id,
                workspace_id=ws_id,
                payload={
                    "scope": scope,
                    "name": name,
                    "audit_gate_override": bool(waived),
                },
            )
        )

        return baseline_id

    # ---------- SE-conformance gate (lever 2) ----------

    def _enforce_audit_gate(
        self,
        *,
        workspace_id: UUID,
        scope: str,
        document_id: Optional[UUID],
        ctx: AuthContext,
        override_reason: Optional[str] = None,
    ) -> Tuple["Finding", ...]:
        """Reject the baseline build when the SE-Auditor reports BLOCKERs.

        A baseline is a governance artefact: freezing a trace graph that the
        workspace's own rigor preset already declares broken makes every
        downstream diff and audit trail authoritative over known-bad data.
        The SE-Auditor (``traceability.audit``) has had BLOCKER-severity rules
        since SysEng 2.0 Phase 2 but was only ever exposed as a *report*; this
        is its first enforcement point.

        Tier awareness comes entirely from the existing
        ``RULE_PRESET_MAP``: Minimal maps to an empty rule set (structurally
        enforced in ``traceability.audit.registry``), so this method issues no
        query and never blocks there. Standard runs the baseline rule set with
        TRACE-P2 downgraded to WARNING; Extended adds the SE-only rules —
        both severity mappings are the RuleEngine's, not re-derived here.

        Latency: run synchronously, matching the surrounding code path —
        ``baseline.services.build`` (delta index + snapshot write) is itself
        synchronous, and the audit is a bounded set of aggregate queries over
        the same scope the build is about to walk. Making the gate async would
        mean the build could not consume its verdict.

        Fail-closed on auditor malfunction (GH-400): this is a governance
        gate, not a best-effort convenience check. An internal error while
        *evaluating* the gate (a bug in a rule, a DB hiccup, an unexpected
        AuditService exception) means the gate's verdict is unknown — and an
        unknown verdict must not be treated as "no BLOCKERs". The previous
        behaviour caught every non-``ValidationError`` exception, logged it,
        and returned as if the audit had come back clean, i.e. an internal
        fault in the gate *itself* silently opened the gate it was supposed
        to guard. Fail-closed here means: surface a clear, catchable
        ``ValidationError`` to the caller (blocking the baseline build) and
        log the original exception via ``logger.exception`` for operators —
        never a silent pass-through.

        Override (GH-513): fail-closed with no exit is a deadlock, not a gate.
        Most findings have no automatic remediation ("Adopt"), and the Auditor
        UI has no manual edit flow, so a workspace with a single stubborn
        BLOCKER could produce no baseline at all — no release, no review, no
        way forward. The gate therefore keeps its default (block), and adds
        one narrow, expensive exit: an explicit written justification from a
        caller with approval authority. Why those three constraints:

          * *explicit* — the override is never implied by a retry; the caller
            has to send ``override_reason`` on purpose;
          * *justified* — the reason is stored in the append-only audit log
            and on the baseline itself, so a later reader sees a waiver rather
            than a clean baseline;
          * *authorised* — waiving a compliance verdict is an approval act
            (``Operation.WORKFLOW_APPROVAL``: Admin or Approver), not a write
            act; every Editor being able to wave the gate through would make
            it decorative.

        The GH-400 fail-closed branch above is deliberately *not* overridable:
        it fires when the verdict is unknown, and an unknown verdict cannot be
        justified — nobody can state what is being accepted.

        Args:
            override_reason: Justification for waiving BLOCKER findings, or
                ``None``/blank for the default (blocking) behaviour.

        Returns:
            The tuple of waived findings (empty when the audit was clean).
            Non-empty means the caller must record the waiver.

        Raises:
            BaselineGateBlockedError: BLOCKER findings and no override.
            PermissionDeniedError: Override attempted without approval authority.
            ValidationError: Override justification unusable, OR the SE-Auditor
                gate itself failed to evaluate (fail-closed, not overridable).
        """
        from application.audit_service import AuditService
        from traceability.audit import AuditScope

        audit_scope = AuditScope(
            scope=scope,
            artifact_id=str(document_id) if document_id is not None else None,
        )
        try:
            findings = AuditService().blocking_findings(
                workspace_id, ctx, scopes=[audit_scope]
            )
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Fail CLOSED on an auditor malfunction (GH-400): a governance
            # gate that cannot be evaluated must block, not silently pass.
            logger.exception(
                "BaselineFacade: SE-Auditor gate failed for ws=%s scope=%s; "
                "blocking the baseline build (fail-closed)",
                workspace_id,
                scope,
            )
            raise ValidationError(
                "Baseline cannot be created: the SE-Auditor gate could not be "
                "evaluated due to an internal error "
                f"({type(exc).__name__}: {exc}). Baseline creation is blocked "
                "until the SE-Auditor is operational again — this is a "
                "fail-closed governance gate, not a best-effort check."
            ) from exc

        if not findings:
            return ()

        if override_reason is not None and str(override_reason).strip():
            self._assert_override_permission(ctx)
            self._validate_override_reason(override_reason)
            logger.warning(
                "BaselineFacade: SE-Auditor gate OVERRIDDEN for ws=%s scope=%s by "
                "user=%s — %s blocking finding(s) waived (%s); reason: %s",
                workspace_id,
                scope,
                getattr(ctx, "user_id", "?"),
                len(findings),
                ", ".join(sorted({f.rule_id for f in findings})),
                str(override_reason).strip(),
            )
            return tuple(findings)

        raise BaselineGateBlockedError(
            f"Baseline cannot be created: the SE-Auditor reported "
            f"{len(findings)} blocking finding(s) for this workspace. "
            f"Resolve them first — {_summarise_findings(findings)}. "
            "If the remaining findings are an accepted deviation, an Admin or "
            "Approver can create the baseline anyway by supplying a written "
            "justification (override_reason); it is recorded in the audit log "
            "and on the baseline."
        )

    @staticmethod
    def _assert_override_permission(ctx: AuthContext) -> None:
        """Require approval authority (Admin/Approver) to waive the gate.

        Imported lazily for the same circular-import reason as
        ``ServiceBase._assert_write_permission``.
        """
        from auth_tenancy.services.authorization import (
            AuthorizationService,
            Operation,
        )

        decision = AuthorizationService().decide_access(
            tuple(getattr(ctx, "active_roles", ()) or ()),
            Operation.WORKFLOW_APPROVAL,
        )
        if not decision.allow:
            raise PermissionDeniedError(
                "Permission denied: overriding the SE-Auditor baseline gate "
                "requires approval authority ('admin' or 'approver'), user has "
                f"{tuple(getattr(ctx, 'active_roles', ()) or ())}."
            )

    @staticmethod
    def _validate_override_reason(override_reason: str) -> None:
        """Reject a justification that would not survive an audit."""
        cleaned = str(override_reason).strip()
        if len(cleaned) < MIN_OVERRIDE_REASON_LENGTH:
            raise ValidationError(
                "Baseline cannot be created: the SE-Auditor override requires a "
                f"written justification of at least {MIN_OVERRIDE_REASON_LENGTH} "
                "characters stating which deviation is being accepted and why."
            )

    def diff_baselines(
        self,
        baseline_a_id: UUID | str,
        baseline_b_id: UUID | str,
        ctx: AuthContext,
    ):
        """Compute structural diff between two baselines.

        REQ-L3-AS006-003.

        Args:
            baseline_a_id: Reference (older) baseline UUID.
            baseline_b_id: Target (newer) baseline UUID.
            ctx: AuthContext for tenant propagation.

        Returns:
            DiffResult (baseline.types.DiffResult).
        """
        self._set_tenant_context(ctx)

        from baseline.services import diff as baseline_diff

        try:
            return baseline_diff(
                baseline_a_id=UUID(str(baseline_a_id)),
                baseline_b_id=UUID(str(baseline_b_id)),
                tenant_id=ctx.tenant_id,
            )
        except Exception as exc:
            _remap_baseline_exc(exc)

    def get_baseline(self, baseline_id: UUID | str, ctx: AuthContext):
        """Return full baseline detail including delta entries.

        Args:
            baseline_id: UUID of the target baseline.
            ctx: AuthContext for tenant propagation.

        Returns:
            BaselineDetail (baseline.types.BaselineDetail).
        """
        self._set_tenant_context(ctx)

        from baseline.services import get as baseline_get

        try:
            return baseline_get(baseline_id=UUID(str(baseline_id)), tenant_id=ctx.tenant_id)
        except Exception as exc:
            _remap_baseline_exc(exc)

    def list_baselines(
        self,
        workspace_id: UUID | str,
        ctx: AuthContext,
        scope: Optional[str] = None,
    ) -> List:
        """Return baseline summaries for a workspace.

        Args:
            workspace_id: Target workspace UUID.
            ctx: AuthContext for tenant propagation.
            scope: Optional scope filter.

        Returns:
            List of BaselineSummary.
        """
        self._set_tenant_context(ctx)

        from baseline.services import list_baselines as baseline_list

        return baseline_list(
            workspace_id=UUID(str(workspace_id)),
            scope=scope,
            tenant_id=ctx.tenant_id,
        )

    def get_item_at_baseline(
        self,
        baseline_id: UUID | str,
        item_id: str,
        ctx: AuthContext,
    ):
        """Reconstruct historical payload of an item at baseline time.

        Args:
            baseline_id: UUID of the target baseline.
            item_id: String UUID of the item.
            ctx: AuthContext for tenant propagation.

        Returns:
            ItemPayload (baseline.types.ItemPayload).
        """
        self._set_tenant_context(ctx)

        from baseline.services import get_item_at_baseline as baseline_item

        try:
            return baseline_item(
                baseline_id=UUID(str(baseline_id)),
                item_id=item_id,
                tenant_id=ctx.tenant_id,
            )
        except Exception as exc:
            _remap_baseline_exc(exc)

    # ---------- Private helpers ----------

    @staticmethod
    def _check_scope_allowed(workspace_id: str, scope: str) -> None:
        """Raise ValidationError if preset forbids this scope.

        IF-AS-INT-006 → PresetPolicyService.is_scope_allowed().
        """
        # get_preset_policy_service is imported at module level to allow test mocking.
        policy = get_preset_policy_service()
        if not policy.is_scope_allowed(workspace_id, scope):
            allowed = policy.get_policy(workspace_id, "baseline_scopes")
            raise ValidationError(
                f"Baseline scope '{scope}' is not allowed by the workspace preset. "
                f"Allowed values: {sorted(allowed)}"
            )


# ---------- SE-Auditor gate helpers (GH-513) ----------

#: How many individual findings the block message enumerates. The QS instance
#: hit 77 BLOCKERs; inlining all of them produced a multi-kilobyte error string
#: that no UI could render usefully. The full list belongs in the Auditor
#: dashboard, which is what the truncation hint points at.
_MAX_LISTED_FINDINGS = 10


def _summarise_findings(findings: Sequence["Finding"]) -> str:
    """Render up to :data:`_MAX_LISTED_FINDINGS` findings, then a count hint."""
    listed = "; ".join(
        f"{f.rule_id} [{', '.join(f.artifact_ids) or 'graph'}]: {f.message}"
        for f in findings[:_MAX_LISTED_FINDINGS]
    )
    remaining = len(findings) - _MAX_LISTED_FINDINGS
    if remaining > 0:
        listed += (
            f"; … and {remaining} more (see the SE-Auditor dashboard for the "
            "full list)"
        )
    return listed


def _annotate_override(
    description: Optional[str],
    waived: Sequence["Finding"],
    override_reason: str,
) -> str:
    """Append the waiver note to the baseline description (GH-513).

    A baseline created over known BLOCKERs must not be indistinguishable from
    a clean one. The audit log is the authoritative record, but it is not what
    a reviewer opening the baseline sees — the description is, and it is
    written once at creation time, so this does not touch the snapshot's
    immutability guarantee (``bl_baseline_snapshot`` rejects UPDATEs).
    """
    rule_ids = ", ".join(sorted({f.rule_id for f in waived}))
    note = (
        f"[SE-Auditor override] {len(waived)} blocking finding(s) waived "
        f"({rule_ids}). Justification: {override_reason.strip()}"
    )
    existing = (description or "").strip()
    return f"{existing}\n\n{note}" if existing else note


# ---------- Exception remapping ----------

def _remap_baseline_exc(exc: Exception) -> None:
    """Re-raise baseline-domain exceptions as application-layer exceptions."""
    from baseline.exceptions import (
        BaselineNotFoundError,
        DuplicateBaselineNameError,
        EmptyBaselineNameError,
        ScopeNotAllowedError,
    )
    from application.base import NotFoundError, ValidationError

    if isinstance(exc, (ScopeNotAllowedError, EmptyBaselineNameError, DuplicateBaselineNameError)):
        raise ValidationError(str(exc)) from exc
    if isinstance(exc, BaselineNotFoundError):
        raise NotFoundError(str(exc)) from exc
    raise exc


__all__ = ["BaselineFacade"]
