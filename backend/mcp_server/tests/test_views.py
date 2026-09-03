import json
from unittest import mock

from django.test import Client, RequestFactory

from mcp_server.views import McpHttpTransportView


def test_get_mcp_with_event_stream_accept_returns_405():
    client = Client()
    resp = client.get("/mcp/", HTTP_ACCEPT="text/event-stream")
    assert resp.status_code == 405


def test_get_mcp_without_event_stream_accept_still_returns_info_json():
    client = Client()
    resp = client.get("/mcp/")
    assert resp.status_code == 200
    assert resp.json()["server"] == "ReqogniLoom MCP Server"


def test_batch_jsonrpc_request_returns_clean_400_not_500():
    """A JSON-array (batch) body must be rejected cleanly, not crash the view.

    Batch dispatch is out of scope (R3/P0-soforthaertung task 12) — no client
    in this codebase's integration surface sends batched requests and the MCP
    spec treats batch support as optional. Before the fix, a list body was
    forwarded into ``handler.handle_http_request`` (which expects a single
    frame dict), threw, and fell into the generic 500 handler.

    Follows the RequestFactory + direct-call pattern from
    ``test_http_transport_json_encoding.py`` (the existing POST test for this
    view in this test suite) — no separate API-key fixture is needed since
    this bypasses URL dispatch/auth middleware entirely.
    """
    fake_handler = mock.Mock()
    request = RequestFactory().post(
        "/mcp/",
        data=b'[{"jsonrpc": "2.0", "method": "ping", "id": 1}]',
        content_type="application/json",
    )

    with mock.patch("mcp_server.views._get_handler", return_value=fake_handler):
        response = McpHttpTransportView().post(request)

    assert response.status_code == 400
    body = json.loads(response.content)
    assert body["error"]["error_code"] == "INVALID_REQUEST"
    fake_handler.handle_http_request.assert_not_called()
