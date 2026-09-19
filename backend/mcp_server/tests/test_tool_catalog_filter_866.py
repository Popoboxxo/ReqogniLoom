"""Issue #866 — MCP tool-catalogue filtering and compaction.

`tools/list` shipped the full 180+-tool catalogue (~100 KB / ~35k tokens) on
every session start. These tests pin the two opt-in levers that let a client
ask for only what a phase needs:

* ``toolset`` / ``filter`` ({groups, names, search}) — subset selection;
* ``compact`` — trim prose while keeping the callable schema;
* ``tools/filter`` — the same mechanism as its own JSON-RPC method, with
  `count`/`total`/`toolsets` metadata.

The pure helpers are tested directly; the registry page composes them (with
``list_tools`` monkeypatched, so no DB/auth is needed); the protocol handler is
exercised end to end with a fake registry.
"""
from __future__ import annotations

import json

import pytest

from mcp_server.protocol_handler import HttpTransportAdapter, ProtocolHandler
from mcp_server.tool_registry import (
    TOOLSET_NAMES,
    ToolRegistry,
    compact_tool,
    filter_tool_catalogue,
    tool_prefix,
)

_SAMPLE = [
    {
        "name": "requirement.get",
        "description": "Get one requirement. This second sentence is prose the compact mode drops.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "UUID"}},
            "required": ["id"],
        },
    },
    {
        "name": "architecture.create",
        "description": "Create an ArchitectureElement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_id": {"type": "string", "description": "optional parent"},
            },
            "required": ["workspace_id", "title"],
        },
    },
    {
        "name": "audit.query",
        "description": "Query the audit log.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def test_tool_prefix():
    assert tool_prefix("requirement.get") == "requirement"
    assert tool_prefix("admin") == "admin"


def test_filter_by_toolset_narrows_to_its_prefixes():
    out = filter_tool_catalogue(_SAMPLE, toolset="authoring")
    assert {t["name"] for t in out} == {"requirement.get", "architecture.create"}


def test_filter_by_explicit_groups():
    out = filter_tool_catalogue(_SAMPLE, groups=["audit"])
    assert [t["name"] for t in out] == ["audit.query"]


def test_filter_by_names_and_search_compose_with_and():
    by_name = filter_tool_catalogue(_SAMPLE, names=["requirement.get", "audit.query"])
    assert {t["name"] for t in by_name} == {"requirement.get", "audit.query"}

    # search matches name OR description, case-insensitively
    assert [t["name"] for t in filter_tool_catalogue(_SAMPLE, search="AUDIT")] == ["audit.query"]
    assert [t["name"] for t in filter_tool_catalogue(_SAMPLE, search="ArchitectureElement")] == [
        "architecture.create"
    ]


def test_unknown_toolset_is_a_caller_error():
    with pytest.raises(ValueError, match="Unknown toolset"):
        filter_tool_catalogue(_SAMPLE, toolset="not-a-real-phase")


def test_compact_trims_prose_but_keeps_the_callable_schema():
    compacted = compact_tool(_SAMPLE[0])

    # First sentence only.
    assert compacted["description"] == "Get one requirement."
    # Prose keys are gone…
    assert "description" not in compacted["inputSchema"]["properties"]["id"]
    # …but the contract survives: type, required.
    assert compacted["inputSchema"]["properties"]["id"]["type"] == "string"
    assert compacted["inputSchema"]["required"] == ["id"]
    # And it is meaningfully smaller than the full tool.
    full = json.dumps(_SAMPLE[0])
    assert len(json.dumps(compacted)) < len(full)


def test_list_tools_page_reports_total_and_toolsets_without_widening():
    registry = ToolRegistry()
    registry.list_tools = lambda api_key, workspace_id=None: [dict(t) for t in _SAMPLE]  # type: ignore[assignment]

    page = registry.list_tools_page("any-key", toolset="authoring")

    assert page["total"] == 3
    assert page["count"] == 2
    assert {t["name"] for t in page["tools"]} == {"requirement.get", "architecture.create"}
    assert set(page["toolsets"]) == set(TOOLSET_NAMES)


def test_list_tools_page_rejects_a_malformed_filter():
    registry = ToolRegistry()
    registry.list_tools = lambda api_key, workspace_id=None: []  # type: ignore[assignment]
    with pytest.raises(ValueError, match="filter"):
        registry.list_tools_page("any-key", tool_filter={"groups": "requirement"})  # type: ignore[arg-type]


class _FakeRegistry:
    """Minimal stand-in: records the kwargs the handler forwards."""

    def __init__(self) -> None:
        self.seen: dict | None = None

    def list_tools_page(self, **kwargs):
        self.seen = kwargs
        return {
            "tools": [{"name": "requirement.get", "description": "x", "inputSchema": {}}],
            "count": 1,
            "total": 3,
            "toolsets": {"core": ["requirement"]},
        }


def _handle(registry, method: str, params: dict):
    handler = ProtocolHandler(tool_registry=registry)
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": {"api_key": "k", **params}}
    ).encode()
    adapter = HttpTransportAdapter(body, {"X-API-Key": "k"})
    handler.handle(adapter)
    return adapter.get_response()


def test_tools_list_forwards_filter_params_and_returns_a_standard_shape():
    registry = _FakeRegistry()
    response = _handle(
        registry,
        "tools/list",
        {"toolset": "authoring", "compact": True, "filter": {"search": "req"}},
    )
    assert "error" not in response
    # Standard MCP tools/list payload: just {"tools": [...]}.
    assert set(response["result"]) == {"tools"}
    assert registry.seen is not None
    assert registry.seen["toolset"] == "authoring"
    assert registry.seen["compact"] is True
    assert registry.seen["tool_filter"] == {"search": "req"}


def test_tools_filter_returns_metadata():
    registry = _FakeRegistry()
    response = _handle(registry, "tools/filter", {"toolset": "core"})
    assert "error" not in response
    assert response["result"]["count"] == 1
    assert response["result"]["total"] == 3
    assert response["result"]["toolsets"] == {"core": ["requirement"]}


def test_tools_list_maps_a_bad_filter_to_a_named_validation_error():
    class _Raising:
        def list_tools_page(self, **kwargs):
            raise ValueError("Unknown toolset 'nope'. Known toolsets: core.")

    response = _handle(_Raising(), "tools/list", {"toolset": "nope"})
    assert response["error"]["code"] == -32602  # VALIDATION_ERROR / invalid params
    assert "Unknown toolset" in response["error"]["message"]
