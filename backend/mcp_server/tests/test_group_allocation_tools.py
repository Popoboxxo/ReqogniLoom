"""MCP parity for allocation.query and the group tools (P2.9/P6.2)."""
from __future__ import annotations

import pytest

from application.artifact_service import append_sort_key
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
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
