"""
End-to-end tests for the SSE transport endpoint.

leaf_id : COMP-MC-001 (ProtocolHandler) + McpSseTransportView
req_id  : REQ-L2-MC-005 (HTTP/SSE transport),
          REQ-L2-MC-006 (API-key auth),
          REQ-L2-MC-007 (RBAC),
          REQ-L2-MC-011 (structured error response)

Architecture change (REQ-044 / DEEP_SYSTEM_ANALYSIS.md BE-20):
    The SSE endpoint changed from a synchronous POST-response pattern
    (one POST → one SSE stream response) to the standard MCP SSE protocol:

      GET  /mcp/sse/                    → establish SSE stream (returns 200 stream)
      POST /mcp/messages/?session_id=…  → send JSON-RPC messages to an active session

    This change was required because the original synchronous McpSseTransportView
    caused a TypeError under ASGI (CorsMixin.dispatch is sync; GET handler async).

SA-61 (SYSTEMAUDIT_2026-08-27 §4.8): the six tests that verified the old
POST-to-SSE pattern used to be permanently ``@pytest.mark.skip``'d with no
path to reactivation. They are replaced below by two kinds of active,
non-skipped regression coverage:

  1. "Message-dispatch" tests (``test_sse_message_*``): they POST to
     ``McpMessagesView`` (the endpoint that used to be reached indirectly via
     the old synchronous SSE POST) and assert on the JSON-RPC frame that
     would be published to the SSE stream. Only the Redis-backed session
     store / publish call are mocked (mirroring the established pattern in
     ``test_sse_session_auth.py``); dispatch runs through the REAL
     ``ProtocolHandler`` / ``ToolRegistry`` stack against the real test
     database. This is the part of the SSE transport most likely to
     regress and it needs no live Redis / live server, so it runs in the
     normal unit suite.

  2. One genuine full-stack round trip (``test_sse_live_redis_round_trip_*``)
     that publishes a message via the real ``sse_pubsub.publish_mcp_message``
     and reads it back through the real ``async_sse_generator`` against a
     live Redis. This is the piece that structurally needs a reachable Redis
     (the project's test settings point ``CELERY_BROKER_URL`` at
     ``memory://``, see ``reqogniloom/settings_test.py``), so it is marked
     with the project's existing ``integration`` marker (see
     ``mcp_server/tests/test_mcp_api_key_roles.py`` for the established
     precedent) and skips cleanly — instead of hanging or failing — when no
     live Redis is reachable (e.g. a bare ``pytest`` run outside
     docker-compose) or in CI. Run it explicitly via:

        docker compose run --rm backend pytest \
            mcp_server/tests/test_e2e_sse_transport.py -m integration -v

    Note on "auth failure": in the new architecture the message endpoint's
    only credential is ``session_id`` (the API key is bound to it once, at
    the SSE handshake — REQ-018 / SYSTEM_AUDIT P-02); an invalid/expired
    session on THIS endpoint therefore surfaces as ``SESSION_EXPIRED``
    (401), which is already covered by
    ``test_sse_session_auth.py::test_messages_invalid_session_is_rejected``.
    A rejected API key at the handshake itself (the old "AUTH_FAILED" case)
    is covered by ``test_sse_session_auth.py::
    test_sse_handshake_with_invalid_key_returns_401``. Neither case is
    re-duplicated here.

Note on error_code vs code (REQ-090):
    ErrorFormatter.format_error emits {"code": <numeric>} per JSON-RPC 2.0 spec.
    Numeric codes are defined in mcp_server.protocol_handler.ERROR_CODE_MAP.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Tuple
from unittest import mock
from uuid import uuid4

import pytest
from django.test import Client, RequestFactory, override_settings

from mcp_server.tests.helpers import make_jsonrpc_request
from mcp_server.views import McpMessagesView

# SYSTEMAUDIT SA-62: classification marker for the `test_e2e_*.py` family —
# see the `e2e` marker docstring in pyproject.toml. Composes with the
# `@pytest.mark.integration` on the one test below that genuinely needs a
# live Redis (module-level pytestmark + function decorators both apply).
pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# New tests: correct GET endpoint behaviour (REQ-085)
# ---------------------------------------------------------------------------


def test_sse_get_without_api_key_returns_401() -> None:
    """[REQ-085] GET /mcp/sse/ without API key returns 401.

    The unauthenticated path is entirely in-memory (no Redis pub/sub required)
    and works with the synchronous Django test client via async_to_sync wrapping.
    """
    client = Client()
    response = client.get("/mcp/sse/")
    assert response.status_code == 401, (
        f"Expected 401 (Authentication required), got {response.status_code}. "
        "The SSE GET endpoint must reject unauthenticated handshake attempts."
    )


def test_sse_options_returns_cors_headers() -> None:
    """[REQ-085] OPTIONS /mcp/sse/ returns CORS headers for preflight.

    Must send an allowlisted Origin: since the CORS fallback for a
    non-allowlisted (or missing) Origin now omits Access-Control-Allow-Origin
    entirely (rather than mirroring an arbitrary allowlist entry), a
    preflight without a real cross-origin Origin header would no longer
    carry the header.
    """
    client = Client()
    response = client.options("/mcp/sse/", HTTP_ORIGIN="http://localhost:3000")
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" in response, (
        "OPTIONS must include CORS headers so browsers can make SSE connections."
    )


def test_sse_options_non_allowlisted_origin_omits_cors_header() -> None:
    """[REQ-081] OPTIONS /mcp/sse/ with a non-allowlisted Origin must not
    carry Access-Control-Allow-Origin at all.

    Previously the CORS fallback mirrored the first configured allowlist
    entry for any non-allowlisted origin, which is misleading metadata (the
    origin was never actually allowed). The header must now be omitted
    entirely.
    """
    client = Client()
    response = client.options("/mcp/sse/", HTTP_ORIGIN="https://evil.example.com")
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response, (
        "A non-allowlisted Origin must not receive an Access-Control-Allow-Origin "
        "header (neither its own origin nor any other allowlist entry)."
    )


def test_sse_post_returns_405_method_not_allowed() -> None:
    """[REQ-085] POST /mcp/sse/ returns 405 (old API is gone).

    JSON-RPC messages are no longer POSTed to /mcp/sse/. They go to
    POST /mcp/messages/?session_id=<id> after an authenticated SSE handshake.
    """
    client = Client()
    body = json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 1}).encode()
    response = client.post("/mcp/sse/", data=body, content_type="application/json")
    assert response.status_code == 405, (
        f"Expected 405 Method Not Allowed for POST /mcp/sse/, got {response.status_code}."
    )


# ---------------------------------------------------------------------------
# Message-dispatch tests (new architecture, REQ-085 Part B)
#
# These replace the five permanently-skipped POST-to-SSE tests. They exercise
# the REAL ProtocolHandler / ToolRegistry stack (RBAC, tenant isolation,
# error formatting) through McpMessagesView.post(); only the Redis-backed
# session store and the SSE publish call are mocked out, so no live Redis /
# live server is required.
# ---------------------------------------------------------------------------


def _dispatch_message(
    session_id: str,
    api_key: str,
    body: bytes,
) -> Dict[str, Any]:
    """POST *body* to ``/mcp/messages/`` for *session_id* and return the
    single JSON-RPC frame that would have been published to the SSE stream.
    """
    request = RequestFactory().post(
        f"/mcp/messages/?session_id={session_id}",
        data=body,
        content_type="application/json",
    )
    published: List[Tuple[str, Dict[str, Any]]] = []

    def _capture(sid: str, message: Dict[str, Any]) -> None:
        published.append((sid, message))

    with mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=api_key
    ), mock.patch(
        "mcp_server.sse_pubsub.publish_mcp_message", side_effect=_capture
    ), mock.patch(
        "mcp_server.views._message_executor"
    ) as executor:
        # Run the bounded-pool work synchronously so we can assert on it
        # (same pattern as test_sse_session_auth.py).
        executor.submit.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        response = McpMessagesView().post(request)

    assert response.status_code == 202, response.content
    assert len(published) == 1, f"Expected exactly one published frame, got {published}"
    return published[0][1]


@pytest.mark.django_db(transaction=True)
def test_sse_message_read_tool_publishes_result_event(
    e2e_workspace,
    e2e_user_admin,
    e2e_api_key_admin: str,
    e2e_userrole_admin,
) -> None:
    """[REQ-085 Part B] A read tool call published via the message endpoint
    yields a result frame (replaces the skipped
    ``test_sse_read_tool_returns_event_stream_with_result``)."""
    session_id = str(uuid4())
    body = make_jsonrpc_request(
        "workspace.get_context", {"workspace_id": str(e2e_workspace.id)}, request_id=1
    )

    frame = _dispatch_message(session_id, e2e_api_key_admin, body)

    assert frame["jsonrpc"] == "2.0"
    assert frame["id"] == 1
    assert "result" in frame, f"Expected a result frame, got: {frame}"
    assert "workspace_context" in frame["result"]


@pytest.mark.django_db(transaction=True)
def test_sse_message_write_tool_publishes_result_event(
    e2e_workspace,
    e2e_user_admin,
    e2e_api_key_admin: str,
    e2e_userrole_admin,
) -> None:
    """[REQ-085 Part B] A write tool call published via the message endpoint
    yields a result frame with the created entity (replaces the skipped
    ``test_sse_write_tool_returns_event_stream_with_result``)."""
    session_id = str(uuid4())
    body = make_jsonrpc_request(
        "requirement.create",
        {"title": "SSE E2E Requirement", "workspace_id": str(e2e_workspace.id)},
        request_id=2,
    )

    frame = _dispatch_message(session_id, e2e_api_key_admin, body)

    assert frame["id"] == 2
    assert "result" in frame, f"Expected a result frame, got: {frame}"
    assert frame["result"]["requirement"]["title"] == "SSE E2E Requirement"


@pytest.mark.django_db(transaction=True)
def test_sse_message_not_found_publishes_error_event(
    e2e_workspace,
    e2e_user_admin,
    e2e_api_key_admin: str,
    e2e_userrole_admin,
) -> None:
    """[REQ-085 Part B / REQ-090] A NOT_FOUND tool error published via the
    message endpoint carries the numeric code -32004 (replaces the skipped
    ``test_sse_error_case_returns_event_stream_with_error``; NOT_FOUND ->
    -32004 per ERROR_CODE_MAP)."""
    session_id = str(uuid4())
    body = make_jsonrpc_request(
        "requirement.get",
        {"id": str(uuid4()), "workspace_id": str(e2e_workspace.id)},
        request_id=3,
    )

    frame = _dispatch_message(session_id, e2e_api_key_admin, body)

    assert frame["id"] == 3
    assert "error" in frame, f"Expected an error frame, got: {frame}"
    assert frame["error"]["code"] == -32004


@pytest.mark.django_db(transaction=True)
def test_sse_message_rbac_denial_publishes_permission_error_event(
    e2e_workspace,
    e2e_user_viewer,
    e2e_api_key_viewer: str,
    e2e_userrole_viewer,
) -> None:
    """[REQ-085 Part B / REQ-090] A viewer's write-tool call published via
    the message endpoint yields PERMISSION_DENIED (-32001) (replaces the
    skipped ``test_sse_rbac_denial_returns_event_stream_with_permission_error``)."""
    session_id = str(uuid4())
    body = make_jsonrpc_request(
        "requirement.create",
        {"title": "Should Be Denied", "workspace_id": str(e2e_workspace.id)},
        request_id=4,
    )

    frame = _dispatch_message(session_id, e2e_api_key_viewer, body)

    assert frame["id"] == 4
    assert "error" in frame, f"Expected an error frame, got: {frame}"
    assert frame["error"]["code"] == -32001


@pytest.mark.django_db(transaction=True)
def test_sse_message_malformed_json_publishes_parse_error_event() -> None:
    """[REQ-085 Part B / REQ-090] A malformed JSON body published via the
    message endpoint yields PARSE_ERROR (-32700) (replaces the skipped
    ``test_sse_parse_error_returns_event_stream_with_parse_error``).

    The parse-error path in ``ProtocolHandler.handle`` is checked before any
    API-key/session validation, so the session/api-key values here are
    arbitrary placeholders.
    """
    session_id = str(uuid4())
    frame = _dispatch_message(session_id, "reqlo_placeholder", b"{not valid json")

    assert frame["id"] is None
    assert "error" in frame, f"Expected an error frame, got: {frame}"
    assert frame["error"]["code"] == -32700


# ---------------------------------------------------------------------------
# Live Redis round trip (integration marker — see conventions in
# test_mcp_api_key_roles.py). Requires a reachable Redis; the project's test
# settings point CELERY_BROKER_URL at "memory://" (settings_test.py), so this
# is deliberately NOT part of the default unit suite.
# ---------------------------------------------------------------------------


def _integration_redis_url() -> str:
    """Build a real Redis URL from env vars, matching docker-compose defaults."""
    host = os.environ.get("REDIS_HOST", "redis")
    port = os.environ.get("REDIS_PORT", "6379")
    password = os.environ.get("REDIS_PASSWORD", "")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/0"


def _redis_reachable(url: str) -> bool:
    """Best-effort PING against *url* with a short timeout; never raises."""
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=1)
        return bool(client.ping())
    except Exception:
        return False


_INTEGRATION_REDIS_URL = _integration_redis_url()
_REDIS_REACHABLE = _redis_reachable(_INTEGRATION_REDIS_URL)


@pytest.mark.integration
@pytest.mark.skipif(
    bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")),
    reason="SSE live-Redis round trip requires a reachable Redis (skipped in CI)",
)
@pytest.mark.skipif(
    not _REDIS_REACHABLE,
    reason=(
        "SSE live-Redis round trip requires a reachable Redis at "
        f"{_INTEGRATION_REDIS_URL}. Run inside the docker-compose backend "
        "container: docker compose run --rm backend pytest "
        "mcp_server/tests/test_e2e_sse_transport.py -m integration -v"
    ),
)
def test_sse_live_redis_round_trip_delivers_published_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[REQ-085 / REQ-107] A message published via ``publish_mcp_message``
    is actually delivered through ``async_sse_generator`` when read back
    against a real Redis — the one piece of the SSE transport that
    structurally needs live infrastructure to verify end-to-end.

    Publishes the message BEFORE opening the generator and replays it via
    the ``last_event_id`` buffer (REQ-107) rather than racing a live
    subscribe/publish, so the test is deterministic. Consumes only the
    known-finite number of chunks produced before the generator's
    infinite keepalive loop, then closes it — it never waits on the
    15s keepalive timeout.
    """
    from mcp_server import sse_pubsub

    # The module caches a Redis connection pool keyed to whatever
    # CELERY_BROKER_URL was in effect on first use; reset it so our
    # override below actually takes effect regardless of test order.
    monkeypatch.setattr(sse_pubsub, "_redis_pool", None)

    session_id = str(uuid4())
    endpoint_url = f"/mcp/messages/?session_id={session_id}"
    message = {"jsonrpc": "2.0", "id": 99, "result": {"ok": True}}

    async def _consume() -> List[str]:
        chunks: List[str] = []
        gen = sse_pubsub.async_sse_generator(session_id, endpoint_url, last_event_id=0)
        try:
            # Exactly 5 chunks are yielded before the generator enters its
            # infinite live-streaming loop: "event: endpoint\n", "data: ...\n\n"
            # (handshake), then "id: ...\n", "event: message\n", "data: ...\n\n"
            # for the one replayed event.
            for _ in range(5):
                chunks.append(await gen.__anext__())
        finally:
            await gen.aclose()
        return chunks

    with override_settings(CELERY_BROKER_URL=_INTEGRATION_REDIS_URL):
        sse_pubsub.publish_mcp_message(session_id, message)
        chunks = asyncio.run(_consume())

    stream = "".join(chunks)
    assert "event: endpoint" in stream
    assert f"data: {endpoint_url}" in stream
    assert "event: message" in stream
    assert json.dumps(message) in stream
