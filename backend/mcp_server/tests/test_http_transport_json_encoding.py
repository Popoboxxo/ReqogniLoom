"""
Regression tests for issue #441: ``workspace.get_context`` (and, more
generally, any MCP tool) crashing the HTTP transport with an unhandled
``TypeError`` when a handler's result contains a value ``json.dumps()``
cannot encode natively (e.g. a raw ``UUID``).

leaf_id : COMP-MC-001
req_id  : REQ-L2-MC-005 (HTTP transport), REQ-L2-MC-011 (structured error response)

Covers:
  - McpHttpTransportView.post() must not let a json.dumps() TypeError escape
    as an unhandled exception (which Django would render as an HTML debug
    page instead of JSON) — it must return a JSON-RPC INTERNAL_ERROR
    envelope with HTTP 500 instead.
  - The success path (serializable response_frame) is unaffected.
"""
from __future__ import annotations

import json
from unittest import mock
from uuid import UUID

from django.test import RequestFactory

from mcp_server.views import McpHttpTransportView

_REQUEST_BODY = b'{"jsonrpc": "2.0", "id": 7, "method": "workspace.get_context", "params": {}}'


def _post_request():
    return RequestFactory().post(
        "/mcp/",
        data=_REQUEST_BODY,
        content_type="application/json",
    )


def test_unencodable_response_frame_returns_jsonrpc_error_not_html_500():
    """A response_frame containing a raw UUID must not crash the view.

    Before the fix, ``json.dumps(response_frame)`` raised ``TypeError:
    Object of type UUID is not JSON serializable`` *outside* the
    try/except around ``handle_http_request()`` — Django then rendered its
    HTML debug page (or a bare 500) instead of a JSON-RPC error envelope.
    """
    fake_handler = mock.Mock()
    fake_handler.handle_http_request.return_value = {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {"workspace_context": {"id": UUID(int=0)}},
    }

    request = _post_request()
    with mock.patch("mcp_server.views._get_handler", return_value=fake_handler):
        response = McpHttpTransportView().post(request)

    assert response.status_code == 500
    assert response["Content-Type"] == "application/json"
    body = json.loads(response.content)
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 7
    assert body["error"]["error_code"] == "INTERNAL_ERROR"


def test_serializable_response_frame_is_returned_unchanged():
    """Sanity check: the success path is not affected by the new guard."""
    fake_handler = mock.Mock()
    fake_handler.handle_http_request.return_value = {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {"workspace_context": {"tenant_id": "abc"}},
    }

    request = _post_request()
    with mock.patch("mcp_server.views._get_handler", return_value=fake_handler):
        response = McpHttpTransportView().post(request)

    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["result"]["workspace_context"]["tenant_id"] == "abc"
