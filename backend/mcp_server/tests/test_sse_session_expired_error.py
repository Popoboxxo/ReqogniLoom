"""Actionable rejection when an SSE session is gone (issue #427).

A client whose ``session_id`` has outlived its Redis binding used to receive a
bare ``401 Invalid or expired session`` in ``text/plain``. MCP clients surface
that verbatim ("Error POSTing to endpoint (HTTP 401): Invalid or expired
session"), which reads like a credentials problem — so operators went looking
for a broken API key when the only fix was to re-open the SSE stream.

These tests pin the replacement contract: a JSON-RPC error envelope carrying a
``SESSION_EXPIRED`` ``error_code`` that is distinguishable from ``AUTH_FAILED``
and names the endpoint to reconnect to.

leaf_id : COMP-MC-001 (McpMessagesView)
req_id  : REQ-047 (string ``error_code`` envelope), REQ-L2-MC-011
"""
from __future__ import annotations

import json
from typing import Optional
from unittest import mock

from django.test import RequestFactory

from mcp_server.protocol_handler import ERROR_CODE_MAP, ERROR_CODES
from mcp_server.views import McpMessagesView

_BODY = b'{"jsonrpc": "2.0", "id": 42, "method": "tools/call"}'


def _post_with_dead_session(session_id: str = "5f0f0f0f-dead-4dea-9dea-000000000000"):
    """POST to the message endpoint while the session binding is missing."""
    request = RequestFactory().post(
        f"/mcp/messages/?session_id={session_id}",
        data=_BODY,
        content_type="application/json",
    )
    unbound: Optional[str] = None
    with mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=unbound
    ), mock.patch("mcp_server.views._get_handler") as get_handler, mock.patch(
        "mcp_server.views._message_executor"
    ) as executor:
        response = McpMessagesView().post(request)
    # An unauthorised session must never reach the tool pipeline.
    get_handler.assert_not_called()
    executor.submit.assert_not_called()
    return response


def test_expired_session_returns_json_envelope_not_plain_text() -> None:
    """The rejection is machine-readable JSON, not a bare sentence."""
    response = _post_with_dead_session()

    assert response.status_code == 401
    assert response["Content-Type"] == "application/json"

    frame = json.loads(response.content)
    assert frame["jsonrpc"] == "2.0"
    # The request id is echoed so a client can correlate the rejection.
    assert frame["id"] == 42


def test_expired_session_uses_a_distinct_error_code() -> None:
    """``SESSION_EXPIRED`` must not collapse into the generic auth failure."""
    frame = json.loads(_post_with_dead_session().content)

    assert frame["error"]["error_code"] == "SESSION_EXPIRED"
    assert frame["error"]["error_code"] != "AUTH_FAILED"
    # Registered in the shared vocabularies so every consumer can resolve it.
    assert "SESSION_EXPIRED" in ERROR_CODES
    assert ERROR_CODE_MAP["SESSION_EXPIRED"] not in (
        ERROR_CODE_MAP["AUTH_FAILED"],
        ERROR_CODE_MAP["INTERNAL_ERROR"],
    )


def test_expired_session_message_is_actionable() -> None:
    """The message tells the operator it is not a token problem, and what to do."""
    frame = json.loads(_post_with_dead_session().content)
    error = frame["error"]

    message = error["message"]
    assert "expired" in message.lower()
    assert "not an authentication failure" in message.lower()
    assert "/mcp/sse/" in message

    data = error["data"]
    assert data["reconnect_endpoint"] == "/mcp/sse/"
    assert data["retryable"] is True
    assert isinstance(data["session_ttl_seconds"], int)


def test_missing_session_id_is_a_separate_error_code() -> None:
    """A malformed call is INVALID_REQUEST — never SESSION_EXPIRED."""
    request = RequestFactory().post(
        "/mcp/messages/", data=_BODY, content_type="application/json"
    )
    with mock.patch("mcp_server.views._get_handler") as get_handler:
        response = McpMessagesView().post(request)

    get_handler.assert_not_called()
    assert response.status_code == 400
    frame = json.loads(response.content)
    assert frame["error"]["error_code"] == "INVALID_REQUEST"
    assert frame["id"] == 42


def test_unparseable_body_still_yields_a_valid_envelope() -> None:
    """Recovering the request id must never turn one error into two."""
    request = RequestFactory().post(
        "/mcp/messages/?session_id=x", data=b"not json at all",
        content_type="application/json",
    )
    unbound: Optional[str] = None
    with mock.patch("mcp_server.sse_pubsub.get_session_api_key", return_value=unbound):
        response = McpMessagesView().post(request)

    assert response.status_code == 401
    frame = json.loads(response.content)
    assert frame["id"] is None
    assert frame["error"]["error_code"] == "SESSION_EXPIRED"
