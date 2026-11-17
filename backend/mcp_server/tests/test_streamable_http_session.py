"""Mcp-Session-Id and SSE-on-POST for the Streamable-HTTP transport.

leaf_id : COMP-MC-001 (McpHttpTransportView, sse_pubsub session store)

Task 2: ``initialize`` mints an ``Mcp-Session-Id`` (only when it carried a
credential), follow-up requests may present that session id instead of the
credential header, and ``DELETE /mcp/`` terminates a known session.

Task 3: a POST that asks for ``text/event-stream`` is answered with a single
SSE ``message`` event; JSON remains the default.
"""
import json
from unittest.mock import patch

import pytest
from django.test import Client


def _initialize_body():
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )


@pytest.mark.django_db
def test_initialize_mints_session_id_header():
    stored = {}
    with patch(
        "mcp_server.views.store_session_api_key",
        side_effect=lambda sid, key, **kw: stored.update({sid: key}),
    ):
        response = Client().post(
            "/mcp/",
            data=_initialize_body(),
            content_type="application/json",
            HTTP_X_API_KEY="reqlo_dummy",
        )
    assert response.status_code == 200
    session_id = response.headers["Mcp-Session-Id"]
    assert stored[session_id] == "reqlo_dummy"


@pytest.mark.django_db
def test_initialize_without_credential_mints_no_session():
    response = Client().post(
        "/mcp/", data=_initialize_body(), content_type="application/json"
    )
    assert response.status_code == 200
    assert "Mcp-Session-Id" not in response.headers


@pytest.mark.django_db
def test_non_initialize_echoes_incoming_session_id():
    body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    with patch("mcp_server.views.get_session_api_key", return_value="reqlo_dummy"):
        response = Client().post(
            "/mcp/",
            data=body,
            content_type="application/json",
            HTTP_MCP_SESSION_ID="sess-1",
        )
    assert response.headers["Mcp-Session-Id"] == "sess-1"


@pytest.mark.django_db
def test_session_id_supplies_the_api_key_when_header_absent():
    body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    with patch(
        "mcp_server.views.get_session_api_key", return_value="reqlo_from_session"
    ) as lookup:
        Client().post(
            "/mcp/",
            data=body,
            content_type="application/json",
            HTTP_MCP_SESSION_ID="sess-1",
        )
    lookup.assert_called_once_with("sess-1")


@pytest.mark.django_db
def test_delete_terminates_a_known_session():
    # API-002: a session id alone is no longer proof — the bound key must be
    # presented as well, otherwise the session cannot be revoked.
    with patch(
        "mcp_server.views.get_session_api_key", return_value="reqlo_dummy"
    ), patch("mcp_server.views.delete_session_api_key") as delete:
        response = Client().delete(
            "/mcp/", HTTP_MCP_SESSION_ID="sess-1", HTTP_X_API_KEY="reqlo_dummy"
        )
    assert response.status_code == 204
    delete.assert_called_once_with("sess-1")


@pytest.mark.django_db
def test_delete_unknown_session_is_404():
    with patch("mcp_server.views.get_session_api_key", return_value=None):
        response = Client().delete("/mcp/", HTTP_MCP_SESSION_ID="nope")
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_without_session_header_is_400():
    assert Client().delete("/mcp/").status_code == 400


# ---------------------------------------------------------------------------
# Task 3 — SSE response body when the client asks for it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_post_returns_sse_when_client_prefers_event_stream():
    response = Client().post(
        "/mcp/",
        data=_initialize_body(),
        content_type="application/json",
        HTTP_ACCEPT="text/event-stream",
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    text = response.content.decode()
    assert text.startswith("event: message\ndata: ")
    assert text.endswith("\n\n")
    payload = json.loads(text.split("data: ", 1)[1].strip())
    assert payload["result"]["protocolVersion"] == "2025-06-18"


@pytest.mark.django_db
def test_post_still_returns_json_by_default():
    response = Client().post(
        "/mcp/", data=_initialize_body(), content_type="application/json"
    )
    assert response["Content-Type"] == "application/json"


@pytest.mark.django_db
def test_sse_response_still_carries_the_session_header():
    with patch("mcp_server.views.store_session_api_key"):
        response = Client().post(
            "/mcp/",
            data=_initialize_body(),
            content_type="application/json",
            HTTP_ACCEPT="text/event-stream",
            HTTP_X_API_KEY="reqlo_dummy",
        )
    assert "Mcp-Session-Id" in response.headers
