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


def _post_with_error_frame(numeric_code: int):
    """POST through McpHttpTransportView with a stubbed handler error frame.

    Mirrors ``test_batch_jsonrpc_request_returns_clean_400_not_500``'s
    RequestFactory + direct-call + ``_get_handler`` mock pattern: no
    DB/auth fixture is needed since ``handle_http_request`` itself is
    stubbed, and this exercises the status-code mapping table further
    down in ``post`` (past Task 12's early list-body guard).
    """
    fake_handler = mock.Mock()
    fake_handler.handle_http_request.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": numeric_code, "message": "stubbed"},
    }
    request = RequestFactory().post(
        "/mcp/",
        data=b'{"jsonrpc": "2.0", "method": "ping", "id": 1}',
        content_type="application/json",
    )
    with mock.patch("mcp_server.views._get_handler", return_value=fake_handler):
        return McpHttpTransportView().post(request)


def test_parse_error_returns_http_400_not_401():
    """R3 (P0-soforthaertung task 13): PARSE_ERROR is a client body defect,
    not an auth failure — it must map to 400, not 401."""
    response = _post_with_error_frame(-32700)  # PARSE_ERROR
    assert response.status_code == 400


def test_invalid_request_returns_http_400_not_401():
    """R3 (P0-soforthaertung task 13): INVALID_REQUEST likewise maps to 400."""
    response = _post_with_error_frame(-32600)  # INVALID_REQUEST
    assert response.status_code == 400


def test_auth_failed_still_returns_http_401():
    """Regression guard: AUTH_FAILED must stay 401 after splitting the
    status-code mapping table (R3/task 13)."""
    response = _post_with_error_frame(-32000)  # AUTH_FAILED
    assert response.status_code == 401
