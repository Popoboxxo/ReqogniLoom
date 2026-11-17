"""S1.2 MCP protocol contract tests (API-003, API-004, API-007).

Pins the three transport-level guarantees that the deep-dive audit found
missing:

* API-003 — every ``notifications/*`` method is id-exempt (JSON-RPC 2.0 §6)
  and gets an empty 202 instead of an INVALID_REQUEST error frame.
* API-004 — every transport-level rejection carries an integer ``error.code``
  alongside the string ``error_code`` alias, so a client can share one error
  branch across handler-level and transport-level failures.
* API-007 — a malformed throttle rate yields a plain 503 on the SSE handshake
  just as it already does (as JSON-RPC) on the synchronous HTTP transport.

All tests are DB-free: the notification path short-circuits before API-key
authentication and the throttles count through LocMemCache (settings_test).
"""
from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.test import RequestFactory, override_settings

from mcp_server.protocol_handler import JsonRpcValidator
from mcp_server.views import McpHttpTransportView, McpSseTransportView

_VALID_FRAME = {"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}}
_BODY = json.dumps(_VALID_FRAME).encode("utf-8")

_NOTIFICATION_METHODS = (
    "notifications/cancelled",
    "notifications/progress",
    "notifications/resources/updated",
    "notifications/initialized",
)


def _rates(**overrides: Any) -> dict[str, Any]:
    """Return REST_FRAMEWORK settings with only the named MCP rates replaced.

    ``override_settings`` replaces the whole setting, so the rest of the DRF
    wiring has to be carried over (same helper shape as the throttling tests).
    """
    merged = dict(settings.REST_FRAMEWORK)
    merged["DEFAULT_THROTTLE_RATES"] = {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        **overrides,
    }
    return merged


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Isolate cache-backed throttle counters between tests."""
    cache.clear()
    yield
    cache.clear()


def _post_request(**extra: Any) -> HttpRequest:
    """Build a valid JSON-RPC POST to the canonical MCP endpoint."""
    return RequestFactory().post(
        "/mcp/", data=_BODY, content_type="application/json", **extra
    )


# ---------------------------------------------------------------------------
# API-003 — notifications are id-exempt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", _NOTIFICATION_METHODS)
def test_notification_requires_no_id(method: str) -> None:
    """JSON-RPC 2.0 §6: a Request without ``id`` is a notification."""
    frame = {"jsonrpc": "2.0", "method": method, "params": {}}
    assert JsonRpcValidator.validate(frame) is None


def test_regular_method_without_id_still_invalid() -> None:
    """Control: the exemption is scoped to ``notifications/*`` only."""
    frame = {"jsonrpc": "2.0", "method": "tools/list"}
    assert JsonRpcValidator.validate(frame) == "INVALID_REQUEST"


@pytest.mark.parametrize("method", _NOTIFICATION_METHODS)
def test_notification_http_returns_empty_202(method: str) -> None:
    """The HTTP transport acknowledges every notification with an empty 202."""
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": {}}).encode(
        "utf-8"
    )
    request = RequestFactory().post(
        "/mcp/", data=body, content_type="application/json"
    )
    response = McpHttpTransportView().post(request)
    assert response.status_code == 202
    assert response.content == b""


# ---------------------------------------------------------------------------
# API-004 — transport rejections carry an integer error.code
# ---------------------------------------------------------------------------


def _transport_rejection(case: str) -> Any:
    """Drive one transport rejection path and return its HttpResponse."""
    if case == "cookie":
        return McpHttpTransportView().post(
            _post_request(HTTP_COOKIE="reqogniloom_access=abc")
        )
    if case == "bad_version":
        return McpHttpTransportView().post(
            _post_request(HTTP_MCP_PROTOCOL_VERSION="1999-01-01")
        )
    if case == "batch":
        request = RequestFactory().post(
            "/mcp/", data=b"[]", content_type="application/json"
        )
        return McpHttpTransportView().post(request)
    if case == "rate_limited":
        with override_settings(REST_FRAMEWORK=_rates(mcp_ip="0/min")):
            return McpHttpTransportView().post(_post_request())
    if case == "service_unavailable":
        with override_settings(REST_FRAMEWORK=_rates(mcp_ip="not-a-rate")):
            return McpHttpTransportView().post(_post_request())
    if case == "internal_error":
        # ``_get_handler()`` sits outside the view's try/except; the fault must
        # land in ``handle_http_request`` to exercise the 500 envelope.
        handler = mock.Mock()
        handler.handle_http_request.side_effect = RuntimeError("boom")
        with mock.patch("mcp_server.views._get_handler", return_value=handler):
            return McpHttpTransportView().post(_post_request())
    raise AssertionError(f"unknown rejection case: {case}")


@pytest.mark.parametrize(
    ("case", "status", "code", "alias"),
    [
        ("cookie", 403, -32000, "UNAUTHORIZED"),
        ("bad_version", 400, -32600, "INVALID_REQUEST"),
        ("batch", 400, -32600, "INVALID_REQUEST"),
        ("rate_limited", 429, -32007, "RATE_LIMITED"),
        ("service_unavailable", 503, -32020, "SERVICE_UNAVAILABLE"),
        ("internal_error", 500, -32603, "INTERNAL_ERROR"),
    ],
)
def test_transport_rejection_has_integer_error_code(
    case: str, status: int, code: int, alias: str
) -> None:
    """Every transport envelope exposes the same numeric code contract."""
    response = _transport_rejection(case)
    assert response.status_code == status
    error = json.loads(response.content)["error"]
    assert error["error_code"] == alias
    assert error["code"] == code
    assert isinstance(error["code"], int)


# ---------------------------------------------------------------------------
# API-007 — SSE handshake degrades to 503 on throttle misconfiguration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_scope", ["mcp_ip", "mcp_key"])
def test_sse_handshake_misconfigured_throttle_returns_plain_503(
    bad_scope: str,
) -> None:
    """A malformed MCP throttle rate must not turn the SSE GET into a 500."""
    request = RequestFactory().get("/mcp/sse/", HTTP_X_API_KEY="reqlo_test")
    auth_service = mock.Mock()
    auth_service.validate_api_key.return_value = mock.Mock()
    with override_settings(
        REST_FRAMEWORK=_rates(**{bad_scope: "not-a-rate"})
    ), mock.patch("mcp_server.views._get_auth_service", return_value=auth_service):
        response = async_to_sync(McpSseTransportView().get)(request)

    assert response.status_code == 503
    assert response["Retry-After"] == "60"
    body = json.loads(response.content)
    # Plain handshake shape, not a JSON-RPC envelope (no error.code here).
    assert isinstance(body["error"], str)
    assert "error_code" not in body


@pytest.mark.parametrize("bad_scope", ["mcp_ip", "mcp_key"])
def test_http_transport_misconfigured_throttle_stays_jsonrpc_503(
    bad_scope: str,
) -> None:
    """The synchronous transport keeps its documented JSON-RPC 503 envelope."""
    with override_settings(
        REST_FRAMEWORK=_rates(**{bad_scope: "not-a-rate"})
    ), mock.patch("mcp_server.views._credential_is_valid", return_value=True):
        response = McpHttpTransportView().post(
            _post_request(HTTP_X_API_KEY="reqlo_test")
        )

    assert response.status_code == 503
    error = json.loads(response.content)["error"]
    assert error["error_code"] == "SERVICE_UNAVAILABLE"
    assert error["code"] == -32020
