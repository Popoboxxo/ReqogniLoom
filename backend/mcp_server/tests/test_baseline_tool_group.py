"""
Real-DB tests for BaselineToolGroup (issue #114).

Covers registration in ToolRegistry (fail-closed RBAC gating for the write
tool `baseline.create` vs the read-only `baseline.list`/`.get`/`.compare`)
plus a create -> list -> get -> compare round-trip against the real
BaselineFacade (application/baseline_facade.py), mirroring
test_diagram_tool_group.py's pattern for other "own" tool groups.

leaf_id : COMP-AS-006 (BaselineFacade), COMP-MC-002 (ToolRegistry)
req_id  : REQ-L1-018, REQ-L2-AS-006, REQ-L2-AS-007, REQ-L2-MC-012
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.baseline import BaselineToolGroup

pytestmark = pytest.mark.django_db


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace (standard preset) + AuthContext for *name*."""
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{name}-ws", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestBaselineToolGroupRegistration:
    def test_baseline_tools_registered_in_registry(self):
        registry = ToolRegistry()
        registry._ensure_groups()

        group, error = registry._router.route("baseline.create")
        assert error is None
        assert isinstance(group, BaselineToolGroup)

        for tool_name in ("baseline.list", "baseline.get", "baseline.compare"):
            group, error = registry._router.route(tool_name)
            assert error is None
            assert isinstance(group, BaselineToolGroup)

    def test_write_tools_require_write_role(self):
        registry = ToolRegistry()
        assert registry._is_write_tool("baseline.create") is True
        assert registry._is_write_tool("baseline.list") is False
        assert registry._is_write_tool("baseline.get") is False
        assert registry._is_write_tool("baseline.compare") is False

    def test_baseline_schemas_exposed(self):
        group = BaselineToolGroup()
        names = {schema["name"] for schema in group.get_tool_schemas()}
        assert names == {
            "baseline.create",
            "baseline.list",
            "baseline.get",
            "baseline.compare",
        }


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------


class TestBaselineToolGroupRoundtrip:
    def test_create_list_get_compare_roundtrip(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-crud")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            create_a = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "v1.0-baseline",
                    "description": "first snapshot",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert create_a.success is True
            baseline_a_id = create_a.data["baseline_id"]

            create_b = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "v2.0-baseline",
                    "description": "second snapshot",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert create_b.success is True
            baseline_b_id = create_b.data["baseline_id"]

            list_result = group._handle_list(
                params={"workspace_id": str(workspace.id)},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert list_result.success is True
            assert list_result.data["count"] == 2
            names = {b["name"] for b in list_result.data["baselines"]}
            assert names == {"v1.0-baseline", "v2.0-baseline"}

            get_result = group._handle_get(
                params={"id": baseline_a_id}, auth_context=ctx, api_key="reqlo_x"
            )
            assert get_result.success is True
            assert get_result.data["baseline"]["name"] == "v1.0-baseline"
            assert get_result.data["baseline"]["scope"] == "project"
            assert "entries" in get_result.data["baseline"]

            compare_result = group._handle_compare(
                params={
                    "baseline_a_id": baseline_a_id,
                    "baseline_b_id": baseline_b_id,
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert compare_result.success is True
            assert "diff" in compare_result.data
        finally:
            TenantContext.clear_tenant()

    def test_create_duplicate_name_returns_validation_error(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-dup")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            first = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "dup-name",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert first.success is True

            second = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "dup-name",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert second.success is False
        assert second.error_code == "VALIDATION_ERROR"

    def test_get_not_found_returns_error(self):
        tenant, _, ctx = _make_tenant_workspace_ctx("baseline-mcp-notfound")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_get(
                params={"id": "00000000-0000-0000-0000-000000009999"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_create_denied_for_viewer(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-viewer")
        viewer_ctx = AuthContext(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            active_roles=("viewer",),
            auth_method="test",
            api_key_id=None,
            tenant_name=ctx.tenant_name,
        )
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "viewer-denied",
                },
                auth_context=viewer_ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"


__all__: list[str] = []
