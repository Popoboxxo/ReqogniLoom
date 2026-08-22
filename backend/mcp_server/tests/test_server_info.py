"""Server-info / capability declaration tests (REQ-131, issue #455).

``GET /mcp/`` returns a health/info payload advertising the supported
transports. The rule is symmetric: the list must name every transport that is
actually routed and functional, and nothing else. Advertising a broken
transport misleads clients into attempting an unsupported connection —
*omitting* a working one is just as harmful, because every plugin config
shipped under ``dist/plugins/`` connects with ``"type": "sse"`` and would look
unsupported against its own server.

SSE was removed from the list under REQ-131 while ``GET /mcp/sse/`` answered
500 on every request (a hop-by-hop ``Connection: keep-alive`` response header
tripped wsgiref's PEP-3333 assertion). That header is gone, so SSE is declared
again.

``stdio`` is deliberately not declared here (deep-dive review D-7a): it is a
separate, non-HTTP-routed transport — ``mcp_server/urls.py`` has no path for
it — so advertising it on this HTTP discovery endpoint would itself violate
the "actually routed" rule above.
"""
from __future__ import annotations

import json

import pytest
from django.test import Client


@pytest.mark.django_db
def test_server_info_declares_every_routed_transport() -> None:
    """The declared transports must match the transports actually served."""
    response = Client().get("/mcp/")
    assert response.status_code == 200

    payload = json.loads(response.content)
    transports = payload["transports"]
    assert transports == ["http", "sse"]


@pytest.mark.django_db
def test_server_info_declares_sse() -> None:
    """SSE is the transport the distributed plugin configs use — declare it."""
    payload = json.loads(Client().get("/mcp/").content)
    assert "sse" in payload["transports"], (
        "dist/plugins/*/... connect with \"type\": \"sse\"; the server must "
        "advertise that transport (issue #455)."
    )
