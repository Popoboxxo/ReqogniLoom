"""SA-36 regression tests — the invariant behind ``csrf_exempt`` on MCP views.

SYSTEMAUDIT-2026-08-27 §4.6 F15: the three MCP transport views are
``csrf_exempt``. That is correct *today* only because the transport
authenticates from request headers (or, for the SSE message endpoint, an
unguessable session id) and never from an ambient browser cookie — a
cross-site request carries cookies but not headers, so there is nothing to ride.

The finding was that nothing enforced it: if the MCP path ever started honouring
``reqogniloom_access``, the CSRF hole would open silently. These tests pin the
guard so that regression fails loudly instead.
"""
from __future__ import annotations

import json

import pytest
from django.test import Client

MCP_URL = "/mcp/"


def _body() -> str:
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})


def _post(client: Client, **extra):
    return client.post(
        MCP_URL, data=_body(), content_type="application/json", **extra
    )


@pytest.mark.django_db
def test_cookie_only_request_is_rejected():
    """The CSRF shape: browser cookies present, no header credential."""
    client = Client()
    client.cookies["reqogniloom_access"] = "some-session-jwt"

    response = _post(client)

    assert response.status_code == 403, (
        "SA-36: a request that could only be authenticated by an ambient "
        "cookie must be refused on a csrf_exempt view"
    )
    payload = json.loads(response.content)
    assert payload["error"]["error_code"] == "UNAUTHORIZED"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cookie_name", ["reqogniloom_access", "reqogniloom_refresh", "sessionid"]
)
def test_every_ambient_cookie_name_is_covered(cookie_name):
    client = Client()
    client.cookies[cookie_name] = "x"
    assert _post(client).status_code == 403


@pytest.mark.django_db
def test_header_credential_beats_a_stale_cookie():
    """A real MCP client is unaffected even if the browser jar has a cookie.

    The response is whatever the auth layer decides about the key (401 for a
    bogus one) — the point is that the SA-36 guard does not short-circuit it.
    """
    client = Client()
    client.cookies["reqogniloom_access"] = "some-session-jwt"

    response = _post(client, HTTP_AUTHORIZATION="Bearer reqlo_not_a_real_key")

    assert response.status_code != 403


@pytest.mark.django_db
def test_no_cookies_at_all_is_untouched():
    """The ordinary MCP path must not be disturbed by the guard."""
    response = _post(Client(), HTTP_X_API_KEY="reqlo_not_a_real_key")
    assert response.status_code != 403


@pytest.mark.django_db
def test_sse_handshake_rejects_cookie_only_request():
    client = Client()
    client.cookies["reqogniloom_access"] = "some-session-jwt"
    assert client.get("/mcp/sse/").status_code == 403


@pytest.mark.django_db
def test_messages_endpoint_accepts_its_session_id_credential():
    """``/mcp/messages/`` authenticates by session id, not by header key.

    The guard must recognise that as an explicit (non-ambient) credential,
    otherwise a legitimate SSE client with a cookie in the jar would break.
    """
    client = Client()
    client.cookies["reqogniloom_access"] = "some-session-jwt"

    with_session = client.post(
        "/mcp/messages/?session_id=not-a-live-session",
        data=_body(),
        content_type="application/json",
    )
    assert with_session.status_code != 403

    without_session = client.post(
        "/mcp/messages/", data=_body(), content_type="application/json"
    )
    assert without_session.status_code == 403
