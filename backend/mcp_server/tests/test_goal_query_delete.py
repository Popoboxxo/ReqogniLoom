"""Tests for GitHub issue #216: ``goal.query`` and ``goal.delete``.

``GoalToolGroup`` used to expose neither a discovery tool (``goal.read``
needs an id, ``goal.list_versions`` needs a ``lineage_id`` — no way to
enumerate Goals in a workspace) nor a delete/archive tool, unlike the
sibling ``GenericCrudToolGroup``-based namespaces (adr/risk/issue) which have
both ``.query`` and ``.delete``.

Style mirrors ``test_goal_tools_issue270.py``: drives the real
``GoalService`` through the MCP tool group against the DB.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.goals import GoalToolGroup
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

VALID_API_KEY = "reqlo_testkey1234"


def _ctx(*, tenant_id, roles=("admin",)) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
    )


def _tenant_and_workspace(tenant_name: str, **workspace_kwargs):
    tenant = Tenant.objects.create(name=tenant_name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, **workspace_kwargs)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _provision(workspace, *, preset: str, item_type: str) -> None:
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# goal.query
# ---------------------------------------------------------------------------


def test_goal_query_lists_current_version_per_lineage():
    tenant, workspace = _tenant_and_workspace("I216-Q1", name="W1", goals_enabled=True)
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    first = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "Goal A"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert first.success is True
    group.execute_tool(
        tool_name="goal.create_version",
        params={
            "workspace_id": str(workspace.id),
            "lineage_id": first.data["lineage_id"],
            "title": "Goal A revised",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "Goal B"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    result = group.execute_tool(
        tool_name="goal.query",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True
    titles = sorted(g["title"] for g in result.data["goals"])
    assert titles == ["Goal A revised", "Goal B"]


def test_goal_query_excludes_archived_by_default_and_includes_on_request():
    tenant, workspace = _tenant_and_workspace("I216-Q2", name="W2", goals_enabled=True)
    _provision(workspace, preset="goal_default", item_type="Goal")
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "Goal to archive"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": created.data["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    default_result = group.execute_tool(
        tool_name="goal.query",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert default_result.data["goals"] == []

    with_archived = group.execute_tool(
        tool_name="goal.query",
        params={"workspace_id": str(workspace.id), "include_archived": True},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert [g["status"] for g in with_archived.data["goals"]] == ["Archiviert"]


def test_goal_query_requires_workspace_id():
    tenant, _workspace = _tenant_and_workspace("I216-Q3", name="W3")
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.query",
        params={},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is False


def test_goal_query_is_registered_as_read_only():
    """``.query`` is exempt from the WRITE RBAC gate via the shared suffix
    convention (tool_registry._READ_ONLY_TOOL_SUFFIXES); pin it so a future
    refactor of that convention doesn't silently write-gate goal.query."""
    registry = ToolRegistry()
    assert registry._is_write_tool("goal.query") is False


# ---------------------------------------------------------------------------
# goal.delete
# ---------------------------------------------------------------------------


def test_goal_delete_archives_a_draft_goal():
    tenant, workspace = _tenant_and_workspace("I216-D1", name="W4", goals_enabled=True)
    _provision(workspace, preset="goal_default", item_type="Goal")
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "Goal A"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert created.data["status"] == "Entwurf"

    result = group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": created.data["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["status"] == "Archiviert"
    assert result.data["id"] == created.data["id"]

    read = group.execute_tool(
        tool_name="goal.read",
        params={"goal_id": created.data["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert read.data["status"] == "Archiviert"


def test_goal_delete_archives_an_approved_goal():
    tenant, workspace = _tenant_and_workspace("I216-D2", name="W5", goals_enabled=True)
    _provision(workspace, preset="goal_default", item_type="Goal")
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "Goal A"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    group.execute_tool(
        tool_name="goal.transition",
        params={
            "goal_id": created.data["id"],
            "target_state": "Freigegeben",
            "change_reason": "Approved.",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    result = group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": created.data["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["status"] == "Archiviert"


def test_goal_delete_rejects_role_without_approver_permission():
    tenant, workspace = _tenant_and_workspace("I216-D3", name="W6", goals_enabled=True)
    _provision(workspace, preset="goal_default", item_type="Goal")
    admin_ctx = _ctx(tenant_id=tenant.id)
    editor_ctx = _ctx(tenant_id=tenant.id, roles=("editor",))
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "Goal A"},
        auth_context=admin_ctx,
        api_key=VALID_API_KEY,
    )

    result = group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": created.data["id"]},
        auth_context=editor_ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_goal_delete_unknown_id_returns_not_found():
    tenant, _workspace = _tenant_and_workspace("I216-D4", name="W7")
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": str(uuid.uuid4())},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_goal_delete_is_reversible_via_transition():
    """Archived is not terminal — goal.transition back to Entwurf still
    works (mirrors the pre-existing Archiviert -> Entwurf reactivation
    edge), unlike a hard DELETE which would lose the row."""
    tenant, workspace = _tenant_and_workspace("I216-D5", name="W8", goals_enabled=True)
    _provision(workspace, preset="goal_default", item_type="Goal")
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "Goal A"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": created.data["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    result = group.execute_tool(
        tool_name="goal.transition",
        params={
            "goal_id": created.data["id"],
            "target_state": "Entwurf",
            "change_reason": "Restore.",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is True, result.message
    assert result.data["status"] == "Entwurf"
