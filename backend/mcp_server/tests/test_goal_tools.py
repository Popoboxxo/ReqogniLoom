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
from uuid import UUID

import pytest

from application.base import PermissionDeniedError
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
