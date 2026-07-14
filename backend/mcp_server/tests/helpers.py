"""JSON-RPC helper for MCP E2E tests."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

# Reverse mapping: JSON-RPC numeric error code → string error code name.
# ErrorFormatter.format_error emits {"code": <int>} per JSON-RPC 2.0 spec;
# tests that call extract_error_code() compare against string names
# (e.g. "VALIDATION_ERROR") so we map back here for readability.
# Source of truth: mcp_server.protocol_handler.ERROR_CODE_MAP.
_NUMERIC_TO_ERROR_CODE: Dict[int, str] = {
    -32700: "PARSE_ERROR",
    -32600: "INVALID_REQUEST",
    -32601: "UNKNOWN_TOOL",
    -32602: "VALIDATION_ERROR",
    -32603: "INTERNAL_ERROR",
    -32000: "AUTH_FAILED",
    -32001: "PERMISSION_DENIED",
    -32002: "FEATURE_NOT_ENABLED",
    -32003: "LLM_NOT_CONFIGURED",
    -32004: "NOT_FOUND",
}


# Constants
ADMIN_ROLE = "admin"
EDITOR_ROLE = "editor"
VIEWER_ROLE = "viewer"


def make_jsonrpc_frame(
    method: str,
    params: Optional[Dict[str, Any]] = None,
    request_id: int = 1,
    jsonrpc: str = "2.0",
) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 request frame (dict, not bytes)."""
    return {
        "jsonrpc": jsonrpc,
        "method": method,
        "id": request_id,
        "params": params or {},
    }


def make_jsonrpc_request(
    method: str,
    params: Optional[Dict[str, Any]] = None,
    request_id: int = 1,
    jsonrpc: str = "2.0",
) -> bytes:
    """Build a JSON-RPC 2.0 request body (bytes for HTTP POST)."""
    return json.dumps(make_jsonrpc_frame(method, params, request_id, jsonrpc)).encode()


def post_mcp(
    client,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    request_id: int = 1,
    api_key: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    jsonrpc: str = "2.0",
):
    """POST a JSON-RPC request to /mcp/ via the given Django test client.

    Returns the Django response object (HttpResponse). Use response.json() to parse.
    """
    body = make_jsonrpc_request(method, params, request_id, jsonrpc)
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["HTTP_X_API_KEY"] = api_key
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/mcp/", data=body, content_type="application/json", **headers)


def extract_result(response) -> Dict[str, Any]:
    """Extract the 'result' field from a JSON-RPC response, or raise AssertionError on error."""
    body = response.json()
    assert "result" in body, f"Expected 'result' in response, got: {body}"
    return body["result"]


def extract_error_code(response) -> str:
    """Extract the error code string from a JSON-RPC error response.

    ErrorFormatter.format_error emits a numeric 'code' field per JSON-RPC 2.0
    (e.g. -32602 for VALIDATION_ERROR). This helper maps that numeric code back
    to the human-readable string name so callers can write:

        assert extract_error_code(response) == "VALIDATION_ERROR"

    If the numeric code is not in the known map, the raw integer is returned as
    a string so the assertion fails with a useful value rather than KeyError.
    """
    body = response.json()
    assert "error" in body, f"Expected 'error' in response, got: {body}"
    numeric_code = body["error"]["code"]
    return _NUMERIC_TO_ERROR_CODE.get(numeric_code, str(numeric_code))


def extract_error_message(response) -> str:
    """Extract the error message from a JSON-RPC error response."""
    body = response.json()
    assert "error" in body, f"Expected 'error' in response, got: {body}"
    return body["error"].get("message", "")


# Templates for seed data
WORKSPACE_TEMPLATE = {
    "name": "E2E Workspace",
    "is_active": True,
}

USER_TEMPLATE = {
    "is_active": True,
    "is_staff": False,
    "is_superuser": False,
}
