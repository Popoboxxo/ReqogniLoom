"""#569 — ``AuditService`` suppression surface, report marking and counts.

Level-2 half of the specification (revision 3, APPROVED): the standalone
``AuditService.suppress_finding`` / ``list_suppressions`` path, the report
marking/filter contract and the L1 → L2 error remaps.

* **AC-569-03** — exactly one ``baseline.waiver_create`` audit entry per created
  waiver.
* **AC-569-04** — idempotency (created / re-used).
* **AC-569-15 / AC-569-17** — a non-blocking finding, and a document-scoped
  finding, are handled precisely.
* **AC-569-20 / AC-569-29 / AC-569-30** — shared authority choke point, the
  three L2 error types and the None-safe ``granted_by`` formula.
* **AC-569-13 / AC-569-27** — descriptive ``counts`` vs absolute ``total_*``;
  the ``include_suppressed=False`` window inequality (m7) and the unconditional
  ``blockers + warnings == total`` identity (R3-01).
* **AC-569-21 / AC-569-31** — expired-row 409, request-expiry 400 precedence and
  decision-time expiry via an injectable ``now``.

Spec/reality note (reported, not papered over): the spec's M3 premise that
``ServiceBase._audit(details=…)`` **persists** its ``details`` does not hold on
this branch — ``log_write`` accepts ``details`` but drops it, and ``AuditEntry``
has no details/JSON column (``backend/audit/{services,models,writer}.py``). The
writer rebuild is an explicit Non-Goal (§7), so the tests here assert the
**durable** audit columns (op, entity_type, change_reason, actor) on the real
entry and the **produced** ``details`` payload on the intercepted
``_audit`` call.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

from application.audit_service import AuditService, SuppressionView
from application.base import (
    PermissionDeniedError,
    SuppressionExpiredError,
    ValidationError,
    WaiverFindingNotBlockingError,
    WaiverReasonPolicyViolation,
)
from application.baseline_facade import BaselineFacade, _validate_gate_reason
from auth_tenancy.context import AuthContext
from baseline.exceptions import GovernanceReasonError
from baseline.models import BaselineGateWaiver
from baseline.waivers import (
    BlockerWaiverRequest,
    assert_gate_waiver_authority,
    finding_key,
    record_waiver,
)
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace
from traceability.audit import AuditScope, AuditResult, Finding, Severity

pytestmark = pytest.mark.django_db

_REASON = "Accepted deviation for the beta cut, see review protocol 2026-09-01."
_US = "\x1f"


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="audit-569", slug="audit-569")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="audit-569-user", email="audit569@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant):
    with _active(tenant):
        return make_workspace(tenant, name="audit-569-ws")


@pytest.fixture
def admin_ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("admin",),
        auth_method="test",
        api_key_id=None,
        tenant_name="audit-569",
    )


@pytest.fixture
def editor_ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )


def _blocker(
    rule_id: str = "TRACE-P1",
    artifact_ids=("art-1",),
    *,
    scope: str | None = None,
    scope_artifact_id: str | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.BLOCKER,
        message="Root Requirement has no derives-from link.",
        artifact_ids=tuple(artifact_ids),
        scope=scope,
        scope_artifact_id=scope_artifact_id,
    )


class _ScopeAwareStubEngine:
    """Deterministic stand-in for the RuleEngine.

    Returns scope-agnostic findings always and scope-aware ones only for the
    requested scopes — enough to exercise the service's scope selection (C1)
    without building a real graph.
    """

    def __init__(self, findings) -> None:
        self._findings = list(findings)
        self.calls: list = []

    def run(self, *, tier, workspace_id, tenant_id, scopes=None):
        self.calls.append(scopes)
        effective = scopes if scopes is not None else [AuditScope("project")]
        wanted = {(s.scope, str(s.artifact_id or "")) for s in effective}
        returned = [
            finding
            for finding in self._findings
            if finding.scope is None
            or (finding.scope, str(finding.scope_artifact_id or "")) in wanted
        ]
        return AuditResult(tier=tier, findings=returned)


def _persist(
    tenant: Tenant,
    workspace,
    *,
    rule_id: str = "TRACE-P1",
    artifact_ids=("art-1",),
    scope: str = "",
    scope_artifact_id: str = "",
    reason: str = _REASON,
    granted_by: str = "author-1",
    expires_at: datetime | None = None,
) -> BaselineGateWaiver:
    request = BlockerWaiverRequest(
        rule_id=rule_id, artifact_ids=tuple(artifact_ids), reason=reason
    )
    row, _ = record_waiver(
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        request=request,
        rule_id=rule_id,
        scope=scope or None,
        scope_artifact_id=scope_artifact_id or None,
        granted_by=granted_by,
        expires_at=expires_at,
    )
    return row


def _waiver_entries(tenant: Tenant):
    from audit.models import AuditEntry

    return AuditEntry.unscoped.filter(
        op="baseline.waiver_create",
        entity_type="BaselineGateWaiver",
        tenant_id=tenant.id,
    )


# ---------------------------------------------------------------------------
# suppress_finding — audit trail, idempotency, authors
# ---------------------------------------------------------------------------


class TestSuppressFinding:
    def test_each_new_suppression_gets_an_audit_entry(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-03 / V7: exactly one audit entry, with reason and author."""
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        view, created = service.suppress_finding(
            workspace.id,
            admin_ctx,
            rule_id="TRACE-P1",
            artifact_ids=["art-1"],
            reason=_REASON,
        )

        assert created is True
        assert isinstance(view, SuppressionView)
        assert view.granted_by == str(admin_ctx.user_id)
        assert view.state == "active"

        entries = list(_waiver_entries(tenant))
        assert len(entries) == 1
        entry = entries[0]
        assert entry.change_reason == _REASON
        assert entry.actor == str(admin_ctx.user_id)
        assert entry.entity_type == "BaselineGateWaiver"

    def test_suppression_audit_details_are_produced(self, tenant, workspace, admin_ctx):
        """AC-569-03: the ``baseline.waiver_create`` details payload is complete.

        Asserted on the intercepted ``_audit`` call because ``details`` are
        dropped by the v1 writer on this branch (see the module docstring).
        """
        from unittest.mock import patch

        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        with patch.object(AuditService, "_audit") as mock_audit:
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                reason=_REASON,
            )

        details = mock_audit.call_args.kwargs["details"]
        assert mock_audit.call_args.kwargs["operation"] == "baseline.waiver_create"
        assert details["rule_id"] == "TRACE-P1"
        assert details["artifact_ids"] == ["art-1"]
        assert details["granted_by"] == str(admin_ctx.user_id)
        assert details["expires_at"] is None
        assert details["finding_key"] == f"TRACE-P1{_US}art-1"

    def test_waiver_is_idempotent_per_finding(self, tenant, workspace, admin_ctx):
        """AC-569-04: a second identical request returns created=False, no new row/entry."""
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        _first, created_first = service.suppress_finding(
            workspace.id,
            admin_ctx,
            rule_id="TRACE-P1",
            artifact_ids=["art-1"],
            reason=_REASON,
        )
        second, created_second = service.suppress_finding(
            workspace.id,
            admin_ctx,
            rule_id="TRACE-P1",
            artifact_ids=["art-1"],
            reason="A different justification on the second attempt.",
        )

        assert created_first is True
        assert created_second is False
        assert second.reason == _REASON  # the first decision stands
        assert BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id).count() == 1
        assert _waiver_entries(tenant).count() == 1

    def test_granted_by_comes_from_the_auth_context_only(
        self, tenant, workspace, user
    ):
        """AC-569-30: author is the None-safe context value, never the body."""
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        view, _ = service.suppress_finding(
            workspace.id,
            ctx,
            rule_id="TRACE-P1",
            artifact_ids=["art-1"],
            reason=_REASON,
        )
        assert view.granted_by == str(getattr(ctx, "user_id", "") or "").strip()

    def test_blank_author_is_rejected(self, tenant, workspace):
        """AC-569-30 / V34: ``None`` ⇒ ``""`` ⇒ 403, never the string ``"None"``."""
        ctx = AuthContext(
            user_id=None,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        assert str(getattr(ctx, "user_id", "") or "").strip() == ""
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        with pytest.raises(PermissionDeniedError):
            service.suppress_finding(
                workspace.id,
                ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                reason=_REASON,
            )
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()


# ---------------------------------------------------------------------------
# Error-type contract over the layer boundary (M-B)
# ---------------------------------------------------------------------------


class TestErrorTypeContract:
    def test_reason_policy_raises_governance_reason_error(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-29(i): L1 raises the domain error, the service maps it."""
        from baseline.waivers import validate_waiver_reason

        with pytest.raises(GovernanceReasonError):
            validate_waiver_reason("ok", label="suppression justification")

        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        with pytest.raises(WaiverReasonPolicyViolation) as exc_info:
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                reason="aaaaaaaaaaaaaaaaaaaa",
            )
        assert exc_info.value.error_code == "WAIVER_REASON_REJECTED"
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_gate_path_still_raises_plain_validation_error(self):
        """AC-569-29(ii): the legacy gate path keeps its exact type (never the new code)."""
        with pytest.raises(ValidationError) as exc_info:
            _validate_gate_reason("ok", label="waiver justification")
        assert type(exc_info.value) is ValidationError

    def test_authority_choke_point_is_shared(self, tenant, workspace, editor_ctx):
        """AC-569-20 / V24: one choke point, identical denial for both paths."""
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        with pytest.raises(PermissionDeniedError):
            service.suppress_finding(
                workspace.id,
                editor_ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                reason=_REASON,
            )
        with pytest.raises(PermissionDeniedError):
            BaselineFacade._assert_override_permission(editor_ctx)
        # … and the shared Layer-1 helper itself raises the domain error.
        from baseline.exceptions import GovernanceAuthorityError

        with pytest.raises(GovernanceAuthorityError):
            assert_gate_waiver_authority(editor_ctx)
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_unknown_or_warning_finding_is_not_blocking(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-15: blocker-only (O2) — unknown and WARNING findings are refused."""
        warning = Finding(
            rule_id="TRACE-P1",
            severity=Severity.WARNING,
            message="advisory",
            artifact_ids=("art-1",),
        )
        service = AuditService(engine=_ScopeAwareStubEngine([warning]))
        with pytest.raises(WaiverFindingNotBlockingError) as exc_info:
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                reason=_REASON,
            )
        assert exc_info.value.error_code == "WAIVER_FINDING_NOT_BLOCKING"

        empty = AuditService(engine=_ScopeAwareStubEngine([]))
        with pytest.raises(WaiverFindingNotBlockingError):
            empty.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="CONS-P11",
                artifact_ids=["other"],
                reason=_REASON,
            )
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()


# ---------------------------------------------------------------------------
# Scope selection (C1)
# ---------------------------------------------------------------------------


class TestScopeSelection:
    def test_document_scoped_finding_can_be_suppressed(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-17: a document-scoped finding is reachable with the named scope."""
        document_finding = _blocker(
            "TRACE-P7", ("child", "sibling"), scope="document", scope_artifact_id="doc-1"
        )
        engine = _ScopeAwareStubEngine([document_finding])
        service = AuditService(engine=engine)

        view, created = service.suppress_finding(
            workspace.id,
            admin_ctx,
            rule_id="TRACE-P7",
            artifact_ids=["child", "sibling"],
            scope="document",
            scope_artifact_id="doc-1",
            reason=_REASON,
        )

        assert created is True
        assert view.scope == "document"
        assert view.scope_artifact_id == "doc-1"
        row = BaselineGateWaiver.unscoped.get(workspace_id=workspace.id)
        assert row.scope == "document"
        assert row.scope_artifact_id == "doc-1"
        assert engine.calls[-1] == [AuditScope("document", artifact_id="doc-1")]

    def test_document_scope_without_artifact_id_is_rejected(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-17: ``document`` without a root artifact is a 400 (never 422)."""
        service = AuditService(
            engine=_ScopeAwareStubEngine(
                [_blocker("TRACE-P7", ("a",), scope="document", scope_artifact_id="d")]
            )
        )
        with pytest.raises(ValidationError):
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P7",
                artifact_ids=["a"],
                scope="document",
                reason=_REASON,
            )

    def test_an_invalid_scope_is_rejected(self, tenant, workspace, admin_ctx):
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        with pytest.raises(ValidationError):
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                scope="galaxy",
                reason=_REASON,
            )

    def test_scope_agnostic_call_does_not_create_a_document_row(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-17: without the scope the document finding is simply not blocking."""
        document_finding = _blocker(
            "TRACE-P7", ("a",), scope="document", scope_artifact_id="doc-1"
        )
        service = AuditService(engine=_ScopeAwareStubEngine([document_finding]))
        with pytest.raises(WaiverFindingNotBlockingError):
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P7",
                artifact_ids=["a"],
                reason=_REASON,
            )
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()


# ---------------------------------------------------------------------------
# Expiry (D2/D3, m1)
# ---------------------------------------------------------------------------


class TestExpiry:
    def test_naive_or_past_expires_at_is_rejected(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-31 / V35: past or naive request expiry ⇒ 400, no row."""
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        past = datetime.now(timezone.utc) - timedelta(days=1)
        naive = datetime.now() + timedelta(days=1)

        for value in (past, naive):
            with pytest.raises(ValidationError):
                service.suppress_finding(
                    workspace.id,
                    admin_ctx,
                    rule_id="TRACE-P1",
                    artifact_ids=["art-1"],
                    reason=_REASON,
                    expires_at=value,
                )
        assert not BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace.id
        ).exists()

    def test_expired_existing_waiver_raises_suppression_expired(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-21 / m1: only an expired row ⇒ 409, no silent 200."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        _persist(tenant, workspace, expires_at=past)

        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        with pytest.raises(SuppressionExpiredError) as exc_info:
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                reason=_REASON,
            )
        assert exc_info.value.error_code == "SUPPRESSION_EXPIRED"
        assert _waiver_entries(tenant).count() == 0

    def test_request_expiry_precedence_beats_the_expired_row(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-21 / R3-07: request ``expires_at`` guard (400) runs before the 409."""
        past = datetime.now(timezone.utc) - timedelta(days=2)
        _persist(tenant, workspace, expires_at=past)

        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        with pytest.raises(ValidationError) as exc_info:
            service.suppress_finding(
                workspace.id,
                admin_ctx,
                rule_id="TRACE-P1",
                artifact_ids=["art-1"],
                reason=_REASON,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        assert not isinstance(exc_info.value, SuppressionExpiredError)

    def test_active_existing_waiver_is_a_200_no_op(self, tenant, workspace, admin_ctx):
        """AC-569-21: an active row ⇒ created=False (not 409)."""
        future = datetime.now(timezone.utc) + timedelta(days=30)
        _persist(tenant, workspace, expires_at=future)
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        _view, created = service.suppress_finding(
            workspace.id,
            admin_ctx,
            rule_id="TRACE-P1",
            artifact_ids=["art-1"],
            reason=_REASON,
        )
        assert created is False


# ---------------------------------------------------------------------------
# list_suppressions
# ---------------------------------------------------------------------------


class TestListSuppressions:
    def test_list_filters_by_state(self, tenant, workspace, admin_ctx):
        """AC-569-05: default active, ``expired``/``all``; identity_key is scoped."""
        # The gate stamps scope="project" for a scope-agnostic rule; identity_key
        # carries that scope, finding_key must not.
        active = _persist(
            tenant,
            workspace,
            rule_id="TRACE-P1",
            artifact_ids=("art-1",),
            scope="project",
        )
        _persist(
            tenant,
            workspace,
            rule_id="VERIF-P8",
            artifact_ids=("art-2",),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        service = AuditService()

        active_views = service.list_suppressions(workspace.id, admin_ctx)
        assert [v.state for v in active_views] == ["active"]
        assert active_views[0].waiver_id == active.id
        assert active_views[0].finding_key == f"TRACE-P1{_US}art-1"
        assert active_views[0].identity_key == f"TRACE-P1{_US}art-1{_US}project"

        expired_views = service.list_suppressions(
            workspace.id, admin_ctx, state="expired"
        )
        assert [v.state for v in expired_views] == ["expired"]

        all_views = service.list_suppressions(workspace.id, admin_ctx, state="all")
        assert {v.state for v in all_views} == {"active", "expired"}

        with pytest.raises(ValidationError):
            service.list_suppressions(workspace.id, admin_ctx, state="nope")


# ---------------------------------------------------------------------------
# run_audit — marking, filtering, counts
# ---------------------------------------------------------------------------


class TestRunAuditSuppression:
    def test_report_marks_and_filters_suppressed(self, tenant, workspace, admin_ctx):
        """AC-569-13 / V17: default keeps and marks; ``False`` filters (m7 identity)."""
        matching = _blocker("TRACE-P1", ("art-1",))
        other = _blocker("VERIF-P8", ("art-2",))
        row = _persist(tenant, workspace, rule_id="TRACE-P1", artifact_ids=("art-1",))
        service = AuditService(engine=_ScopeAwareStubEngine([matching, other]))

        report = service.run_audit(workspace.id, admin_ctx, tier="extended")
        by_rule = {fv.finding.rule_id: fv for fv in report.findings}
        assert by_rule["TRACE-P1"].suppressed is True
        assert by_rule["TRACE-P1"].suppression_reason == _REASON
        assert by_rule["TRACE-P1"].suppression_id == row.id
        assert by_rule["VERIF-P8"].suppressed is False

        counts = report.to_dict()["counts"]
        assert counts["total"] == 2
        assert counts["blockers"] == 2
        assert counts["warnings"] == 0
        assert counts["suppressed"] == 1
        assert counts["suppressed_blockers"] == 1
        # R3-01: the unconditional identity — never an intra-counts inequality.
        assert counts["blockers"] + counts["warnings"] == counts["total"]
        payload = report.to_dict()
        assert payload["total_suppressed_available"] == 1
        assert payload["total_suppressed_blockers_available"] == 1
        assert payload["suppressed_filtered"] == 0

        filtered = service.run_audit(
            workspace.id, admin_ctx, tier="extended", include_suppressed=False
        )
        assert [fv.finding.rule_id for fv in filtered.findings] == ["VERIF-P8"]
        filtered_payload = filtered.to_dict()
        filtered_counts = filtered_payload["counts"]
        assert filtered_counts["total"] == 1
        assert filtered_counts["blockers"] + filtered_counts["warnings"] == filtered_counts["total"]
        # m7: counts describe the window, total_* the full run.
        assert filtered_counts["total"] != filtered_payload["total_findings_available"]
        assert filtered_payload["total_findings_available"] == len(
            filtered.findings
        ) + filtered_payload["suppressed_filtered"]
        assert filtered_payload["suppressed_filtered"] == 1

    def test_expired_suppression_is_not_applied(self, tenant, workspace, admin_ctx):
        """AC-569-10: an expired waiver does not mark the finding, it blocks again."""
        _persist(
            tenant,
            workspace,
            rule_id="TRACE-P1",
            artifact_ids=("art-1",),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))
        report = service.run_audit(workspace.id, admin_ctx, tier="extended")
        assert report.findings[0].suppressed is False
        assert report.to_dict()["counts"]["suppressed"] == 0

    def test_expiry_is_evaluated_at_decision_time_with_injected_now(
        self, tenant, workspace, admin_ctx
    ):
        """AC-569-31: moving ``now`` past the expiry flips the suppression off."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        _persist(
            tenant,
            workspace,
            rule_id="TRACE-P1",
            artifact_ids=("art-1",),
            expires_at=expires_at,
        )
        service = AuditService(engine=_ScopeAwareStubEngine([_blocker()]))

        before = service.run_audit(
            workspace.id, admin_ctx, tier="extended", now=expires_at - timedelta(days=1)
        )
        assert before.findings[0].suppressed is True

        after = service.run_audit(
            workspace.id, admin_ctx, tier="extended", now=expires_at + timedelta(seconds=1)
        )
        assert after.findings[0].suppressed is False

        states = service.list_suppressions(workspace.id, admin_ctx, state="all")
        assert [v.state for v in states] == ["active"]
        expired = service.list_suppressions(
            workspace.id,
            admin_ctx,
            state="all",
            now=expires_at + timedelta(seconds=1),
        )
        assert [v.state for v in expired] == ["expired"]

    def test_suppressed_finding_key_is_the_scoped_identity(
        self, tenant, workspace, admin_ctx
    ):
        """``finding_key`` on the finding stays the scoped key (display identity)."""
        document_finding = _blocker(
            "TRACE-P7", ("a",), scope="document", scope_artifact_id="doc-1"
        )
        _persist(
            tenant,
            workspace,
            rule_id="TRACE-P7",
            artifact_ids=("a",),
            scope="document",
            scope_artifact_id="doc-1",
        )
        service = AuditService(engine=_ScopeAwareStubEngine([document_finding]))
        report = service.run_audit(
            workspace.id,
            admin_ctx,
            tier="extended",
            scopes=[AuditScope("document", artifact_id="doc-1")],
        )
        view = report.findings[0]
        assert view.suppressed is True
        assert view.finding_key == finding_key("TRACE-P7", ("a",), "document")
