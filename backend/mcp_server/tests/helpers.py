"""JSON-RPC helper for MCP E2E tests."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


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
    """Extract the 'error_code' from a JSON-RPC error response."""
    body = response.json()
    assert "error" in body, f"Expected 'error' in response, got: {body}"
    return body["error"]["error_code"]


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
