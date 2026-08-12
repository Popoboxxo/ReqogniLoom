"""The SSE response must not carry hop-by-hop headers (issue #455).

``GET /mcp/sse/`` answered HTTP 500 on every request under ``manage.py
runserver``: the view set ``Connection: keep-alive``, and PEP 3333 forbids a
WSGI application from emitting hop-by-hop headers. wsgiref enforces that with a
bare ``assert not is_hop_by_hop(name)`` in
``wsgiref.handlers.BaseHandler.start_response``, which raised
``AssertionError: Hop-by-hop header, 'Connection: keep-alive', not allowed``
before a single byte of the stream was written.

The production stack (gunicorn + UvicornWorker) tolerated the header, so this
was a development-only outage — but every shipped plugin config connects with
``"type": "sse"``, which made the whole transport unusable against a dev server.

Guarding the property (no hop-by-hop headers) rather than the single header
name keeps a future ``Keep-Alive``/``Transfer-Encoding`` addition from
reintroducing the same class of bug.

leaf_id : COMP-MC-001 (McpSseTransportView)
req_id  : REQ-L2-MC-005 (SSE transport)
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional
from unittest import mock
from wsgiref.util import is_hop_by_hop

from asgiref.sync import async_to_sync
from django.test import RequestFactory

from mcp_server.views import McpSseTransportView

_API_KEY = "reqlo_test_key_value"


def _open_stream():
    """Perform an authenticated SSE handshake and return the response."""

    def _fake_generator(
        session_id: str, endpoint_url: str, last_event_id: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        async def _gen() -> AsyncGenerator[str, None]:
            yield f"data: {endpoint_url}\n\n"

        return _gen()

    request = RequestFactory().get("/mcp/sse/", HTTP_X_API_KEY=_API_KEY)
    auth_svc = mock.Mock()
    auth_svc.validate_api_key.return_value = mock.Mock()

    with mock.patch(
        "mcp_server.sse_pubsub.async_sse_generator", side_effect=_fake_generator
    ), mock.patch(
        "mcp_server.sse_pubsub.store_session_api_key"
    ), mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=None
    ), mock.patch(
        "mcp_server.views._get_auth_service", return_value=auth_svc
    ):
        return async_to_sync(McpSseTransportView().get)(request)


def test_sse_response_sets_no_hop_by_hop_headers() -> None:
    """No response header may be hop-by-hop — wsgiref rejects those outright."""
    response = _open_stream()

    offending = [name for name, _ in response.items() if is_hop_by_hop(name)]
    assert not offending, (
        "SSE response carries hop-by-hop header(s) "
        f"{offending}; PEP 3333 forbids them and wsgiref answers 500 (issue #455)."
    )


def test_sse_response_still_disables_caching() -> None:
    """Removing Connection must not take the required Cache-Control with it."""
    response = _open_stream()

    assert response["Cache-Control"] == "no-cache"
    assert response["Content-Type"] == "text/event-stream"
    assert response.status_code == 200
