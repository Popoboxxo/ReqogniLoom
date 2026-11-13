"""Phase G / #1374 S3: the three projection tools on the MCP surface."""

from __future__ import annotations

import pytest

from mcp_server.tools.document import DocumentToolGroup

pytestmark = pytest.mark.django_db

NEW_TOOLS = {
    "document.project",
    "document.projection_status",
    "document.adopt",
}


def test_the_three_tools_are_dispatchable() -> None:
    group = DocumentToolGroup()

    assert NEW_TOOLS <= set(group._TOOL_MAP)


def test_the_three_tools_are_advertised_with_a_schema() -> None:
    schemas = {schema["name"]: schema for schema in DocumentToolGroup().get_tool_schemas()}

    assert NEW_TOOLS <= set(schemas)
    for name in NEW_TOOLS:
        assert schemas[name]["inputSchema"]["type"] == "object"

    assert set(schemas["document.adopt"]["inputSchema"]["required"]) == {
        "id",
        "file_sha256",
    }
    assert set(schemas["document.project"]["inputSchema"]["required"]) == {"id"}


def test_projection_status_carries_an_optional_confirm_object() -> None:
    schema = next(
        item
        for item in DocumentToolGroup().get_tool_schemas()
        if item["name"] == "document.projection_status"
    )

    confirm = schema["inputSchema"]["properties"]["confirm"]
    assert confirm["required"] == ["document_id", "sha256"]


def test_the_projection_tools_are_classified_for_rbac() -> None:
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES, _WRITE_TOOL_PREFIXES

    assert "document.project" in _READ_ONLY_TOOL_NAMES
    assert "document.projection_status" in _READ_ONLY_TOOL_NAMES
    assert "document.adopt" in _WRITE_TOOL_PREFIXES
