"""
Real-DB tests for DiagramToolGroup (Phase 1 Task 5).

Covers registration in ToolRegistry plus a create -> outdate -> query ->
reactivate round-trip. Diagram has no denormalized status mirror field
(REQ-066/REQ-173) — soft-delete state lives only in WorkflowItemState, so
these tests assert against that table directly, mirroring
test_own_tool_groups_lifecycle.py's pattern for the other "own" tool groups.

leaf_id : COMP-DS-001 (DiagramManager), COMP-MC-002 (ToolRegistry)
req_id  : REQ-L2-DS-001, REQ-L3-DM-001..004, REQ-066, REQ-173
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.diagram import DiagramToolGroup

pytestmark = pytest.mark.django_db

VALID_JSON_BLOCK = '{"nodes": [{"id": "A", "label": "Block A"}]}'
VALID_JSON_BLOCK_V2 = '{"nodes": [{"id": "A", "label": "Block A v2"}]}'


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


def _ensure_workflow(tenant, workspace, preset: str, item_type: str) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestDiagramToolGroupRegistration:
    def test_diagram_tools_registered_in_registry(self):
        registry = ToolRegistry()
        registry._ensure_groups()

        group, error = registry._router.route("diagram.create")
        assert error is None
        assert isinstance(group, DiagramToolGroup)

    def test_write_tools_require_write_role(self):
        registry = ToolRegistry()
        assert registry._is_write_tool("diagram.create") is True
        assert registry._is_write_tool("diagram.update") is True
        assert registry._is_write_tool("diagram.outdate") is True
        assert registry._is_write_tool("diagram.reactivate") is True
        assert registry._is_write_tool("diagram.get") is False
        assert registry._is_write_tool("diagram.query") is False

    def test_diagram_schemas_exposed(self):
        group = DiagramToolGroup()
        names = {schema["name"] for schema in group.get_tool_schemas()}
        assert names == {
            "diagram.create",
            "diagram.get",
            "diagram.update",
            "diagram.query",
            "diagram.outdate",
            "diagram.reactivate",
        }


# ---------------------------------------------------------------------------
# Tool-group-level RBAC (Systemaudit #102)
# ---------------------------------------------------------------------------


class TestDiagramToolGroupWritePermission:
    """diagram/services.py takes no AuthContext and checks nothing itself, so
    DiagramToolGroup must gate write handlers directly (defense-in-depth
    alongside the registry-level fail-closed default from Systemaudit #99).
    """

    def test_create_denied_for_viewer(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("diag-mcp-viewer-c")
        viewer_ctx = AuthContext(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            active_roles=("viewer",),
            auth_method="test",
            api_key_id=None,
            tenant_name=ctx.tenant_name,
        )
        group = DiagramToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "name": "Block Diagram",
                    "diagram_type": "block",
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK,
                },
                auth_context=viewer_ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_update_denied_for_viewer(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("diag-mcp-viewer-u")
        group = DiagramToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            create_result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "name": "Block Diagram",
                    "diagram_type": "block",
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK,
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            diagram_id = create_result.data["diagram"]["id"]

            viewer_ctx = AuthContext(
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                active_roles=("viewer",),
                auth_method="test",
                api_key_id=None,
                tenant_name=ctx.tenant_name,
            )
            result = group._handle_update(
                params={
                    "id": diagram_id,
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK_V2,
                },
                auth_context=viewer_ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# CRUD + lifecycle round-trip
# ---------------------------------------------------------------------------


class TestDiagramToolGroupCrud:
    def test_create_get_update_roundtrip(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("diag-mcp-crud")
        group = DiagramToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            create_result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "name": "Block Diagram",
                    "diagram_type": "block",
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK,
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert create_result.success is True
            diagram_id = create_result.data["diagram"]["id"]
            assert create_result.data["diagram"]["workspace_id"] == str(workspace.id)

            get_result = group._handle_get(
                params={"id": diagram_id}, auth_context=ctx, api_key="reqlo_x"
            )
            assert get_result.success is True
            assert get_result.data["diagram"]["content"] == VALID_JSON_BLOCK
            assert get_result.data["diagram"]["version_number"] == 1

            update_result = group._handle_update(
                params={
                    "id": diagram_id,
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK_V2,
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert update_result.success is True
            assert update_result.data["diagram"]["version_number"] == 2
            assert update_result.data["diagram"]["content"] == VALID_JSON_BLOCK_V2
        finally:
            TenantContext.clear_tenant()

    def test_create_invalid_payload_returns_validation_error(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("diag-mcp-invalid")
        group = DiagramToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "name": "Bad Diagram",
                    "diagram_type": "block",
                    "payload_format": "json",
                    "content": "not valid json {{{",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_get_not_found_returns_error(self):
        tenant, _, ctx = _make_tenant_workspace_ctx("diag-mcp-notfound")
        group = DiagramToolGroup()

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


class TestDiagramToolGroupLifecycle:
    def test_outdate_then_reactivate_roundtrip(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("diag-mcp-lifecycle")
        _ensure_workflow(tenant, workspace, "diagram_default", "Diagram")
        group = DiagramToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            create_result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "name": "Lifecycle Diagram",
                    "diagram_type": "block",
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK,
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            diagram_id = create_result.data["diagram"]["id"]

            outdate_result = group._handle_outdate(
                params={"id": diagram_id, "reason": "obsolete"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert outdate_result.success is True
            assert outdate_result.data == {"id": diagram_id, "status": "outdated"}

            state = WorkflowItemState.objects.get(
                item_id=diagram_id, item_type="Diagram"
            )
            assert state.current_state == "outdated"

            reactivate_result = group._handle_reactivate(
                params={"id": diagram_id}, auth_context=ctx, api_key="reqlo_x"
            )
            assert reactivate_result.success is True
            assert reactivate_result.data["id"] == diagram_id
            assert reactivate_result.data["status"] != "outdated"
        finally:
            TenantContext.clear_tenant()

    def test_outdate_not_found_returns_error(self):
        tenant, _, ctx = _make_tenant_workspace_ctx("diag-mcp-outdate-notfound")
        group = DiagramToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_outdate(
                params={"id": "00000000-0000-0000-0000-000000009999"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_query_include_deleted_filters(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("diag-mcp-query")
        _ensure_workflow(tenant, workspace, "diagram_default", "Diagram")
        group = DiagramToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            kept = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "name": "Kept",
                    "diagram_type": "block",
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK,
                },
                auth_context=ctx,
                api_key="x",
            ).data["diagram"]["id"]
            deleted = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "name": "Deleted",
                    "diagram_type": "block",
                    "payload_format": "json",
                    "content": VALID_JSON_BLOCK,
                },
                auth_context=ctx,
                api_key="x",
            ).data["diagram"]["id"]

            group._handle_outdate(
                params={"id": deleted}, auth_context=ctx, api_key="x"
            )

            result = group._handle_query(
                params={"workspace_id": str(workspace.id)},
                auth_context=ctx,
                api_key="x",
            )
            ids = {d["id"] for d in result.data["diagrams"]}
            assert kept in ids
            assert deleted not in ids

            result_incl = group._handle_query(
                params={"workspace_id": str(workspace.id), "include_deleted": True},
                auth_context=ctx,
                api_key="x",
            )
            ids_incl = {d["id"] for d in result_incl.data["diagrams"]}
            assert deleted in ids_incl
        finally:
            TenantContext.clear_tenant()


__all__: list[str] = []
