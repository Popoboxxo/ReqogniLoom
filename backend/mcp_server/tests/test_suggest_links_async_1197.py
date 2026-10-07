"""Issue #1197 — MCP async trigger + status tool for ``traceability.suggest_links``.

Covers the ``async`` parameter on ``traceability.suggest_links`` and the new
``traceability.suggest_links_status`` poll tool, plus the registry
classification that keeps the status tool read-only and workspace-scope
ratchet-compliant.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

pytestmark = pytest.mark.django_db


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method="test",
    )


def test_async_true_dispatches_and_returns_task_id() -> None:
    service = MagicMock()
    service.suggest_links_async.return_value = "task-mcp"
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group._handle_traceability_suggest_links(
        params={"workspace_id": str(uuid4()), "async": True},
        auth_context=_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is True
    assert result.data == {"task_id": "task-mcp"}
    service.suggest_links.assert_not_called()


def test_async_accepts_the_string_flag() -> None:
    service = MagicMock()
    service.suggest_links_async.return_value = "task-mcp-str"
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group._handle_traceability_suggest_links(
        params={"workspace_id": str(uuid4()), "async": "true"},
        auth_context=_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is True
    assert result.data == {"task_id": "task-mcp-str"}


def test_broker_not_configured_returns_service_unavailable() -> None:
    service = MagicMock()
    service.suggest_links_async.return_value = {
        "error": {"code": "BROKER_NOT_CONFIGURED", "message": "no broker"}
    }
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group._handle_traceability_suggest_links(
        params={"workspace_id": str(uuid4()), "async": True},
        auth_context=_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is False
    assert result.error_code == "SERVICE_UNAVAILABLE"


def test_omitting_async_stays_synchronous() -> None:
    service = MagicMock()
    result_obj = MagicMock()
    result_obj.to_dict.return_value = {"tier": "standard", "suggestions": []}
    service.suggest_links.return_value = result_obj
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group._handle_traceability_suggest_links(
        params={"workspace_id": str(uuid4())},
        auth_context=_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is True
    assert result.data == {"tier": "standard", "suggestions": []}
    service.suggest_links_async.assert_not_called()


def test_status_tool_delegates_to_the_service() -> None:
    service = MagicMock()
    service.get_suggest_links_status.return_value = {
        "task_id": "t-1",
        "status": "not_found",
        "result": None,
        "error": None,
    }
    group = CrossCuttingToolGroup(trace_suggest_service=service)

    result = group._handle_traceability_suggest_links_status(
        params={"task_id": "t-1"},
        auth_context=_ctx(),
        api_key="reqlo_x",
    )

    assert result.success is True
    assert result.data["status"] == "not_found"
    service.get_suggest_links_status.assert_called_once()


def test_schemas_advertise_the_async_param_and_status_tool() -> None:
    group = CrossCuttingToolGroup()
    schemas = {s["name"]: s for s in group.get_tool_schemas()}

    assert (
        "async"
        in schemas["traceability.suggest_links"]["inputSchema"]["properties"]
    )
    assert "traceability.suggest_links_status" in schemas
    assert (
        schemas["traceability.suggest_links_status"]["inputSchema"]["required"]
        == ["task_id"]
    )


def test_status_tool_is_read_only_in_the_registry() -> None:
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    assert registry._is_write_tool("traceability.suggest_links_status") is False
    assert registry._is_write_tool("traceability.suggest_links") is False
