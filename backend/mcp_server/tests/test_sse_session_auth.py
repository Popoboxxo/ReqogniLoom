"""
Unit tests for the SSE session-binding security fix (REQ-018 / SYSTEM_AUDIT P-02).

Verifies that the MCP SSE transport no longer embeds the API key in the
message-endpoint URL and instead binds the authenticated key to the session
server-side:

  (a) the SSE ``endpoint`` URL contains only ``session_id`` — never ``api_key``;
  (b) a message POST with a valid ``session_id`` (and no ``api_key`` in the URL)
      is accepted (HTTP 202) using the server-side session binding;
  (c) a message POST with an unknown/expired ``session_id`` is rejected (HTTP 401).

These tests mock the Redis-backed session store and the background handler so
they run without a live Redis / full application stack.

leaf_id : COMP-MC-001 (McpSseTransportView, McpMessagesView)
req_id  : REQ-018 (SYSTEM_AUDIT P-02 — no API key in SSE URL)
"""
from __future__ import annotations

from typing import AsyncGenerator, List, Optional, Tuple
from unittest import mock

from asgiref.sync import async_to_sync
from django.test import RequestFactory

from mcp_server.views import McpMessagesView, McpSseTransportView


_API_KEY = "rfk_test_key_value"


# ---------------------------------------------------------------------------
# (a) SSE endpoint URL must not contain the API key
# ---------------------------------------------------------------------------


def test_sse_endpoint_url_excludes_api_key() -> None:
    """The SSE ``endpoint`` event URL carries only ``session_id`` — no api_key."""
    captured: List[Tuple[str, str]] = []

    def _fake_generator(
        session_id: str, endpoint_url: str, last_event_id: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        captured.append((session_id, endpoint_url))

        async def _gen() -> AsyncGenerator[str, None]:
            yield "event: endpoint\n"
            yield f"data: {endpoint_url}\n\n"

        return _gen()

    request = RequestFactory().get("/mcp/sse/", HTTP_X_API_KEY=_API_KEY)
    view = McpSseTransportView()

    auth_svc = mock.Mock()
    auth_svc.validate_api_key.return_value = mock.Mock()

    with mock.patch(
        "mcp_server.sse_pubsub.async_sse_generator", side_effect=_fake_generator
    ), mock.patch("mcp_server.sse_pubsub.store_session_api_key") as store, mock.patch(
        "mcp_server.views._get_auth_service", return_value=auth_svc
    ):
        response = async_to_sync(view.get)(request)

    auth_svc.validate_api_key.assert_called_once_with(_API_KEY)

    assert response.status_code == 200
    assert len(captured) == 1
    session_id, endpoint_url = captured[0]

    # The key must be bound server-side to the session...
    store.assert_called_once_with(session_id, _API_KEY)
    # ...and must NOT appear anywhere in the URL handed to the client.
    assert "api_key" not in endpoint_url
    assert _API_KEY not in endpoint_url
    assert endpoint_url == f"/mcp/messages/?session_id={session_id}"


# ---------------------------------------------------------------------------
# (b) Message POST with a valid session (no api_key in URL) is accepted
# ---------------------------------------------------------------------------


def test_messages_valid_session_is_accepted_without_api_key_in_url() -> None:
    """A valid ``session_id`` authorises the POST via the server-side binding."""
    session_id = "11111111-1111-1111-1111-111111111111"
    request = RequestFactory().post(
        f"/mcp/messages/?session_id={session_id}",
        data=b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}',
        content_type="application/json",
    )

    forwarded_headers: dict = {}

    fake_handler = mock.Mock()

    def _handle(body: bytes, headers: dict) -> dict:
        forwarded_headers.update(headers)
        return {"jsonrpc": "2.0", "id": 1, "result": {}}

    fake_handler.handle_http_request.side_effect = _handle

    with mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=_API_KEY
    ) as get_key, mock.patch(
        "mcp_server.sse_pubsub.publish_mcp_message"
    ), mock.patch(
        "mcp_server.views._get_handler", return_value=fake_handler
    ), mock.patch(
        "mcp_server.views._message_executor"
    ) as executor:
        # Run the bounded-pool work synchronously so we can assert on it.
        executor.submit.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        response = McpMessagesView().post(request)

    assert response.status_code == 202
    get_key.assert_called_once_with(session_id)
    # The handler received the session-bound key, not one from the URL.
    assert forwarded_headers["HTTP_X_API_KEY"] == _API_KEY
    assert forwarded_headers["HTTP_AUTHORIZATION"] == f"Bearer {_API_KEY}"


# ---------------------------------------------------------------------------
# (c) Message POST with an unknown/expired session is rejected
# ---------------------------------------------------------------------------


def test_messages_invalid_session_is_rejected() -> None:
    """An unknown ``session_id`` yields HTTP 401 and never dispatches the tool."""
    session_id = "does-not-exist"
    request = RequestFactory().post(
        f"/mcp/messages/?session_id={session_id}",
        data=b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}',
        content_type="application/json",
    )

    unbound: Optional[str] = None
    with mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=unbound
    ), mock.patch("mcp_server.views._get_handler") as get_handler, mock.patch(
        "mcp_server.views._message_executor"
    ) as executor:
        response = McpMessagesView().post(request)

    assert response.status_code == 401
    # No handler dispatch and no background work for an unauthorised session.
    get_handler.assert_not_called()
    executor.submit.assert_not_called()


# ---------------------------------------------------------------------------
# (d) Session api key is encrypted at rest in Redis (REQ-036 / audit BE-5)
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Minimal in-memory Redis stand-in capturing stored values."""

    def __init__(self) -> None:
        self.store: dict = {}

    def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self.store[key] = value

    def get(self, key: str):
        return self.store.get(key)


def test_session_api_key_is_encrypted_at_rest_and_round_trips() -> None:
    """Stored value is Django-signed (not plaintext) yet decrypts back to the key."""
    from mcp_server import sse_pubsub

    session_id = "22222222-2222-2222-2222-222222222222"
    fake = _FakeRedis()

    with mock.patch(
        "mcp_server.sse_pubsub._get_redis_client", return_value=fake
    ):
        sse_pubsub.store_session_api_key(session_id, _API_KEY)

        # The raw Redis value must not expose the plaintext key.
        stored = fake.store[sse_pubsub._session_auth_key(session_id)]
        assert _API_KEY not in stored
        assert stored != _API_KEY

        # Reading back yields the original plaintext for the auth flow.
        assert sse_pubsub.get_session_api_key(session_id) == _API_KEY


def test_tampered_session_api_key_returns_none() -> None:
    """A value with a broken signature is treated as unknown (BadSignature -> None)."""
    from mcp_server import sse_pubsub

    session_id = "33333333-3333-3333-3333-333333333333"
    fake = _FakeRedis()
    fake.store[sse_pubsub._session_auth_key(session_id)] = "tampered:not-a-signature"

    with mock.patch(
        "mcp_server.sse_pubsub._get_redis_client", return_value=fake
    ):
        assert sse_pubsub.get_session_api_key(session_id) is None


# ---------------------------------------------------------------------------
# (e) SSE handshake is authenticated over the async request path (REQ-044)
#
# The endpoint is fully async and must not crash (previously the sync CorsMixin
# raised a TypeError on every GET). These tests exercise the real ASGI request
# path via Django's AsyncClient.
# ---------------------------------------------------------------------------


def _fake_sse_generator(
    session_id: str, endpoint_url: str, last_event_id: Optional[int] = None
) -> AsyncGenerator[str, None]:
    """Redis-free stand-in for the SSE event generator."""

    async def _gen() -> AsyncGenerator[str, None]:
        yield "event: endpoint\n"
        yield f"data: {endpoint_url}\n\n"

    return _gen()


def test_sse_handshake_without_key_returns_401() -> None:
    """GET /mcp/sse/ without any API key is rejected (401) — no stream opened."""
    from django.test import AsyncClient

    response = async_to_sync(AsyncClient().get)("/mcp/sse/")

    assert response.status_code == 401
    assert response["Content-Type"] == "application/json"
    assert response.json() == {"error": "Authentication required"}


def test_sse_handshake_with_valid_key_opens_event_stream() -> None:
    """GET /mcp/sse/ with a valid API key returns a 200 text/event-stream."""
    from django.test import AsyncClient

    auth_svc = mock.Mock()
    auth_svc.validate_api_key.return_value = mock.Mock()

    with mock.patch(
        "mcp_server.views._get_auth_service", return_value=auth_svc
    ), mock.patch(
        "mcp_server.sse_pubsub.async_sse_generator", side_effect=_fake_sse_generator
    ), mock.patch("mcp_server.sse_pubsub.store_session_api_key") as store:
        response = async_to_sync(AsyncClient().get)(
            "/mcp/sse/", headers={"x-api-key": _API_KEY}
        )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"
    assert response["Cache-Control"] == "no-cache"
    auth_svc.validate_api_key.assert_called_once_with(_API_KEY)
    store.assert_called_once()


def test_sse_handshake_with_invalid_key_returns_401() -> None:
    """A syntactically present but invalid API key is rejected (401)."""
    from django.test import AsyncClient

    from auth_tenancy.errors import AuthenticationFailed

    auth_svc = mock.Mock()
    auth_svc.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")

    with mock.patch(
        "mcp_server.views._get_auth_service", return_value=auth_svc
    ), mock.patch("mcp_server.sse_pubsub.store_session_api_key") as store:
        response = async_to_sync(AsyncClient().get)(
            "/mcp/sse/", headers={"x-api-key": "rfk_bogus"}
        )

    assert response.status_code == 401
    assert response.json() == {"error": "Authentication required"}
    store.assert_not_called()
