"""Issue #1615 — every workspace-scoped ``*.query`` tool must *require* its workspace.

The schema drift this guards against: ``requirement.query`` advertised
``workspace_id`` as an optional property while its handler already refused a
call without it, so a client that trusted ``tools/list`` could not tell the
call is workspace-bound. Five sibling ``*.query`` tools declared it as
required; the sixth did not.

The assertion runs over the *advertised* catalogue (``ToolRegistry``), not over
a hand-maintained list of files: a new ``*.query`` tool cannot silently opt out
of the contract, and the sibling tools are compared as one group so a fix in
one of them cannot leave the others behind.

Deliberately **not** covered here (each is scoped by something other than one
workspace, so an optional ``workspace_id`` is the honest schema):

* ``audit.query`` — tenant-wide audit log, ``workspace_id`` is a filter;
* ``traceability.query`` / ``context.query`` — artifact-scoped, keyed by
  ``artifact_id``;
* ``memory.query`` — multi-scope (``scope``/``scopes``), ``workspace_id`` is one
  optional selector.

The committed manifest is kept in lockstep by
``test_tool_manifest_drift.py`` (whole-contract comparison), so a schema change
that is not re-baselined fails there as well.
"""
from __future__ import annotations

from typing import Any

from mcp_server.tool_registry import ToolRegistry

#: Query tools whose subject is not exactly one workspace (see module docstring).
_NOT_WORKSPACE_SCOPED = frozenset(
    {
        "audit.query",
        "context.query",
        "memory.query",
        "traceability.query",
    }
)

#: The workspace-scoped sibling group the issue named. Kept explicit so the
#: expectation is readable at a glance; the general assertion below covers any
#: future query tool added outside this list.
_WORKSPACE_SCOPED_QUERY_TOOLS = frozenset(
    {
        "architecture.query",
        "diagram.query",
        "needs.query",
        "requirement.query",
        "risk.query",
        "test.query",
    }
)


def _query_tools() -> dict[str, dict[str, Any]]:
    """Return every advertised ``*.query`` tool, keyed by name."""
    registry = ToolRegistry()
    registry._ensure_groups()
    return {
        schema["name"]: schema
        for schema in registry.all_tool_schemas()
        if str(schema.get("name", "")).endswith(".query")
    }


def _required(schema: dict[str, Any]) -> list[str]:
    return list(schema.get("inputSchema", {}).get("required") or [])


def _properties(schema: dict[str, Any]) -> dict[str, Any]:
    return dict(schema.get("inputSchema", {}).get("properties") or {})


def test_workspace_scoped_query_tools_require_workspace_id():
    """Every query tool that filters by workspace must require it."""
    query_tools = _query_tools()
    assert query_tools, "the registry advertised no *.query tool at all"

    offenders = sorted(
        name
        for name, schema in query_tools.items()
        if name not in _NOT_WORKSPACE_SCOPED
        and "workspace_id" in _properties(schema)
        and "workspace_id" not in _required(schema)
    )
    assert offenders == [], (
        "workspace-scoped *.query tools must declare workspace_id in "
        f"'required': {offenders}"
    )


def test_the_named_sibling_group_is_consistent():
    """The six siblings called out by issue #1615 share one required contract."""
    query_tools = _query_tools()
    missing = sorted(_WORKSPACE_SCOPED_QUERY_TOOLS - set(query_tools))
    assert missing == [], f"expected query tools are not advertised: {missing}"

    for name in sorted(_WORKSPACE_SCOPED_QUERY_TOOLS):
        schema = query_tools[name]
        assert "workspace_id" in _properties(schema), (
            f"{name} does not even declare a workspace_id property"
        )
        assert _required(schema)[0] == "workspace_id", (
            f"{name} must require workspace_id first, got {_required(schema)}"
        )


def test_requirement_query_required_list_is_exactly_the_workspace():
    """No over-correction: the fix must not require anything else."""
    assert _required(_query_tools()["requirement.query"]) == ["workspace_id"]


def test_non_workspace_query_tools_keep_their_contract():
    """The documented exemptions stay as they are (no accidental tightening)."""
    query_tools = _query_tools()
    for name in sorted(_NOT_WORKSPACE_SCOPED):
        schema = query_tools[name]
        # They may *offer* workspace_id as a selector, but must not require it.
        assert "workspace_id" not in _required(schema), (
            f"{name} is not workspace-scoped and must not require workspace_id"
        )
