"""
End-to-end tests for the SSE transport endpoint (``POST /mcp/sse/``).

leaf_id : COMP-MC-001 (ProtocolHandler) + McpSseTransportView
req_id  : REQ-L2-MC-005 (HTTP/SSE transport),
          REQ-L2-MC-006 (API-key auth),
          REQ-L2-MC-007 (RBAC),
          REQ-L2-MC-011 (structured error response)

The SSE transport is a thin Django view (``McpSseTransportView``) that wraps
a single ``ProtocolHandler.handle_http_request()`` response frame in an
SSE event (``data: {json.dumps(frame)}\\n\\n``) and returns it as a
``StreamingHttpResponse`` with ``content_type="text/event-stream"`` and
``status=200``.

Key contract under test: the HTTP-level status is *always* 200 on the SSE
endpoint (the transport never returns 4xx/5xx), but the *payload* still
carries the same JSON-RPC 2.0 error envelope that the HTTP transport
produces, just wrapped in an SSE ``data:`` line. The tests below parse
that line back out and assert on the inner frame.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
from uuid import uuid4

import pytest
from django.test import Client

from auth_tenancy.models import UserRole
from mcp_server.tests.conftest_e2e import (
    admin_client,
    e2e_preset,
    e2e_userrole_admin,
    e2e_userrole_viewer,
    e2e_workspace,
    viewer_client,
)
from mcp_server.tests.helpers import make_jsonrpc_request
from persistence.models import Workspace


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _post_sse(
    client: Client,
    method: str,
    params: Dict[str, Any],
    request_id: int = 1,
    api_key: str | None = None,
):
    """POST a JSON-RPC request to ``/mcp/sse/`` and return the Django response.

    The body is a standard JSON-RPC 2.0 frame; the API key is passed via
    the ``X-API-Key`` header (mirroring how the production MCP client
    authenticates over SSE).
    """
    body = make_jsonrpc_request(method, params, request_id)
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["HTTP_X_API_KEY"] = api_key
    return client.post(
        "/mcp/sse/", data=body, content_type="application/json", **headers
    )


def _parse_sse_events(response) -> List[Dict[str, Any]]:
    """Parse a ``text/event-stream`` body into a list of ``data:`` payload dicts.

    The current ``McpSseTransportView`` emits exactly one ``data:`` line
    per request, but the parser handles multiple events for forward-
    compatibility with any future streaming-response work.
    """
    body = response.content.decode("utf-8")
    events: List[Dict[str, Any]] = []
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[len("data: "):]
            events.append(json.loads(payload))
    return events


def _admin_api_key(admin_client: Client) -> str:
    """Return the admin client's pre-wired API key (used for negative tests)."""
    return admin_client.defaults.get("HTTP_X_API_KEY", "")


# ---------------------------------------------------------------------------
# 1. Read-tool happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_sse_read_tool_returns_event_stream_with_result(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """POST ``/mcp/sse/`` with ``requirement.query`` returns a single
    ``data:`` event whose payload carries a JSON-RPC 2.0 ``result``
    containing a ``requirements`` list (possibly empty).

    Asserts the SSE envelope contract:
    * HTTP status is 200
    * ``Content-Type`` is ``text/event-stream``
    * The body is exactly one ``data: {json}`` line
    * The inner frame is a valid JSON-RPC 2.0 success envelope
    """
    response = _post_sse(
        admin_client,
        "requirement.query",
        {"workspace_id": str(e2e_workspace.id)},
    )

    # SSE transport always responds with HTTP 200, even on success.
    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"

    events = _parse_sse_events(response)
    assert len(events) == 1, (
        f"Expected exactly one SSE event, got {len(events)}: {events!r}"
    )

    frame = events[0]
    assert frame["jsonrpc"] == "2.0"
    assert "result" in frame
    assert "error" not in frame
    assert "requirements" in frame["result"]
    assert isinstance(frame["result"]["requirements"], list)
    assert frame["result"]["count"] == len(frame["result"]["requirements"])


# ---------------------------------------------------------------------------
# 2. Write-tool happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_sse_write_tool_returns_event_stream_with_result(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """POST ``/mcp/sse/`` with ``workspace.close`` returns a single
    ``data:`` event whose payload reflects the deactivated workspace
    (``is_active == False``).

    Proves that write tools are also reachable over the SSE transport
    and that the success envelope round-trips through the SSE framing
    losslessly.
    """
    response = _post_sse(
        admin_client,
        "workspace.close",
        {"workspace_id": str(e2e_workspace.id)},
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"

    events = _parse_sse_events(response)
    assert len(events) == 1

    frame = events[0]
    assert frame["jsonrpc"] == "2.0"
    assert "error" not in frame
    assert "result" in frame
    # After close, the workspace is reported as inactive.
    assert frame["result"]["workspace"]["is_active"] is False
    assert frame["result"]["workspace"]["id"] == str(e2e_workspace.id)


# ---------------------------------------------------------------------------
# 3. NOT_FOUND error frame inside an SSE 200 response
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_sse_error_case_returns_event_stream_with_error(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """POST ``/mcp/sse/`` with a random UUID for ``requirement.get`` returns
    a single ``data:`` event carrying a JSON-RPC ``error`` envelope with
    ``error_code == "NOT_FOUND"``.

    Critically, the HTTP status is *still* 200 (SSE contract): the failure
    is communicated via the inner error frame, not via the HTTP status code.
    """
    response = _post_sse(
        admin_client,
        "requirement.get",
        {"id": str(uuid4()), "workspace_id": str(e2e_workspace.id)},
    )

    # SSE always returns 200 at the HTTP level — even on tool errors.
    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"

    events = _parse_sse_events(response)
    assert len(events) == 1

    frame = events[0]
    assert frame["jsonrpc"] == "2.0"
    assert "result" not in frame
    assert "error" in frame
    assert frame["error"]["error_code"] == "NOT_FOUND"
    assert "message" in frame["error"]


# ---------------------------------------------------------------------------
# 4. AUTH_FAILED error frame on missing API key
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_sse_auth_failure_returns_event_stream_with_auth_error(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """POST ``/mcp/sse/`` *without* an ``X-API-Key`` header returns a
    single ``data:`` event whose payload is a JSON-RPC ``error`` frame
    with ``error_code == "AUTH_FAILED"``.

    Uses a fresh, un-authenticated ``Client`` so that the missing-key
    path is the one under test (the ``admin_client`` fixture pre-wires
    a valid key via ``defaults``).
    """
    # Fresh client: no API key, no defaults.
    unauthenticated_client = Client()
    response = _post_sse(
        unauthenticated_client,
        "requirement.get",
        {"id": str(uuid4()), "workspace_id": str(e2e_workspace.id)},
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"

    events = _parse_sse_events(response)
    assert len(events) == 1

    frame = events[0]
    assert frame["jsonrpc"] == "2.0"
    assert "result" not in frame
    assert "error" in frame
    assert frame["error"]["error_code"] == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# 5. PERMISSION_DENIED error frame for RBAC-violating write tool
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_sse_rbac_denial_returns_event_stream_with_permission_error(
    viewer_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_viewer: UserRole,
):
    """POST ``/mcp/sse/`` as a *viewer* hitting a write tool
    (``workspace.close``) returns a single ``data:`` event whose payload
    is a JSON-RPC ``error`` frame with ``error_code == "PERMISSION_DENIED"``.

    The viewer has the right tenant/workspace membership but lacks the
    admin role required to mutate workspace state.
    """
    response = _post_sse(
        viewer_client,
        "workspace.close",
        {"workspace_id": str(e2e_workspace.id)},
    )

    # SSE HTTP layer is always 200.
    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"

    events = _parse_sse_events(response)
    assert len(events) == 1

    frame = events[0]
    assert frame["jsonrpc"] == "2.0"
    assert "result" not in frame
    assert "error" in frame
    assert frame["error"]["error_code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# 6. PARSE_ERROR error frame on invalid JSON body
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_sse_parse_error_returns_event_stream_with_parse_error(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """POST ``/mcp/sse/`` with a syntactically invalid JSON body returns
    a single ``data:`` event whose payload is a JSON-RPC ``error`` frame
    with ``error_code == "PARSE_ERROR"``.

    The API key header is still required and is forwarded from the
    admin client so that the failure mode under test is the JSON parser,
    not the auth layer.
    """
    api_key = _admin_api_key(admin_client)
    raw_client = Client()
    response = raw_client.post(
        "/mcp/sse/",
        data=b"not json{",
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"

    events = _parse_sse_events(response)
    assert len(events) == 1

    frame = events[0]
    assert frame["jsonrpc"] == "2.0"
    assert "result" not in frame
    assert "error" in frame
    assert frame["error"]["error_code"] == "PARSE_ERROR"
