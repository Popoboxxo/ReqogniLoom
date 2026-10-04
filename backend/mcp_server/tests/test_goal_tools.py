"""Tests for Goal/MainGoal MCP tool groups (Task 7 of feat/ziele-hauptziel-design).

leaf_id : (Task 7 of feat/ziele-hauptziel-design)
req_id  : REQ-L2-TE-020

Mirrors the registration-smoke-test style used throughout
``mcp_server/tests/test_tool_registry.py`` (e.g.
``test_change_request_tools_registered``): build a real ``ToolRegistry``,
force group registration via ``_ensure_groups()``, and assert on tool
presence / the fail-closed write gate (``_is_write_tool``) rather than
inventing new public API surface that doesn't exist on ``ToolRegistry``.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from application.base import OptimisticLockError, PermissionDeniedError
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.goals import GoalToolGroup, MainGoalToolGroup


def _registered_tool_names(registry: ToolRegistry) -> set[str]:
    registry._ensure_groups()
    names: set[str] = set()
    seen_group_ids: set[int] = set()
    for group in registry._groups.values():
        if id(group) in seen_group_ids:
            continue
        seen_group_ids.add(id(group))
        names.update(t["name"] for t in group.get_tool_schemas())
    return names


@pytest.mark.django_db
def test_goal_tools_registered():
    registry = ToolRegistry()
    names = _registered_tool_names(registry)
    assert "goal.read" in names
    assert "goal.create" in names
    assert "goal.create_version" in names
    assert "goal.list_versions" in names
    assert "goal.transition" in names


@pytest.mark.django_db
def test_main_goal_tools_registered():
    registry = ToolRegistry()
    names = _registered_tool_names(registry)
    assert "main_goal.read" in names
    assert "main_goal.generate" in names
    assert "main_goal.create_manual" in names
    assert "main_goal.approve" in names
    assert "main_goal.list_versions" in names


@pytest.mark.django_db
def test_goal_read_tool_is_read_only():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("goal.read") is False


@pytest.mark.django_db
def test_goal_create_tool_is_write_protected():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("goal.create") is True


@pytest.mark.django_db
def test_goal_create_version_tool_is_write_protected():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("goal.create_version") is True


@pytest.mark.django_db
def test_goal_transition_tool_is_write_protected():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("goal.transition") is True


@pytest.mark.django_db
def test_goal_list_versions_tool_is_read_only():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("goal.list_versions") is False


@pytest.mark.django_db
def test_main_goal_read_tool_is_read_only():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("main_goal.read") is False


@pytest.mark.django_db
def test_main_goal_list_versions_tool_is_read_only():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("main_goal.list_versions") is False


@pytest.mark.django_db
def test_main_goal_generate_tool_is_write_protected():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("main_goal.generate") is True


@pytest.mark.django_db
def test_main_goal_create_manual_tool_is_write_protected():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("main_goal.create_manual") is True


@pytest.mark.django_db
def test_main_goal_approve_tool_is_write_protected():
    registry = ToolRegistry()
    registry._ensure_groups()
    assert registry._is_write_tool("main_goal.approve") is True


@pytest.mark.django_db
def test_no_duplicate_tool_names_with_goal_groups_registered():
    """Sanity check mirroring test_no_duplicate_names_across_full_registry:
    goal/main_goal must not collide with any existing prefix."""
    registry = ToolRegistry()
    registry._ensure_groups()
    names: list[str] = []
    seen_group_ids: set[int] = set()
    for group in registry._groups.values():
        if id(group) in seen_group_ids:
            continue
        seen_group_ids.add(id(group))
        names.extend(t["name"] for t in group.get_tool_schemas())
    assert len(names) == len(set(names)), (
        f"duplicate tool names: {[n for n in names if names.count(n) > 1]}"
    )


# ---------------------------------------------------------------------------
# PermissionDeniedError handling (round-1 fix for reviewer Finding 1)
#
# GoalService/MainGoalService are instantiated inline inside each handler
# (no constructor injection point), so the service classes are patched at
# their `mcp_server.tools.goals` import location, matching the approach used
# for other tool groups without service injection.
# ---------------------------------------------------------------------------

VIEWER_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("viewer",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

WORKSPACE_UUID = UUID("00000000-0000-0000-0000-000000000010")
LINEAGE_UUID = UUID("00000000-0000-0000-0000-000000000011")
MAIN_GOAL_UUID = UUID("00000000-0000-0000-0000-000000000012")
GOAL_UUID = UUID("00000000-0000-0000-0000-000000000013")
VALID_API_KEY = "reqlo_testkey1234"


@pytest.mark.django_db
@patch("mcp_server.tools.goals.GoalService")
def test_goal_create_permission_denied(mock_service_cls):
    mock_service_cls.return_value.create_version.side_effect = PermissionDeniedError(
        "no write"
    )
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(WORKSPACE_UUID), "title": "X"},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
@patch("mcp_server.tools.goals.GoalService")
def test_goal_create_version_permission_denied(mock_service_cls):
    mock_service_cls.return_value.create_version.side_effect = PermissionDeniedError(
        "no write"
    )
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.create_version",
        params={
            "workspace_id": str(WORKSPACE_UUID),
            "lineage_id": str(LINEAGE_UUID),
            "title": "X",
        },
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@patch("mcp_server.tools.goals.GoalService")
def test_goal_transition_permission_denied(mock_service_cls):
    mock_service_cls.return_value.transition_status.side_effect = (
        PermissionDeniedError("no write")
    )
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.transition",
        params={"goal_id": str(GOAL_UUID), "target_state": "Freigegeben"},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@patch("mcp_server.tools.goals.GoalService")
def test_goal_transition_requires_target_state(mock_service_cls):
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.transition",
        params={"goal_id": str(GOAL_UUID)},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    mock_service_cls.return_value.transition_status.assert_not_called()


@patch("mcp_server.tools.goals.GoalService")
def test_goal_transition_returns_new_status(mock_service_cls):
    goal = SimpleNamespace(
        id=GOAL_UUID,
        lineage_id=LINEAGE_UUID,
        sequence_number=2,
        status="Freigegeben",
    )
    mock_service_cls.return_value.transition_status.return_value = goal
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.transition",
        params={
            "goal_id": str(GOAL_UUID),
            "target_state": "Freigegeben",
            "change_reason": "Approved.",
        },
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is True
    assert result.data["status"] == "Freigegeben"
    assert result.data["id"] == str(GOAL_UUID)


@patch("mcp_server.tools.goals.MainGoalService")
def test_main_goal_generate_permission_denied(mock_service_cls):
    mock_service_cls.return_value.generate_ai.side_effect = PermissionDeniedError(
        "no write"
    )
    group = MainGoalToolGroup()

    result = group.execute_tool(
        tool_name="main_goal.generate",
        params={"workspace_id": str(WORKSPACE_UUID)},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@patch("mcp_server.tools.goals.MainGoalService")
def test_main_goal_create_manual_permission_denied(mock_service_cls):
    mock_service_cls.return_value.create_manual.side_effect = PermissionDeniedError(
        "no write"
    )
    group = MainGoalToolGroup()

    result = group.execute_tool(
        tool_name="main_goal.create_manual",
        params={"workspace_id": str(WORKSPACE_UUID), "content": "X"},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@patch("mcp_server.tools.goals.MainGoalService")
def test_main_goal_approve_permission_denied(mock_service_cls):
    mock_service_cls.return_value.approve.side_effect = PermissionDeniedError(
        "no write"
    )
    group = MainGoalToolGroup()

    result = group.execute_tool(
        tool_name="main_goal.approve",
        params={"main_goal_id": str(MAIN_GOAL_UUID)},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Schema validation (Issue #369)
# ---------------------------------------------------------------------------


def test_goal_outdate_schema_has_required_goal_id():
    """#369: goal.outdate schema must declare 'required' with goal_id.
    This is the established pattern for soft-delete tools (goal.delete also
    has required=['goal_id'])."""
    group = GoalToolGroup()
    schema = next(
        s for s in group.get_tool_schemas() if s["name"] == "goal.outdate"
    )["inputSchema"]

    assert "required" in schema, "goal.outdate schema missing 'required' field"
    assert "goal_id" in schema["required"], (
        "goal_id not in goal.outdate required fields"
    )


def test_goal_reactivate_schema_has_required_goal_id():
    """#369: goal.reactivate schema must declare 'required' with goal_id.
    This is the established pattern for lifecycle tools (goal.delete also
    has required=['goal_id'])."""
    group = GoalToolGroup()
    schema = next(
        s for s in group.get_tool_schemas() if s["name"] == "goal.reactivate"
    )["inputSchema"]

    assert "required" in schema, "goal.reactivate schema missing 'required' field"
    assert "goal_id" in schema["required"], (
        "goal_id not in goal.reactivate required fields"
    )


# ---------------------------------------------------------------------------
# expected_version optimistic locking (GitHub #1129)
#
# goal.transition already accepted expected_version and mapped a lost race to
# a caller-retryable conflict (CR-08). goal.delete / goal.outdate /
# goal.reactivate and main_goal.approve did not, leaving concurrent MCP
# writers last-writer-wins.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name", ["goal.delete", "goal.outdate", "goal.reactivate"]
)
def test_goal_lifecycle_schema_exposes_expected_version(tool_name):
    schema = next(
        s for s in GoalToolGroup().get_tool_schemas() if s["name"] == tool_name
    )["inputSchema"]

    assert "expected_version" in schema["properties"], (
        f"{tool_name} schema missing expected_version"
    )
    assert schema["properties"]["expected_version"]["type"] == "integer"


def test_main_goal_approve_schema_exposes_expected_version():
    schema = next(
        s
        for s in MainGoalToolGroup().get_tool_schemas()
        if s["name"] == "main_goal.approve"
    )["inputSchema"]

    assert "expected_version" in schema["properties"]
    assert schema["properties"]["expected_version"]["type"] == "integer"


@patch("mcp_server.tools.goals.GoalService")
def test_goal_delete_forwards_expected_version_and_maps_conflict(mock_service_cls):
    mock_service_cls.return_value.archive.side_effect = OptimisticLockError("stale")
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": str(GOAL_UUID), "expected_version": 7},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Version conflict" in (result.message or "")
    assert mock_service_cls.return_value.archive.call_args.kwargs[
        "expected_version"
    ] == 7


@patch("mcp_server.tools.goals.GoalService")
def test_goal_outdate_forwards_expected_version_and_maps_conflict(mock_service_cls):
    mock_service_cls.return_value.archive.side_effect = OptimisticLockError("stale")
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.outdate",
        params={"goal_id": str(GOAL_UUID), "expected_version": 7},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Version conflict" in (result.message or "")
    assert mock_service_cls.return_value.archive.call_args.kwargs[
        "expected_version"
    ] == 7


@patch("mcp_server.tools.goals.GoalService")
def test_goal_reactivate_forwards_expected_version_and_maps_conflict(mock_service_cls):
    mock_service_cls.return_value.restore.side_effect = OptimisticLockError("stale")
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.reactivate",
        params={"goal_id": str(GOAL_UUID), "expected_version": 7},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Version conflict" in (result.message or "")
    assert mock_service_cls.return_value.restore.call_args.kwargs[
        "expected_version"
    ] == 7


@patch("mcp_server.tools.goals.MainGoalService")
def test_main_goal_approve_forwards_expected_version_and_maps_conflict(
    mock_service_cls,
):
    mock_service_cls.return_value.approve.side_effect = OptimisticLockError("stale")
    group = MainGoalToolGroup()

    result = group.execute_tool(
        tool_name="main_goal.approve",
        params={"main_goal_id": str(MAIN_GOAL_UUID), "expected_version": 7},
        auth_context=VIEWER_CTX,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Version conflict" in (result.message or "")
    assert mock_service_cls.return_value.approve.call_args.kwargs[
        "expected_version"
    ] == 7


# ---------------------------------------------------------------------------
# main_goal.approve — end-to-end optimistic locking against the real DB
# ---------------------------------------------------------------------------


def _main_goal_tenant_and_workspace(name: str):
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name=name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=name, goals_enabled=True)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _provision_main_goal_workflow(workspace) -> None:
    from persistence.tenancy import TenantContext
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="main_goal_default",
            item_type="MainGoal",
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


def _main_goal_engine_version(tenant_id, main_goal_id) -> int:
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowItemState

    TenantContext.set_tenant(tenant_id)
    try:
        return WorkflowItemState.objects.get(
            item_id=main_goal_id, item_type="MainGoal"
        ).version
    finally:
        TenantContext.clear_tenant()


def _admin_ctx(tenant_id, workspace_id) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=tenant_id,
        active_roles=("admin", "approver", "editor"),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        workspace_id=workspace_id,
    )


@pytest.mark.django_db
def test_main_goal_approve_stale_expected_version_is_rejected():
    tenant, workspace = _main_goal_tenant_and_workspace("I1129-MG1")
    _provision_main_goal_workflow(workspace)
    ctx = _admin_ctx(tenant.id, workspace.id)
    group = MainGoalToolGroup()

    created = group.execute_tool(
        tool_name="main_goal.create_manual",
        params={"workspace_id": str(workspace.id), "content": "Main goal."},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert created.success is True, created.message
    main_goal_id = UUID(created.data["main_goal"]["id"])
    stale = _main_goal_engine_version(tenant.id, main_goal_id) + 1

    result = group.execute_tool(
        tool_name="main_goal.approve",
        params={
            "main_goal_id": str(main_goal_id),
            "change_reason": "stale approval",
            "expected_version": stale,
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert "Version conflict" in (result.message or ""), result.message

    # No last-writer-wins: the draft was not approved by the stale call.
    read = group.execute_tool(
        tool_name="main_goal.read",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert read.data["main_goal"] is None


@pytest.mark.django_db
def test_main_goal_approve_current_expected_version_succeeds():
    tenant, workspace = _main_goal_tenant_and_workspace("I1129-MG2")
    _provision_main_goal_workflow(workspace)
    ctx = _admin_ctx(tenant.id, workspace.id)
    group = MainGoalToolGroup()

    created = group.execute_tool(
        tool_name="main_goal.create_manual",
        params={"workspace_id": str(workspace.id), "content": "Main goal."},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert created.success is True, created.message
    main_goal_id = UUID(created.data["main_goal"]["id"])
    current = _main_goal_engine_version(tenant.id, main_goal_id)

    result = group.execute_tool(
        tool_name="main_goal.approve",
        params={
            "main_goal_id": str(main_goal_id),
            "change_reason": "approved",
            "expected_version": current,
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["main_goal"]["status"] == "Freigegeben"
