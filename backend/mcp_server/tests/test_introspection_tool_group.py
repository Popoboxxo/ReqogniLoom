"""``tool.list_groups`` introspection tool (MCP-Modernisierung Task 13)."""
from __future__ import annotations

import json
import uuid

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.introspection import IntrospectionToolGroup


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def _run():
    return IntrospectionToolGroup().execute_tool(
        tool_name="tool.list_groups",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )


def test_group_exposes_exactly_one_tool():
    schemas = IntrospectionToolGroup().get_tool_schemas()
    assert [s["name"] for s in schemas] == ["tool.list_groups"]


def test_schema_takes_no_required_parameters():
    schema = IntrospectionToolGroup().get_tool_schemas()[0]
    assert schema["inputSchema"].get("required", []) == []


def test_returns_group_names_with_tool_counts():
    result = _run()
    assert result.success
    groups = {g["name"]: g for g in result.data["groups"]}
    assert groups["requirement"]["tool_count"] > 0
    assert result.data["count"] == len(result.data["groups"])


def test_payload_is_stdlib_json_encodable():
    json.dumps(_run().data)


def test_hides_the_invisible_capability_groups():
    """resource.* / prompt.* publish no schemas, so they are not real groups."""
    names = {g["name"] for g in _run().data["groups"]}
    assert "resource" not in names
    assert "prompt" not in names


def test_includes_the_icd_group():
    # Four tools on this base: read/query (Phase prior) plus create/update.
    groups = {g["name"]: g for g in _run().data["groups"]}
    assert groups["icd"]["tool_count"] == 4


def test_groups_are_sorted_by_name():
    names = [g["name"] for g in _run().data["groups"]]
    assert names == sorted(names)


def test_tool_is_read_only():
    from mcp_server.tool_registry import ToolRegistry

    assert ToolRegistry()._is_write_tool("tool.list_groups") is False


def test_tool_is_always_visible():
    from mcp_server.tool_registry import _ALWAYS_VISIBLE_TOOLS

    assert "tool.list_groups" in _ALWAYS_VISIBLE_TOOLS


def test_group_is_registered():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    group, err = registry._router.route("tool.list_groups")
    assert err is None
    assert type(group).__name__ == "IntrospectionToolGroup"
