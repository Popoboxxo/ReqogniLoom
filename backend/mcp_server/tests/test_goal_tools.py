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

import pytest

from mcp_server.tool_registry import ToolRegistry


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
