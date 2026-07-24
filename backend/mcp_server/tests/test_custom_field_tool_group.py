"""
Real-DB tests for CustomFieldToolGroup (Phase 1 Task 6).

Covers registration in ToolRegistry plus read operations (get/query).
Crucially proves that write operations (create/update/delete/outdate) are
deliberately NOT registered.

leaf_id : COMP-MC-006 (CustomField, read-only), COMP-MC-002 (ToolRegistry)
req_id  : REQ-L2-MC-006, REQ-066
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.custom_field import CustomFieldToolGroup

pytestmark = pytest.mark.django_db


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace + AuthContext triple for *name*."""
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
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


class TestCustomFieldToolGroupRegistration:
    def test_custom_field_read_tools_registered_in_registry(self):
        """Prove custom_field.get and custom_field.query are registered."""
        registry = ToolRegistry()
        registry._ensure_groups()

        group, error = registry._router.route("custom_field.get")
        assert error is None
        assert isinstance(group, CustomFieldToolGroup)

        group, error = registry._router.route("custom_field.query")
        assert error is None
        assert isinstance(group, CustomFieldToolGroup)

    def test_custom_field_write_tools_not_registered(self):
        """Prove that write operations are deliberately NOT registered."""
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        registry = ToolRegistry()
        registry._ensure_groups()

        # Only read tools should exist in the tool group
        group, _ = registry._router.route("custom_field.get")
        tool_schemas = group.get_tool_schemas()
        tool_names = {t["name"] for t in tool_schemas}

        # Read tools MUST be present
        assert "custom_field.get" in tool_names
        assert "custom_field.query" in tool_names

        # Write tools MUST NOT be present (intentional design: protect workspace config)
        assert "custom_field.create" not in tool_names
        assert "custom_field.update" not in tool_names
        assert "custom_field.delete" not in tool_names
        assert "custom_field.outdate" not in tool_names

        # Also verify that NO custom_field.* tool is in the write prefixes
        for prefix in _WRITE_TOOL_PREFIXES:
            assert not prefix.startswith("custom_field."), (
                f"custom_field.* tool '{prefix}' should NOT be in _WRITE_TOOL_PREFIXES"
            )

    def test_custom_field_schemas_exposed(self):
        """Prove that only read schemas are exposed."""
        group = CustomFieldToolGroup()
        names = {schema["name"] for schema in group.get_tool_schemas()}
        assert names == {"custom_field.get", "custom_field.query"}

    def test_read_tools_not_marked_as_write(self):
        """Prove that get/query are marked as read-only (not write)."""
        registry = ToolRegistry()
        assert registry._is_write_tool("custom_field.get") is False
        assert registry._is_write_tool("custom_field.query") is False


# ---------------------------------------------------------------------------
# CRUD read operations
# ---------------------------------------------------------------------------


class TestCustomFieldToolGroupRead:
    def test_get_definition_success(self):
        """Prove custom_field.get fetches a definition successfully."""
        tenant, workspace, ctx = _make_tenant_workspace_ctx("cf-read-get")
        group = CustomFieldToolGroup()

        # Create a definition directly (bypass MCP layer)
        from persistence.models import CustomFieldDefinition

        TenantContext.set_tenant(tenant.id)
        try:
            definition = CustomFieldDefinition.objects.create(
                workspace=workspace,
                name="Priority",
                field_type="dropdown",
                is_required=True,
                options=["Low", "Medium", "High"],
                order=1,
                created_by_id=ctx.user_id,
            )

            result = group._handle_get(
                params={"id": str(definition.id)}, auth_context=ctx, api_key="reqlo_x"
            )
            assert result.success is True
            assert result.data["definition"]["name"] == "Priority"
            assert result.data["definition"]["field_type"] == "dropdown"
            assert result.data["definition"]["is_required"] is True
            assert result.data["definition"]["options"] == ["Low", "Medium", "High"]
        finally:
            TenantContext.clear_tenant()

    def test_get_not_found_returns_error(self):
        """Prove custom_field.get returns NOT_FOUND for missing definition."""
        tenant, _, ctx = _make_tenant_workspace_ctx("cf-read-notfound")
        group = CustomFieldToolGroup()

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

    def test_query_definitions_success(self):
        """Prove custom_field.query lists definitions for a workspace."""
        tenant, workspace, ctx = _make_tenant_workspace_ctx("cf-read-query")
        group = CustomFieldToolGroup()

        from persistence.models import CustomFieldDefinition

        TenantContext.set_tenant(tenant.id)
        try:
            def1 = CustomFieldDefinition.objects.create(
                workspace=workspace,
                name="Status",
                field_type="text",
                order=1,
                created_by_id=ctx.user_id,
            )
            def2 = CustomFieldDefinition.objects.create(
                workspace=workspace,
                name="Assigned To",
                field_type="text",
                order=2,
                created_by_id=ctx.user_id,
            )

            result = group._handle_query(
                params={"workspace_id": str(workspace.id)},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert result.success is True
            assert result.data["count"] == 2
            ids = {d["id"] for d in result.data["definitions"]}
            assert str(def1.id) in ids
            assert str(def2.id) in ids
        finally:
            TenantContext.clear_tenant()

    def test_query_empty_workspace(self):
        """Prove custom_field.query returns empty list for workspace with no definitions."""
        tenant, workspace, ctx = _make_tenant_workspace_ctx("cf-read-empty")
        group = CustomFieldToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_query(
                params={"workspace_id": str(workspace.id)},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert result.success is True
            assert result.data["count"] == 0
            assert result.data["definitions"] == []
        finally:
            TenantContext.clear_tenant()


__all__: list[str] = []
