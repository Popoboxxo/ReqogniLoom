"""MCP metrics.* tool group — central statistics surface (Issue #1265).

The handlers are thin wrappers over ``se_metrics.services``; these tests pin the
published schemas, the argument normalisation and the delegation contract
without a database (the service calls are patched).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from auth_tenancy.context import AuthContext, AuthMethod


@pytest.fixture
def group():
    from mcp_server.tools.metrics import MetricsToolGroup

    return MetricsToolGroup()


@pytest.fixture
def ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _call(group, name, params, ctx):
    return group.execute_tool(
        tool_name=name,
        params=params,
        auth_context=ctx,
        # Matches the placeholder convention of the sibling tool-group tests
        # (e.g. test_attribute_definition_tools.py) — never a real key.
        api_key="reqlo_test_key",
    )


def test_group_publishes_exactly_the_two_read_tools(group):
    names = {schema["name"] for schema in group._TOOL_SCHEMAS}
    assert names == {"metrics.catalog", "metrics.get"}
    assert set(group._TOOL_MAP) == names
    for handler in group._TOOL_MAP.values():
        assert hasattr(group, handler)


def test_metrics_get_requires_workspace_id_in_its_schema(group):
    schema = next(
        s for s in group._TOOL_SCHEMAS if s["name"] == "metrics.get"
    )
    assert schema["inputSchema"]["required"] == ["workspace_id"]
    assert schema["inputSchema"]["properties"]["workspace_id"]["type"] == "string"


def test_metrics_catalog_declares_no_parameters(group):
    schema = next(
        s for s in group._TOOL_SCHEMAS if s["name"] == "metrics.catalog"
    )
    assert schema["inputSchema"]["properties"] == {}


def test_group_is_registered_as_a_read_only_namespace(db):
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    assert "metrics" in registry._groups
    assert registry._is_write_tool("metrics.catalog") is False
    assert registry._is_write_tool("metrics.get") is False


def test_catalog_delegates_to_the_service(group, ctx):
    payload = {"metrics": [{"key": "open_risks"}], "default_keys": [], "all_keys": []}
    with patch(
        "mcp_server.tools.metrics.get_metric_catalog", return_value=payload
    ) as mock_catalog:
        result = _call(group, "metrics.catalog", {}, ctx)

    assert result.success is True
    assert result.data == payload
    mock_catalog.assert_called_once_with()


def test_get_returns_a_validation_error_without_a_workspace(group, ctx):
    result = _call(group, "metrics.get", {}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_returns_a_validation_error_for_a_malformed_workspace(group, ctx):
    result = _call(group, "metrics.get", {"workspace_id": "not-a-uuid"}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_forwards_keys_timeframe_and_refresh(group, ctx):
    workspace_id = str(uuid.uuid4())
    payload = {"workspace_id": workspace_id, "metrics": {}, "unknown_keys": []}
    with patch(
        "mcp_server.tools.metrics.get_metric_values", return_value=payload
    ) as mock_values:
        result = _call(
            group,
            "metrics.get",
            {
                "workspace_id": workspace_id,
                "keys": ["open_risks", "volatility"],
                "timeframe": "P7D",
                "refresh": True,
            },
            ctx,
        )

    assert result.success is True
    assert result.data == payload
    assert mock_values.call_args.kwargs == {
        "workspace_id": workspace_id,
        "keys": ["open_risks", "volatility"],
        "timeframe": "P7D",
        "refresh": True,
    }


def test_get_accepts_a_comma_separated_key_string(group, ctx):
    workspace_id = str(uuid.uuid4())
    with patch(
        "mcp_server.tools.metrics.get_metric_values", return_value={}
    ) as mock_values:
        _call(
            group,
            "metrics.get",
            {"workspace_id": workspace_id, "keys": "open_risks, volatility"},
            ctx,
        )

    assert mock_values.call_args.kwargs["keys"] == ["open_risks", "volatility"]


def test_get_rejects_a_non_string_key_entry(group, ctx):
    result = _call(
        group,
        "metrics.get",
        {"workspace_id": str(uuid.uuid4()), "keys": ["open_risks", 7]},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_defaults_refresh_to_false(group, ctx):
    with patch(
        "mcp_server.tools.metrics.get_metric_values", return_value={}
    ) as mock_values:
        _call(group, "metrics.get", {"workspace_id": str(uuid.uuid4())}, ctx)

    assert mock_values.call_args.kwargs["refresh"] is False
    assert mock_values.call_args.kwargs["keys"] is None


def test_unknown_tool_is_reported(group, ctx):
    result = _call(group, "metrics.nope", {}, ctx)

    assert result.success is False
    assert result.error_code == "UNKNOWN_TOOL"
