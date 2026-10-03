"""RES-02 (audit findings 221 + N6) — MCP rate limiting runs after authentication.

Before RES-02 the MCP transport charged the per-credential bucket *before*
authenticating, for whatever value the caller presented. Because
``McpApiKeyRateThrottle`` keys on a digest of that value, every distinct —
including every invalid — credential minted its own
``throttle_mcp_key_<sha256[:32]>`` cache entry: a single HTTP 401 filled a
bucket, and a spray of random keys grew Redis without bound against
``maxmemory 256mb`` / ``noeviction``.

The fix splits the counters (``mcp_server.throttling``) and reorders the views:

* ``check_mcp_ip_rate_limit`` runs first, keyed on the client IP only, so it
  can never create a bucket per presented credential;
* authentication validates the credential;
* ``check_mcp_key_rate_limit`` runs after, and only for the verified value.

These tests pin the observable contract, not just the call order:

* a 401 / expired-session rejection creates **no** ``throttle_mcp_key_*`` key;
* the per-IP backstop is still charged (the flood is still bounded);
* a *verified* credential does create its key bucket (positive control, so the
  "no bucket" assertions cannot pass vacuously);
* the credential is verified before the per-key bucket is charged.

No database is needed: the auth service and the handlers are stubbed, and
``settings_test`` pins the cache to ``LocMemCache`` so the real counting code
runs against an inspectable store.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest
from asgiref.sync import async_to_sync
from django.core.cache import cache, caches
from django.test import RequestFactory

from auth_tenancy.errors import AuthenticationFailed
from mcp_server.throttling import check_mcp_key_rate_limit
from mcp_server.views import McpHttpTransportView, McpMessagesView, McpSseTransportView

_BODY = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
_AUTH_FAILED_FRAME = {
    "jsonrpc": "2.0",
    "id": 1,
    "error": {"code": -32000, "message": "Authentication failed: invalid_api_key"},
}
_SUCCESS_FRAME = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle buckets are cache state; isolate every test from every other."""
    cache.clear()
    yield
    cache.clear()


def _bucket_keys(prefix: str) -> list[str]:
    """Cache keys of the default (LocMemCache) store containing *prefix*.

    DRF's ``SimpleRateThrottle.cache_format`` is ``"throttle_%(scope)s_%(ident)s"``,
    so the two MCP counters appear as ``throttle_mcp_key_*`` and
    ``throttle_mcp_ip_*``. LocMemCache stores them under the versioned key
    (``:1:throttle_mcp_key_*``), so match by containment rather than by a
    leading prefix. Reading the backing dict is the only way to assert a key
    was **not** created; a ``cache.get`` on a guessed key would pass even when a
    different key leaked.
    """
    store = getattr(caches["default"], "_cache", {})
    return [key for key in store if prefix in key]


def _valid_auth_service():
    """Auth service stub whose every key validates."""
    service = mock.Mock()
    service.validate_api_key.return_value = mock.Mock()
    return service


def _invalid_auth_service():
    """Auth service stub that rejects every key (an unknown API key)."""
    service = mock.Mock()
    service.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")
    return service


# ---------------------------------------------------------------------------
# HTTP transport — POST /mcp/
# ---------------------------------------------------------------------------


def test_authn_runs_before_key_throttle(monkeypatch):
    """The credential is verified before the per-credential bucket is charged."""
    order: list[str] = []

    service = mock.Mock()

    def _validate(_key):
        order.append("auth")
        return mock.Mock()

    service.validate_api_key.side_effect = _validate
    monkeypatch.setattr("mcp_server.views._get_auth_service", lambda: service)

    import mcp_server.views as views

    real_check = views.check_mcp_key_rate_limit

    def _spy(request, credential):
        order.append("key_throttle")
        return real_check(request, credential)

    monkeypatch.setattr("mcp_server.views.check_mcp_key_rate_limit", _spy)

    handler = mock.Mock()
    handler.handle_http_request.return_value = _SUCCESS_FRAME
    monkeypatch.setattr("mcp_server.views._get_handler", lambda: handler)

    request = RequestFactory().post(
        "/mcp/",
        data=_BODY,
        content_type="application/json",
        HTTP_X_API_KEY="reqlo_verified_key",
        REMOTE_ADDR="10.9.0.1",
    )
    response = McpHttpTransportView().post(request)

    assert response.status_code == 200
    assert order == ["auth", "key_throttle"]


def test_valid_credential_creates_a_key_bucket(monkeypatch):
    """Positive control: a verified credential *does* get its own bucket."""
    monkeypatch.setattr(
        "mcp_server.views._get_auth_service", _valid_auth_service
    )
    handler = mock.Mock()
    handler.handle_http_request.return_value = _SUCCESS_FRAME
    monkeypatch.setattr("mcp_server.views._get_handler", lambda: handler)

    request = RequestFactory().post(
        "/mcp/",
        data=_BODY,
        content_type="application/json",
        HTTP_X_API_KEY="reqlo_verified_key",
        REMOTE_ADDR="10.9.0.2",
    )
    response = McpHttpTransportView().post(request)

    assert response.status_code == 200
    assert _bucket_keys("throttle_mcp_key_"), "verified key must be counted"


def test_invalid_credential_401_creates_no_key_bucket(monkeypatch):
    """A 401 must not fill a per-credential bucket — only the IP backstop."""
    monkeypatch.setattr(
        "mcp_server.views._get_auth_service", _invalid_auth_service
    )
    handler = mock.Mock()
    handler.handle_http_request.return_value = _AUTH_FAILED_FRAME
    monkeypatch.setattr("mcp_server.views._get_handler", lambda: handler)

    request = RequestFactory().post(
        "/mcp/",
        data=_BODY,
        content_type="application/json",
        HTTP_X_API_KEY="reqlo_invalid_probe",
        REMOTE_ADDR="10.9.0.3",
    )
    response = McpHttpTransportView().post(request)

    assert response.status_code == 401
    assert _bucket_keys("throttle_mcp_key_") == []
    # The flood is still bounded: the per-IP backstop was charged.
    assert _bucket_keys("throttle_mcp_ip_")


def test_five_invalid_credentials_create_no_key_buckets(monkeypatch):
    """The finding's reproduction: 5 invalid keys, zero per-key buckets.

    Each request presents a *different* key, which the pre-fix code turned into
    five distinct cache keys. After RES-02 the per-key bucket is never reached
    for an unverified value, so the key count is zero.
    """
    monkeypatch.setattr(
        "mcp_server.views._get_auth_service", _invalid_auth_service
    )
    handler = mock.Mock()
    handler.handle_http_request.return_value = _AUTH_FAILED_FRAME
    monkeypatch.setattr("mcp_server.views._get_handler", lambda: handler)

    for i in range(5):
        response = McpHttpTransportView().post(
            RequestFactory().post(
                "/mcp/",
                data=_BODY,
                content_type="application/json",
                HTTP_X_API_KEY=f"reqlo_bogus_{i}",
                REMOTE_ADDR="10.9.0.4",
            )
        )
        assert response.status_code == 401

    assert _bucket_keys("throttle_mcp_key_") == []
    # One bucket, keyed on the IP — not five, keyed on the presented values.
    assert len(_bucket_keys("throttle_mcp_ip_")) == 1


# ---------------------------------------------------------------------------
# Message endpoint — POST /mcp/messages/
# ---------------------------------------------------------------------------


def test_messages_expired_session_creates_no_key_bucket(monkeypatch):
    """An unauthenticated session id never reaches the per-key counter."""
    monkeypatch.setattr(
        "mcp_server.sse_pubsub.get_session_api_key", lambda _sid: None
    )
    request = RequestFactory().post(
        "/mcp/messages/?session_id=expired-session",
        data=_BODY,
        content_type="application/json",
        REMOTE_ADDR="10.9.1.1",
    )
    response = McpMessagesView().post(request)

    assert response.status_code == 401
    assert json.loads(response.content)["error"]["error_code"] == "SESSION_EXPIRED"
    assert _bucket_keys("throttle_mcp_key_") == []
    assert _bucket_keys("throttle_mcp_ip_")


def test_messages_verified_session_is_charged(monkeypatch):
    """Positive control for the message endpoint: a bound session is counted."""
    monkeypatch.setattr(
        "mcp_server.sse_pubsub.get_session_api_key", lambda _sid: "reqlo_bound"
    )
    handler = mock.Mock()
    monkeypatch.setattr("mcp_server.views._get_handler", lambda: handler)
    # Do not run the background closure: the bucket is charged in the view.
    monkeypatch.setattr("mcp_server.views._message_executor", mock.Mock())

    request = RequestFactory().post(
        "/mcp/messages/?session_id=bound-session",
        data=_BODY,
        content_type="application/json",
        REMOTE_ADDR="10.9.1.2",
    )
    response = McpMessagesView().post(request)

    assert response.status_code == 202
    assert _bucket_keys("throttle_mcp_key_"), "verified session must be counted"
    assert _bucket_keys("throttle_mcp_ip_")


# ---------------------------------------------------------------------------
# SSE handshake — GET /mcp/sse/
# ---------------------------------------------------------------------------


def test_sse_invalid_key_creates_no_key_bucket(monkeypatch):
    """A rejected handshake key never mints a per-credential bucket."""
    monkeypatch.setattr(
        "mcp_server.views._get_auth_service", _invalid_auth_service
    )

    request = RequestFactory().get(
        "/mcp/sse/", HTTP_X_API_KEY="reqlo_invalid_probe", REMOTE_ADDR="10.9.2.1"
    )
    response = async_to_sync(McpSseTransportView().get)(request)

    assert response.status_code == 401
    assert _bucket_keys("throttle_mcp_key_") == []
    assert _bucket_keys("throttle_mcp_ip_")


# ---------------------------------------------------------------------------
# Counter primitive
# ---------------------------------------------------------------------------


def test_key_counter_never_charges_an_empty_credential():
    """``check_mcp_key_rate_limit("")`` touches no cache at all."""
    request = RequestFactory().post("/mcp/", REMOTE_ADDR="10.9.3.1")

    assert check_mcp_key_rate_limit(request, "") is None
    assert _bucket_keys("throttle_mcp_key_") == []
