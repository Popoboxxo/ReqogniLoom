"""F1.2-T2 (#1374, PR-F3b) — ``diagram.create`` requires ``workspace_id``.

Same contract as the REST twin (``POST /api/v1/diagrams/``): a Diagram is a
TraceLink endpoint only through its backing ``Artifact``, which cannot exist
without a workspace. The MCP tool therefore declares ``workspace_id`` as a
required input-schema field and reads it through ``require_uuid`` so a missing
or malformed value travels the existing validation path:

``ParameterError`` -> ``VALIDATION_ERROR`` -> JSON-RPC ``-32602`` (invalid
params). No new error code is introduced.
"""
from __future__ import annotations

import uuid

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.protocol_handler import ErrorFormatter
from mcp_server.tools.diagram import DiagramToolGroup

_CREATE_PARAMS = {
    "name": "Workspace-less Diagram",
    "diagram_type": "block",
    "payload_format": "json",
    "content": '{"nodes": [{"id": "A", "label": "Login"}]}',
}


def _editor_ctx() -> AuthContext:
    """A write-capable identity — the role gate runs before parameter checks."""
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _create_schema() -> dict:
    group = DiagramToolGroup()
    return next(
        schema
        for schema in group.get_tool_schemas()
        if schema["name"] == "diagram.create"
    )


def test_workspace_id_is_a_required_schema_field() -> None:
    schema = _create_schema()["inputSchema"]

    assert "workspace_id" in schema["required"]
    assert schema["properties"]["workspace_id"]["type"] == "string"


def test_create_without_workspace_is_invalid_params() -> None:
    result = DiagramToolGroup().execute_tool(
        "diagram.create",
        dict(_CREATE_PARAMS),
        _editor_ctx(),
        api_key="reqlo_test",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "workspace_id" in result.message


def test_missing_workspace_maps_to_jsonrpc_invalid_params() -> None:
    """A missing workspace_id is an invalid-params defect at the wire boundary."""
    result = DiagramToolGroup().execute_tool(
        "diagram.create",
        dict(_CREATE_PARAMS),
        _editor_ctx(),
        api_key="reqlo_test",
    )

    assert result.error_code == "VALIDATION_ERROR"
    assert ErrorFormatter.format_error("VALIDATION_ERROR")["code"] == -32602
