"""Server-info / capability declaration tests (REQ-131).

GET /mcp/ returns a health/info payload advertising the supported transports.
SSE is not an implemented transport, so it must not appear in that list —
declaring it misleads MCP clients into attempting an unsupported connection.
"""
from __future__ import annotations

import json

import pytest
from django.test import Client


@pytest.mark.django_db
def test_server_info_does_not_advertise_sse() -> None:
    """The declared transports must exclude the unimplemented SSE transport."""
    response = Client().get("/mcp/")
    assert response.status_code == 200

    payload = json.loads(response.content)
    transports = payload["transports"]
    assert "sse" not in transports
    assert transports == ["http", "stdio"]
