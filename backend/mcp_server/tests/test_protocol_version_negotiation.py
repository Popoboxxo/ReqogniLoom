"""Protocol revision 2025-06-18 negotiation (MCP-Modernisierung Task 1 / Task 4).

leaf_id : COMP-MC-001 (ProtocolHandler, McpHttpTransportView)

Covers two contracts:
  * ``initialize`` negotiates a revision (echo a supported requested one,
    otherwise answer with the newest) and advertises ``tools``, ``resources``
    and ``prompts``.
  * ``MCP-Protocol-Version`` on a Streamable-HTTP request is validated: an
    unsupported revision is a 400 ``INVALID_REQUEST``, absent/known values
    pass through untouched.
"""
import json

import pytest
from django.test import Client

from mcp_server.protocol_handler import (
    MCP_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    HttpTransportAdapter,
    ProtocolHandler,
    negotiate_protocol_version,
)


def test_constant_is_2025_06_18():
    assert MCP_PROTOCOL_VERSION == "2025-06-18"


def test_supported_versions_include_legacy():
    assert SUPPORTED_PROTOCOL_VERSIONS[0] == "2025-06-18"
    assert "2024-11-05" in SUPPORTED_PROTOCOL_VERSIONS


@pytest.mark.parametrize(
    "requested,expected",
    [
        ("2025-06-18", "2025-06-18"),
        ("2024-11-05", "2024-11-05"),
        ("1999-01-01", "2025-06-18"),
        (None, "2025-06-18"),
        (12345, "2025-06-18"),
    ],
)
def test_negotiate_echoes_supported_else_newest(requested, expected):
    assert negotiate_protocol_version(requested) == expected


def _initialize(params):
    handler = ProtocolHandler(tool_registry=object())
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
    ).encode()
    return handler.handle(HttpTransportAdapter(body=body, headers={}), headers={})


def test_initialize_advertises_resources_and_prompts():
    capabilities = _initialize({})["result"]["capabilities"]
    assert capabilities["tools"] == {}
    assert capabilities["resources"] == {}
    assert capabilities["prompts"] == {}


def test_initialize_echoes_legacy_client_version():
    result = _initialize({"protocolVersion": "2024-11-05"})["result"]
    assert result["protocolVersion"] == "2024-11-05"


def test_initialize_defaults_to_newest_without_params():
    assert _initialize({})["result"]["protocolVersion"] == "2025-06-18"


# ---------------------------------------------------------------------------
# MCP-Protocol-Version request header (Task 4)
# ---------------------------------------------------------------------------


def _tools_list_body():
    return json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})


@pytest.mark.django_db
def test_unsupported_protocol_header_is_rejected():
    response = Client().post(
        "/mcp/",
        data=_tools_list_body(),
        content_type="application/json",
        HTTP_MCP_PROTOCOL_VERSION="1999-01-01",
    )
    assert response.status_code == 400
    body = json.loads(response.content)
    assert body["error"]["error_code"] == "INVALID_REQUEST"
    assert "1999-01-01" in body["error"]["message"]


@pytest.mark.django_db
def test_supported_protocol_header_passes_through():
    response = Client().post(
        "/mcp/",
        data=_tools_list_body(),
        content_type="application/json",
        HTTP_MCP_PROTOCOL_VERSION="2024-11-05",
    )
    assert response.status_code != 400


@pytest.mark.django_db
def test_absent_protocol_header_passes_through():
    response = Client().post(
        "/mcp/", data=_tools_list_body(), content_type="application/json"
    )
    assert response.status_code != 400
