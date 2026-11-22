"""MCP parity for allocation.query and the group tools (P2.9/P6.2)."""
from __future__ import annotations

import pytest

from application.artifact_service import append_sort_key
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _env(slug="mcp-group"):
    tenant = Tenant.objects.create(name=slug, slug=slug)
    user = User.objects.create(
        username=f"{slug}-user", email=f"{slug}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id, tenant_id=tenant.id, active_roles=("editor",), auth_method="test"
    )
    return tenant, workspace, ctx


def _requirement(tenant, workspace, title):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        sort_key=append_sort_key(workspace.id, None, "Requirement"),
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=f"R-{title}",
    )


def test_group_lifecycle_over_mcp():
    tenant, workspace, ctx = _env()
    requirement = _requirement(tenant, workspace, "Req")
    group = CrossCuttingToolGroup()

    created = group.execute_tool(
        "group.create",
        {"workspace_id": str(workspace.id), "title": "Cluster"},
        ctx,
        "test-api-key",
    )
    assert created.success, created.message
    group_id = created.data["group"]["id"]

    added = group.execute_tool(
        "group.add_member",
        {"group_id": group_id, "requirement_id": str(requirement.id)},
        ctx,
        "test-api-key",
    )
    assert added.success, added.message

    members = group.execute_tool(
        "group.members", {"group_id": group_id}, ctx, "test-api-key"
    )
    assert members.success
    assert members.data["members"][0]["requirement_artifact_id"] == str(
        requirement.artifact_id
    )

    listed = group.execute_tool(
        "group.list", {"workspace_id": str(workspace.id)}, ctx, "test-api-key"
    )
    assert listed.success
    assert listed.data["groups"][0]["title"] == "Cluster"


def test_allocation_query_over_mcp():
    tenant, workspace, ctx = _env("mcp-alloc")
    _requirement(tenant, workspace, "Req")

    result = CrossCuttingToolGroup().execute_tool(
        "allocation.query", {"workspace_id": str(workspace.id)}, ctx, "test-api-key"
    )

    assert result.success, result.message
    assert result.data["meta"]["total"] == 1
    assert result.data["results"][0]["title"] == "Req"


# ---------------------------------------------------------------------------
# Issue #1980 — router reachability
#
# The tests above call group.execute_tool() directly and so bypass the router.
# The tools are in _TOOL_MAP and the manifest, but GROUP_SPECS had no `group` or
# `allocation` prefix, so ToolGroupRouter.route() (which matches `prefix.`) sent
# every one of them to UNKNOWN_TOOL at the wire. These pin the router path.
# ---------------------------------------------------------------------------

_GROUP_AND_ALLOCATION_TOOLS = (
    "group.add_member",
    "group.create",
    "group.list",
    "group.members",
    "group.move_member",
    "group.remove_member",
    "allocation.query",
)


def test_router_routes_all_group_and_allocation_tools() -> None:
    registry = ToolRegistry()
    registry._ensure_groups()

    for name in _GROUP_AND_ALLOCATION_TOOLS:
        group, error = registry._router.route(name)
        assert error is None, f"{name}: {error}"
        assert isinstance(group, CrossCuttingToolGroup), name

    # Both prefixes share the one cross_cutting group instance (and its policy).
    assert registry._router.route("group.list")[0] is registry._router.route(
        "allocation.query"
    )[0]


@pytest.mark.django_db
def test_dispatch_request_does_not_report_group_tools_as_unknown(
    e2e_api_key_admin, e2e_userrole_admin, e2e_workspace
) -> None:
    """The exact regression: dispatch_request used to answer UNKNOWN_TOOL."""
    result = ToolRegistry().dispatch_request(
        tool_name="group.list",
        params={"workspace_id": str(e2e_workspace.id)},
        api_key=e2e_api_key_admin,
    )

    assert result.error_code != "UNKNOWN_TOOL", (result.error_code, result.message)
    assert result.success is True, (result.error_code, result.message)
