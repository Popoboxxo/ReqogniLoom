"""
Tests for the SE-Auditor gate on baseline creation (SE-conformance lever 2).

leaf_id : COMP-AS-006 (BaselineFacade) / COMP-AS-AUDIT (AuditService)

The SE-Auditor has shipped BLOCKER-severity rules since SysEng 2.0 Phase 2 but
was only ever exposed as a *report*. ``BaselineFacade.create_baseline`` is its
first enforcement point: a baseline must not freeze a trace graph the
workspace's own rigor preset already declares broken.

Three layers are covered:
  * wiring — the facade consults ``AuditService.blocking_findings`` before
    delegating to ``baseline.services.build``, and fails CLOSED on an auditor
    malfunction (GH-400; mock-level, mirroring ``test_baseline_facade.py``);
  * override — the documented waiver path out of the GH-513 deadlock
    (fail-closed gate + no in-UI way to resolve every finding), including its
    RBAC gate, its justification requirement and its audit trail;
  * tier behaviour — verified against real preset configs and the real
    RuleEngine, not assumed.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.audit_service import AuditService
from application.base import (
    BaselineGateBlockedError,
    PermissionDeniedError,
    ValidationError,
)
from application.baseline_facade import BaselineFacade
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext
from traceability.audit import AuditScope, Finding, Severity

pytestmark = pytest.mark.django_db


WS_ID = uuid.uuid4()


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


def _blocker(rule_id: str = "TRACE-P1") -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.BLOCKER,
        message="Root Requirement has no derives-from link.",
        artifact_ids=("art-1",),
    )


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


class TestBaselineAuditGateWiring:
    def test_blocker_findings_reject_the_build(self):
        facade = BaselineFacade()
        ctx = _make_ctx()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed"
            ),
            patch.object(
                AuditService, "blocking_findings", return_value=[_blocker()]
            ),
            patch("baseline.services.build") as mock_build,
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            with pytest.raises(ValidationError) as exc_info:
                facade.create_baseline(
                    scope="project", workspace_id=WS_ID, name="v1", ctx=ctx
                )

        message = str(exc_info.value)
        assert "TRACE-P1" in message
        assert "art-1" in message
        assert "derives-from" in message
        mock_build.assert_not_called()

    def test_many_blocker_findings_produce_a_bounded_error_message(self):
        """#582: 1000+ BLOCKERs must not inflate the 400 body to 100s of KB.

        ``_summarise_findings`` already caps the enumerated findings at
        ``_MAX_LISTED_FINDINGS`` (see application/baseline_facade.py) — this
        pins that behaviour so a future edit can't silently regress it back
        to an unbounded per-finding dump.
        """
        facade = BaselineFacade()
        ctx = _make_ctx()
        many_findings = [_blocker(rule_id=f"TRACE-P{i}") for i in range(1000)]

        with (
            patch("application.baseline_facade.TenantContext"),
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed"
            ),
            patch.object(
                AuditService, "blocking_findings", return_value=many_findings
            ),
            patch("baseline.services.build") as mock_build,
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            with pytest.raises(BaselineGateBlockedError) as exc_info:
                facade.create_baseline(
                    scope="project", workspace_id=WS_ID, name="v1", ctx=ctx
                )

        message = str(exc_info.value)
        assert len(message) < 5000, (
            f"error message is {len(message)} chars — findings enumeration "
            "is no longer bounded"
        )
        assert "1000 blocking finding(s)" in message
        assert "990 more" in message
        mock_build.assert_not_called()

    def test_clean_audit_allows_the_build(self):
        facade = BaselineFacade()
        ctx = _make_ctx()
        baseline_id = uuid.uuid4()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed"
            ),
            patch.object(AuditService, "blocking_findings", return_value=[]),
            patch("baseline.services.build", return_value=baseline_id) as mock_build,
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            result = facade.create_baseline(
                scope="project", workspace_id=WS_ID, name="v1", ctx=ctx
            )

        assert result == baseline_id
        mock_build.assert_called_once()

    def test_document_scope_is_forwarded_to_the_auditor(self):
        facade = BaselineFacade()
        ctx = _make_ctx()
        doc_id = uuid.uuid4()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed"
            ),
            patch.object(
                AuditService, "blocking_findings", return_value=[]
            ) as mock_audit,
            patch("baseline.services.build", return_value=uuid.uuid4()),
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            facade.create_baseline(
                scope="document",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
                document_id=doc_id,
            )

        scopes = mock_audit.call_args.kwargs["scopes"]
        assert scopes == [AuditScope(scope="document", artifact_id=str(doc_id))]

    def test_auditor_malfunction_fails_closed(self):
        """GH-400: an internal auditor error must BLOCK the build, not open the gate.

        Regression test for the fail-open bug: the gate used to catch any
        non-``ValidationError`` exception from ``AuditService.blocking_findings``,
        log it, and let the baseline build proceed as if the audit had come
        back clean. A security/compliance gate must fail closed when its own
        evaluation is unreliable.
        """
        facade = BaselineFacade()
        ctx = _make_ctx()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed"
            ),
            patch.object(
                AuditService,
                "blocking_findings",
                side_effect=RuntimeError("engine exploded"),
            ),
            patch("baseline.services.build") as mock_build,
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            with pytest.raises(ValidationError) as exc_info:
                facade.create_baseline(
                    scope="project", workspace_id=WS_ID, name="v1", ctx=ctx
                )

        assert "engine exploded" in str(exc_info.value)
        mock_build.assert_not_called()

    def test_warnings_do_not_block(self):
        """Only BLOCKER severity gates; WARNING findings are advisory."""
        engine = MagicMock()
        engine.run.return_value = MagicMock(
            findings=[
                Finding(
                    rule_id="TRACE-P2",
                    severity=Severity.WARNING,
                    message="advisory",
                ),
                _blocker("TRACE-P1b"),
            ]
        )
        service = AuditService(engine=engine)
        ctx = _make_ctx()

        with patch.object(AuditService, "_set_tenant_context"), patch.object(
            AuditService, "resolve_tier", return_value="standard"
        ):
            findings = service.blocking_findings(WS_ID, ctx)

        assert [f.rule_id for f in findings] == ["TRACE-P1b"]


# ---------------------------------------------------------------------------
# Override / waiver (GH-513)
# ---------------------------------------------------------------------------


class TestBaselineAuditGateOverride:
    """The documented way out of the GH-513 deadlock.

    Before this, a workspace with at least one BLOCKER could neither produce a
    baseline (fail-closed gate, GH-490) nor resolve every finding through the
    Auditor UI (only findings with an unambiguous automatic remediation offer
    an "Adopt" button; GH-451). The gate stays fail-closed by default — the
    escape hatch is an explicit, RBAC-gated, audit-logged waiver.
    """

    @staticmethod
    def _gate_patches(*, findings, build_result=None):
        return (
            patch("application.baseline_facade.TenantContext"),
            patch("application.baseline_facade.BaselineFacade._check_scope_allowed"),
            patch.object(AuditService, "blocking_findings", return_value=findings),
            patch(
                "baseline.services.build",
                return_value=build_result or uuid.uuid4(),
            ),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        )

    def test_block_message_points_at_the_override_path(self):
        """A dead end must at least document its own exit (GH-513)."""
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("admin",))
        p1, p2, p3, p4, p5 = self._gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4, p5, patch(
            "application.baseline_facade.ServiceBase._audit"
        ):
            with pytest.raises(BaselineGateBlockedError) as exc_info:
                facade.create_baseline(
                    scope="project", workspace_id=WS_ID, name="v1", ctx=ctx
                )

        assert "override_reason" in str(exc_info.value)

    def test_blocked_error_is_a_validation_error_subclass(self):
        """Existing ``except ValidationError`` callers must keep working."""
        assert issubclass(BaselineGateBlockedError, ValidationError)

    def test_admin_override_with_justification_builds_the_baseline(self):
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("admin",))
        baseline_id = uuid.uuid4()
        p1, p2, p3, p4, p5 = self._gate_patches(
            findings=[_blocker(), _blocker("VERIF-P8")], build_result=baseline_id
        )

        with p1, p2, p3, p4 as mock_build, p5, patch(
            "application.baseline_facade.ServiceBase._audit"
        ) as mock_audit:
            result = facade.create_baseline(
                scope="project",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
                override_reason="Release 1.6 cut agreed with QA; findings tracked in GH-513.",
            )

        assert result == baseline_id
        mock_build.assert_called_once()

        details = mock_audit.call_args.kwargs["details"]
        assert details["audit_gate_override"] is True
        assert details["waived_blocker_count"] == 2
        assert sorted(details["waived_rule_ids"]) == ["TRACE-P1", "VERIF-P8"]
        assert (
            mock_audit.call_args.kwargs["change_reason"]
            == "Release 1.6 cut agreed with QA; findings tracked in GH-513."
        )

    def test_override_is_recorded_in_the_baseline_description(self):
        """The waiver must be visible on the artefact it was granted for."""
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("admin",))
        p1, p2, p3, p4, p5 = self._gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, patch(
            "application.baseline_facade.ServiceBase._audit"
        ):
            facade.create_baseline(
                scope="project",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
                description="Release candidate",
                override_reason="Waived for the beta cut, tracked in GH-513.",
            )

        description = mock_build.call_args.kwargs["description"]
        assert description.startswith("Release candidate")
        assert "SE-Auditor override" in description
        assert "Waived for the beta cut" in description
        assert "TRACE-P1" in description

    def test_editor_may_not_override(self):
        """Waiving a governance gate needs approval authority, not write access."""
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("editor",))
        p1, p2, p3, p4, p5 = self._gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, patch(
            "application.baseline_facade.ServiceBase._audit"
        ):
            with pytest.raises(PermissionDeniedError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=WS_ID,
                    name="v1",
                    ctx=ctx,
                    override_reason="We really need this baseline for the demo.",
                )

        mock_build.assert_not_called()

    def test_approver_may_override(self):
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("approver",))
        p1, p2, p3, p4, p5 = self._gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, patch(
            "application.baseline_facade.ServiceBase._audit"
        ):
            facade.create_baseline(
                scope="project",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
                override_reason="Accepted deviation, see review protocol 2026-08-15.",
            )

        mock_build.assert_called_once()

    @pytest.mark.parametrize("reason", ["", "   ", "ok", "  fix later  "])
    def test_a_non_justification_is_rejected(self, reason):
        """An empty or throwaway reason is not an auditable waiver."""
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("admin",))
        p1, p2, p3, p4, p5 = self._gate_patches(findings=[_blocker()])

        with p1, p2, p3, p4 as mock_build, p5, patch(
            "application.baseline_facade.ServiceBase._audit"
        ):
            with pytest.raises(ValidationError):
                facade.create_baseline(
                    scope="project",
                    workspace_id=WS_ID,
                    name="v1",
                    ctx=ctx,
                    override_reason=reason,
                )

        mock_build.assert_not_called()

    def test_auditor_malfunction_is_not_overridable(self):
        """An unknown verdict stays fail-closed — a waiver waives *known* findings.

        GH-400's fail-closed rule is about the gate being unevaluable; there is
        nothing to justify because nobody knows what would be waived.
        """
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("admin",))

        with (
            patch("application.baseline_facade.TenantContext"),
            patch("application.baseline_facade.BaselineFacade._check_scope_allowed"),
            patch.object(
                AuditService,
                "blocking_findings",
                side_effect=RuntimeError("engine exploded"),
            ),
            patch("baseline.services.build") as mock_build,
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            with pytest.raises(ValidationError) as exc_info:
                facade.create_baseline(
                    scope="project",
                    workspace_id=WS_ID,
                    name="v1",
                    ctx=ctx,
                    override_reason="We accept the risk for the beta cut.",
                )

        assert not isinstance(exc_info.value, BaselineGateBlockedError)
        mock_build.assert_not_called()

    def test_override_reason_on_a_clean_workspace_is_inert(self):
        """Nothing was waived, so nothing is recorded as waived."""
        facade = BaselineFacade()
        ctx = _make_ctx(roles=("admin",))
        p1, p2, p3, p4, p5 = self._gate_patches(findings=[])

        with p1, p2, p3, p4 as mock_build, p5, patch(
            "application.baseline_facade.ServiceBase._audit"
        ) as mock_audit:
            facade.create_baseline(
                scope="project",
                workspace_id=WS_ID,
                name="v1",
                ctx=ctx,
                description="Release candidate",
                override_reason="Unnecessary justification.",
            )

        assert "audit_gate_override" not in mock_audit.call_args.kwargs["details"]
        assert mock_build.call_args.kwargs["description"] == "Release candidate"


# ---------------------------------------------------------------------------
# Tier behaviour (real presets, real RuleEngine)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_preset_cache():
    yield
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="bl-gate-tenant", slug="bl-gate-tenant")


def _workspace(tenant: Tenant, tier: str) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant,
            name=f"bl-{tier}-{uuid.uuid4().hex[:6]}",
            preset={"name": tier},
        )
    finally:
        TenantContext.clear_tenant()


def _orphan_requirement(tenant: Tenant, ws: Workspace) -> Requirement:
    """A Requirement with no derives-from link — a guaranteed TRACE-P1 BLOCKER."""
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="Orphan requirement"
        )
    finally:
        TenantContext.clear_tenant()


def _ctx(tenant: Tenant) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method="test",
    )


class TestTierBehaviour:
    def test_minimal_tier_ruleset_is_structurally_empty(self):
        from traceability.audit.registry import active_rule_ids_for_tier

        assert active_rule_ids_for_tier("minimal") == frozenset()
        assert active_rule_ids_for_tier("standard")
        assert active_rule_ids_for_tier("extended") >= active_rule_ids_for_tier(
            "standard"
        )

    def test_minimal_tier_reports_no_blockers_even_on_a_broken_graph(
        self, tenant
    ):
        ws = _workspace(tenant, "minimal")
        _orphan_requirement(tenant, ws)

        findings = AuditService().blocking_findings(
            ws.id, _ctx(tenant), scopes=[AuditScope("project")]
        )

        assert findings == []

    def test_extended_tier_reports_blockers_on_the_same_graph(self, tenant):
        ws = _workspace(tenant, "extended")
        _orphan_requirement(tenant, ws)

        findings = AuditService().blocking_findings(
            ws.id, _ctx(tenant), scopes=[AuditScope("project")]
        )

        assert findings, "expected TRACE-P1/P1b blockers for an orphan requirement"
        assert all(f.severity is Severity.BLOCKER for f in findings)

    def test_extended_baseline_build_is_rejected_on_a_broken_graph(self, tenant):
        ws = _workspace(tenant, "extended")
        _orphan_requirement(tenant, ws)

        with pytest.raises(ValidationError) as exc_info:
            BaselineFacade().create_baseline(
                scope="project",
                workspace_id=ws.id,
                name="v1",
                ctx=_ctx(tenant),
            )

        assert "SE-Auditor reported" in str(exc_info.value)

    def test_extended_baseline_build_succeeds_on_a_clean_workspace(self, tenant):
        ws = _workspace(tenant, "extended")

        baseline_id = BaselineFacade().create_baseline(
            scope="project", workspace_id=ws.id, name="v1", ctx=_ctx(tenant)
        )

        assert baseline_id is not None

    def test_broken_graph_is_releasable_with_a_documented_override(self, tenant):
        """GH-513 end-to-end: the deadlock has an exit, on real rules.

        Same broken graph as
        ``test_extended_baseline_build_is_rejected_on_a_broken_graph`` — the
        only difference is the justification.
        """
        ws = _workspace(tenant, "extended")
        _orphan_requirement(tenant, ws)

        baseline_id = BaselineFacade().create_baseline(
            scope="project",
            workspace_id=ws.id,
            name="v1-waived",
            ctx=_ctx(tenant),
            override_reason="Beta cut; open trace findings tracked in GH-513.",
        )

        assert baseline_id is not None

        from baseline.models import BaselineSnapshot

        TenantContext.set_tenant(tenant.id)
        try:
            snapshot = BaselineSnapshot.objects.get(id=baseline_id)
        finally:
            TenantContext.clear_tenant()
        assert "SE-Auditor override" in snapshot.description
