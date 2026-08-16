"""MCP prompt_variable tool group (spec §3.1)."""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="PVT Tenant", slug="pvt-tenant")
    user = User.objects.create(username="pvt-user", email="pvt@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PVT WS")
        admin = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        viewer = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("viewer",),
            auth_method="test",
        )
        yield admin, viewer, workspace
    finally:
        TenantContext.clear_tenant()


def _group():
    from mcp_server.tools.prompt_variable import PromptVariableToolGroup

    return PromptVariableToolGroup()


def test_schema_declares_all_four_tools():
    names = {s["name"] for s in _group().get_tool_schemas()}

    assert names == {
        "prompt_variable.list",
        "prompt_variable.get",
        "prompt_variable.set",
        "prompt_variable.clear",
    }


def test_list_returns_the_catalog(ctx_workspace):
    admin, _viewer, workspace = ctx_workspace

    result = _group()._handle_list(
        params={"workspace_id": str(workspace.id)}, auth_context=admin, api_key="k"
    )

    assert result.success is True
    assert result.data["count"] == len(result.data["variables"])


def test_set_creates_a_new_config_variable(ctx_workspace):
    admin, _viewer, _ws = ctx_workspace

    result = _group()._handle_set(
        params={"name": "review_depth_hint", "value": "be thorough", "var_type": "str"},
        auth_context=admin,
        api_key="k",
    )

    assert result.success is True
    assert result.data["variable"]["effective_value"] == "be thorough"


def test_set_is_admin_gated(ctx_workspace):
    _admin, viewer, _ws = ctx_workspace

    result = _group()._handle_set(
        params={"name": "review_depth_hint", "value": "x"},
        auth_context=viewer,
        api_key="k",
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_set_rejects_a_data_variable(ctx_workspace):
    admin, _viewer, _ws = ctx_workspace

    result = _group()._handle_set(
        params={"name": "req_title", "value": "nope"}, auth_context=admin, api_key="k"
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_reports_not_found_for_an_unknown_name(ctx_workspace):
    admin, _viewer, _ws = ctx_workspace

    result = _group()._handle_get(
        params={"name": "does_not_exist"}, auth_context=admin, api_key="k"
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_clear_rejects_a_data_variable(ctx_workspace):
    admin, _viewer, _ws = ctx_workspace

    result = _group()._handle_clear(
        params={"name": "req_title"}, auth_context=admin, api_key="k"
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_clear_returns_the_now_effective_state(ctx_workspace):
    admin, _viewer, workspace = ctx_workspace
    group = _group()
    group._handle_set(
        params={"name": "review_depth_hint", "value": "tenant", "var_type": "str"},
        auth_context=admin,
        api_key="k",
    )
    group._handle_set(
        params={
            "name": "review_depth_hint",
            "value": "ws",
            "workspace_id": str(workspace.id),
        },
        auth_context=admin,
        api_key="k",
    )

    result = group._handle_clear(
        params={"name": "review_depth_hint", "workspace_id": str(workspace.id)},
        auth_context=admin,
        api_key="k",
    )

    assert result.data["variable"]["effective_value"] == "tenant"


def test_write_tools_are_registered_as_writes():
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert "prompt_variable.set" in _WRITE_TOOL_PREFIXES
    assert "prompt_variable.clear" in _WRITE_TOOL_PREFIXES
