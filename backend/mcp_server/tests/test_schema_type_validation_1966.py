"""#1966 — a wrongly typed tool argument is VALIDATION_ERROR, never 500.

Two layers are pinned:

* the dispatcher validates provided params against each tool's published
  ``inputSchema`` and names the offending field;
* ``artifact.search`` keeps a typed local guard for direct group calls (which
  bypass the dispatcher in unit tests and other hosts).
"""
from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry, _DispatchContext
from mcp_server.tools.base import BaseToolGroup, map_tool_exception
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

# The dispatcher arms/clears the request tenant through a DB round trip.
pytestmark = pytest.mark.django_db

CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("admin",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)
WORKSPACE_ID = str(UUID("00000000-0000-0000-0000-000000000010"))


class _SchemaProbeGroup(BaseToolGroup):
    """Minimal group whose published schema declares one integer parameter."""

    _TOOL_MAP: ClassVar[dict[str, str]] = {"probe.run": "_run"}
    _TOOL_SCHEMAS: ClassVar[list[dict]] = [
        {
            "name": "probe.run",
            "description": "Probe.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Page size."},
                    "flag": {"type": "boolean"},
                },
                "required": ["limit"],
            },
        }
    ]

    def _run(self, *, params, auth_context, api_key):
        from mcp_server.protocol_handler import ToolResult

        return ToolResult.ok({"limit": params["limit"]})


def _dispatch(tool_name: str, params: dict, group=None):
    registry = ToolRegistry()
    group = group or _SchemaProbeGroup()
    registry.register_groups({"probe": group})
    context = _DispatchContext(
        auth_ctx=CTX,
        gate_ctx=CTX,
        group=group,
        workspace_id=None,
        scope_workspace_id=None,
    )
    with patch.object(registry, "_validate_api_key", return_value=(CTX, None)), patch.object(
        registry, "_authorize_tool_call", return_value=None
    ), patch.object(
        registry, "_resolve_dispatch_context", return_value=(context, None)
    ), patch.object(registry, "_ensure_groups", return_value=None):
        return registry.dispatch_request(tool_name, params, "reqlo_test_key")


def test_dispatcher_rejects_wrong_integer_type_with_field_name():
    result = _dispatch("probe.run", {"limit": "abc"})
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "limit" in result.message


def test_dispatcher_rejects_wrong_boolean_type_with_field_name():
    result = _dispatch("probe.run", {"limit": 20, "flag": "maybe"})
    assert result.error_code == "VALIDATION_ERROR"
    assert "flag" in result.message


def test_dispatcher_accepts_numeric_string_and_skips_unknown_fields():
    """Legacy callers sending ``limit="10"`` must keep working (#1966)."""
    result = _dispatch("probe.run", {"limit": "10", "undeclared": object()})
    assert result.success is True
    assert result.data["limit"] == "10"


def test_dispatcher_type_gate_runs_before_the_handler():
    group = _SchemaProbeGroup()
    with patch.object(group, "_run", wraps=group._run) as handler:
        result = _dispatch("probe.run", {"limit": "abc"}, group=group)
    assert result.error_code == "VALIDATION_ERROR"
    handler.assert_not_called()


class TestArtifactSearchLocalGuard:
    def _group(self) -> CrossCuttingToolGroup:
        return CrossCuttingToolGroup(
            artifact_service=MagicMock(),
            search_service=MagicMock(),
            trace_service=MagicMock(),
            trace_suggest_service=MagicMock(),
            summary_service=MagicMock(),
        )

    @pytest.mark.parametrize("field", ["limit", "page"])
    def test_invalid_pagination_names_the_field(self, field):
        params = {"query": "hello", field: "abc"}
        result = self._group().execute_tool(
            "artifact.search", params, CTX, "reqlo_test_key"
        )
        assert result.error_code == "VALIDATION_ERROR"
        assert field in result.message

    def test_bool_is_not_an_integer(self):
        result = self._group().execute_tool(
            "artifact.search", {"query": "hello", "limit": True}, CTX, "reqlo_test_key"
        )
        assert result.error_code == "VALIDATION_ERROR"
        assert "limit" in result.message


def test_plain_value_error_is_mapped_instead_of_masked():
    mapped = map_tool_exception(ValueError("invalid literal for int(): 'abc'"))
    assert mapped is not None
    assert mapped[0] == "VALIDATION_ERROR"
