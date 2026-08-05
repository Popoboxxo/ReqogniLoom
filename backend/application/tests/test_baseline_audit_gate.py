"""
Tests for the SE-Auditor gate on baseline creation (SE-conformance lever 2).

leaf_id : COMP-AS-006 (BaselineFacade) / COMP-AS-AUDIT (AuditService)

The SE-Auditor has shipped BLOCKER-severity rules since SysEng 2.0 Phase 2 but
was only ever exposed as a *report*. ``BaselineFacade.create_baseline`` is its
first enforcement point: a baseline must not freeze a trace graph the
workspace's own rigor preset already declares broken.

Two layers are covered:
  * wiring — the facade consults ``AuditService.blocking_findings`` before
    delegating to ``baseline.services.build``, and fails open on an auditor
    malfunction (mock-level, mirroring ``test_baseline_facade.py``);
  * tier behaviour — verified against real preset configs and the real
    RuleEngine, not assumed.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.audit_service import AuditService
from application.base import ValidationError
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

    def test_auditor_malfunction_fails_open(self):
        """An internal auditor error must not make baselining impossible."""
        facade = BaselineFacade()
        ctx = _make_ctx()
        baseline_id = uuid.uuid4()

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
            patch("baseline.services.build", return_value=baseline_id) as mock_build,
            patch("application.baseline_facade.ServiceBase._audit"),
            patch("application.baseline_facade.ServiceBase._emit_event"),
        ):
            result = facade.create_baseline(
                scope="project", workspace_id=WS_ID, name="v1", ctx=ctx
            )

        assert result == baseline_id
        mock_build.assert_called_once()

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
