"""#402 — ``scenario_kind`` at the service and MCP-tool level.

Complements ``rest_api/tests/test_testcase_scenario_kind_402.py`` (HTTP surface)
and ``traceability/tests/test_val_p1_402.py`` (the VAL-P1 rule). The category is
additive metadata with no enforcement rule in this cluster (spec F2).
"""
from __future__ import annotations

import pytest

from persistence.models import ScenarioKind

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-402-sk", slug="t-402-sk")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-402-sk")
    user = User.objects.create(
        username="u-402-sk", email="u-402-sk@example.com", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, workspace, user, ctx


def test_service_default_is_nominal(env):
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    tc = TestService().create_test_case(workspace_id=workspace.id, title="TC", ctx=ctx)
    assert tc.scenario_kind == ScenarioKind.NOMINAL


def test_service_accepts_off_nominal(env):
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    tc = TestService().create_test_case(
        workspace_id=workspace.id,
        title="TC",
        ctx=ctx,
        scenario_kind=ScenarioKind.OFF_NOMINAL,
    )
    assert tc.scenario_kind == ScenarioKind.OFF_NOMINAL


def test_service_rejects_an_unknown_scenario_kind(env):
    from application.base import ValidationError
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    with pytest.raises(ValidationError):
        TestService().create_test_case(
            workspace_id=workspace.id, title="TC", ctx=ctx, scenario_kind="bogus"
        )


def test_service_update_changes_scenario_kind(env):
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    service = TestService()
    tc = service.create_test_case(workspace_id=workspace.id, title="TC", ctx=ctx)

    updated = service.update_test_case(
        tc.id, ctx, scenario_kind=ScenarioKind.OFF_NOMINAL
    )
    assert updated.scenario_kind == ScenarioKind.OFF_NOMINAL
    assert updated.version > tc.version


def test_mcp_create_and_update_expose_scenario_kind(env):
    from mcp_server.tools.tests import McpTestToolGroup

    _tenant, workspace, _user, ctx = env
    group = McpTestToolGroup()

    created = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "Negative path",
            "scenario_kind": "off_nominal",
        },
        auth_context=ctx,
        api_key="test",
    )
    assert created.success, created.message
    payload = created.data["test_case"]
    assert payload["scenario_kind"] == ScenarioKind.OFF_NOMINAL

    updated = group._handle_update(
        params={
            "id": payload["id"],
            "data": {"scenario_kind": "nominal"},
        },
        auth_context=ctx,
        api_key="test",
    )
    assert updated.success, updated.message
    assert updated.data["test_case"]["scenario_kind"] == ScenarioKind.NOMINAL


def test_mcp_create_rejects_an_unknown_scenario_kind(env):
    from mcp_server.tools.tests import McpTestToolGroup

    _tenant, workspace, _user, ctx = env
    result = McpTestToolGroup()._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "Bad",
            "scenario_kind": "bogus",
        },
        auth_context=ctx,
        api_key="test",
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
