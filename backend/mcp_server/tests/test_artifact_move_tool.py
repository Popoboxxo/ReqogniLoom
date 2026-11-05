"""P1 Task 1.4: MCP ``artifact.move`` parity with the REST move endpoint."""
from __future__ import annotations

import pytest
from django.db.models import F

from application.artifact_service import append_sort_key
from auth_tenancy.context import AuthContext
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
from persistence.models import Artifact, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def _env():
    tenant = Tenant.objects.create(name="mcp-move", slug="mcp-move")
    user = User.objects.create(
        username="mcp-move-user", email="mcp-move@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="mcp-move-ws")
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )
    return tenant, workspace, ctx


def _artifact(tenant, workspace, parent=None):
    parent_id = parent.id if parent is not None else None
    return Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        parent=parent,
        sort_key=append_sort_key(workspace.id, parent_id, "Requirement"),
    )


def _children(parent):
    return list(
        Artifact.unscoped.filter(parent_id=parent.id).order_by(
            F("sort_key").asc(nulls_last=True), "created_at", "id"
        )
    )


def test_artifact_move_reorders_and_reports_key():
    tenant, workspace, ctx = _env()
    root = _artifact(tenant, workspace)
    a = _artifact(tenant, workspace, parent=root)
    b = _artifact(tenant, workspace, parent=root)
    c = _artifact(tenant, workspace, parent=root)

    result = CrossCuttingToolGroup().execute_tool(
        "artifact.move",
        {
            "artifact_id": str(c.id),
            "parent_id": str(root.id),
            "after_id": str(a.id),
        },
        ctx,
        "test-api-key",
    )

    assert result.success, result.message
    assert result.data["artifact"]["id"] == str(c.id)
    assert result.data["artifact"]["sort_key"]
    assert [row.id for row in _children(root)] == [a.id, c.id, b.id]


def test_artifact_move_omitted_after_appends():
    tenant, workspace, ctx = _env()
    root = _artifact(tenant, workspace)
    a = _artifact(tenant, workspace, parent=root)
    _artifact(tenant, workspace, parent=root)

    result = CrossCuttingToolGroup().execute_tool(
        "artifact.move",
        {"artifact_id": str(a.id), "parent_id": str(root.id)},
        ctx,
        "test-api-key",
    )

    assert result.success, result.message
    assert _children(root)[-1].id == a.id


def test_artifact_move_maps_validation_error():
    tenant, workspace, ctx = _env()
    root = _artifact(tenant, workspace)
    child = _artifact(tenant, workspace, parent=root)
    stranger = _artifact(tenant, workspace)

    result = CrossCuttingToolGroup().execute_tool(
        "artifact.move",
        {
            "artifact_id": str(child.id),
            "parent_id": str(root.id),
            "after_id": str(stranger.id),
        },
        ctx,
        "test-api-key",
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_artifact_move_maps_not_found():
    _tenant, _workspace, ctx = _env()
    result = CrossCuttingToolGroup().execute_tool(
        "artifact.move",
        {"artifact_id": "00000000-0000-0000-0000-000000000000", "parent_id": None},
        ctx,
        "test-api-key",
    )
    assert not result.success
    assert result.error_code == "NOT_FOUND"
