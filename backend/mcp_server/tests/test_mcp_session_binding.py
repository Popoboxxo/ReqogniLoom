"""API-002 — MCP session-id hardening regression tests.

Pins the backward-compatible rollout of the SSE ``Mcp-Session-Id`` header as
the primary credential channel (the legacy ``?session_id=`` query fallback
stays alive for one release) and the Streamable-HTTP ``DELETE`` bound-key
proof requirement.

The session id is a credential: these tests also assert it is never written
to logs and that the MCP tool contract (registry/manifest) is untouched by
this transport-only change.

leaf_id : COMP-MC-001 (McpMessagesView, McpHttpTransportView)
req_id  : REQ-L2-MC-005 / REQ-L2-MC-006 (transport + API-key auth)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest import mock

import pytest
from django.test import RequestFactory

from mcp_server.views import McpHttpTransportView, McpMessagesView

_BOUND_KEY = "reqlo_bound_key_for_session"
_SESSION_ID = "session-id-primary-channel"
_BODY = b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}'


def _post_messages(*, header_session: str | None, query_session: str | None):
    """POST to ``/mcp/messages/`` with the given session-id channels."""
    url = "/mcp/messages/"
    if query_session is not None:
        url = f"{url}?session_id={query_session}"
    kwargs: dict[str, object] = {}
    if header_session is not None:
        kwargs["HTTP_MCP_SESSION_ID"] = header_session
    return RequestFactory().post(
        url, data=_BODY, content_type="application/json", **kwargs
    )


def _dispatch_synchronously(request):
    """Run McpMessagesView.post with the Redis/publish/executor seams mocked.

    Returns ``(response, forwarded_headers, get_key_mock)``. The handler is a
    fake so the test needs no real tool stack or database rows.
    """
    forwarded_headers: dict[str, str] = {}

    def _handle(body: bytes, headers: dict) -> dict:
        forwarded_headers.update(headers)
        return {"jsonrpc": "2.0", "id": 1, "result": {}}

    with mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=_BOUND_KEY
    ) as get_key, mock.patch(
        "mcp_server.sse_pubsub.publish_mcp_message"
    ), mock.patch(
        "mcp_server.views._get_handler"
    ) as get_handler, mock.patch(
        "mcp_server.views._message_executor"
    ) as executor:
        get_handler.return_value.handle_http_request.side_effect = _handle
        executor.submit.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        response = McpMessagesView().post(request)

    return response, forwarded_headers, get_key


# ---------------------------------------------------------------------------
# (a) Header-only POST: primary credential channel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_header_only_post_dispatches_with_bound_key() -> None:
    """``Mcp-Session-Id`` alone is accepted and the bound key drives dispatch."""
    request = _post_messages(header_session=_SESSION_ID, query_session=None)
    response, headers, get_key = _dispatch_synchronously(request)

    assert response.status_code == 202
    get_key.assert_called_once_with(_SESSION_ID)
    assert headers["HTTP_X_API_KEY"] == _BOUND_KEY
    assert headers["HTTP_AUTHORIZATION"] == f"Bearer {_BOUND_KEY}"
    # The secure channel emits no deprecation signal.
    assert "Deprecation" not in response


# ---------------------------------------------------------------------------
# (b) Legacy query path still works, with a deprecation signal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_legacy_query_post_still_accepted_with_deprecation_signal() -> None:
    """The 202 response stays; RFC 9745/8594 headers tell clients to migrate."""
    request = _post_messages(header_session=None, query_session=_SESSION_ID)
    response, headers, get_key = _dispatch_synchronously(request)

    assert response.status_code == 202
    get_key.assert_called_once_with(_SESSION_ID)
    assert headers["HTTP_X_API_KEY"] == _BOUND_KEY
    assert response["Deprecation"] == "true"
    assert "Sunset" in response


@pytest.mark.django_db
def test_header_wins_over_legacy_query_without_deprecation() -> None:
    """A header caller is never marked deprecated by an extra query param."""
    request = _post_messages(
        header_session=_SESSION_ID, query_session="stale-query-session"
    )
    response, _headers, get_key = _dispatch_synchronously(request)

    assert response.status_code == 202
    get_key.assert_called_once_with(_SESSION_ID)
    assert "Deprecation" not in response
    assert "Sunset" not in response


@pytest.mark.django_db
def test_legacy_query_deprecation_signal_also_on_rejection() -> None:
    """Even a rejected legacy call carries the migration hint."""
    request = _post_messages(header_session=None, query_session=_SESSION_ID)
    with mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=None
    ), mock.patch("mcp_server.views._get_handler") as get_handler:
        response = McpMessagesView().post(request)

    assert response.status_code == 401
    assert response["Deprecation"] == "true"
    get_handler.assert_not_called()


# ---------------------------------------------------------------------------
# (c) DELETE without bound-key proof is rejected and deletes nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra_kwargs",
    [
        {},  # no key at all
        {"HTTP_X_API_KEY": "reqlo_wrong_key"},  # wrong key
        {"HTTP_AUTHORIZATION": "Bearer reqlo_wrong_key"},  # wrong bearer key
    ],
)
def test_delete_without_bound_key_proof_is_rejected(extra_kwargs: dict) -> None:
    """A session id alone never revokes a session (API-002)."""
    request = RequestFactory().delete(
        "/mcp/", HTTP_MCP_SESSION_ID=_SESSION_ID, **extra_kwargs
    )
    with mock.patch(
        "mcp_server.views.get_session_api_key", return_value=_BOUND_KEY
    ), mock.patch("mcp_server.views.delete_session_api_key") as delete:
        response = McpHttpTransportView().delete(request)

    assert response.status_code == 403
    delete.assert_not_called()


def test_delete_unknown_session_is_404_and_deletes_nothing() -> None:
    request = RequestFactory().delete(
        "/mcp/", HTTP_MCP_SESSION_ID=_SESSION_ID, HTTP_X_API_KEY=_BOUND_KEY
    )
    with mock.patch(
        "mcp_server.views.get_session_api_key", return_value=None
    ), mock.patch("mcp_server.views.delete_session_api_key") as delete:
        response = McpHttpTransportView().delete(request)

    assert response.status_code == 404
    delete.assert_not_called()


# ---------------------------------------------------------------------------
# (d) DELETE with bound key succeeds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("header", ["HTTP_X_API_KEY", "HTTP_AUTHORIZATION"])
def test_delete_with_bound_key_succeeds(header: str) -> None:
    """Both supported credential headers satisfy the bound-key proof."""
    value = _BOUND_KEY if header == "HTTP_X_API_KEY" else f"Bearer {_BOUND_KEY}"
    request = RequestFactory().delete(
        "/mcp/", HTTP_MCP_SESSION_ID=_SESSION_ID, **{header: value}
    )
    with mock.patch(
        "mcp_server.views.get_session_api_key", return_value=_BOUND_KEY
    ), mock.patch("mcp_server.views.delete_session_api_key") as delete:
        response = McpHttpTransportView().delete(request)

    assert response.status_code == 204
    delete.assert_called_once_with(_SESSION_ID)


# ---------------------------------------------------------------------------
# (3) The session id is a credential: never written to logs
# ---------------------------------------------------------------------------


def test_delete_rejection_does_not_log_the_session_id(caplog) -> None:
    secret_session_id = "never-log-this-session-credential"
    request = RequestFactory().delete(
        "/mcp/", HTTP_MCP_SESSION_ID=secret_session_id
    )
    with mock.patch(
        "mcp_server.views.get_session_api_key", return_value=_BOUND_KEY
    ), mock.patch("mcp_server.views.delete_session_api_key"):
        with caplog.at_level(logging.WARNING):
            response = McpHttpTransportView().delete(request)

    assert response.status_code == 403
    assert secret_session_id not in caplog.text


# ---------------------------------------------------------------------------
# (e) Transport-only change: tool registry / manifest contract untouched
# ---------------------------------------------------------------------------


def test_session_hardening_does_not_change_tool_contract() -> None:
    """The live tool manifest still matches the committed one after API-002."""
    from mcp_server.management.commands.export_tool_manifest import (
        _MANIFEST_SUFFIX,
        build_manifest,
    )

    repo_root = Path(__file__).resolve().parents[3]
    committed = json.loads((repo_root / _MANIFEST_SUFFIX).read_text(encoding="utf-8"))
    live = build_manifest()

    assert live["tool_count"] == committed["tool_count"]
    assert {tool["name"] for tool in live["tools"]} == {
        tool["name"] for tool in committed["tools"]
    }
