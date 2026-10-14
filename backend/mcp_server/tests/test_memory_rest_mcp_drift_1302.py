"""#1302 drift guard: the REST memory surface and the MCP memory tools are held
against each other.

Both transports delegate to the same services, but their *surfaces* are declared
in two places (``rest_api.urls`` and the MCP tool registry). This test fails the
moment a REST memory route gains no MCP counterpart — or a new MCP ``memory.*``
tool is neither mapped to a route nor explicitly declared route-less — so the
two cannot drift apart silently, which is exactly what #1302 was opened for.

Design mirror: every intentional asymmetry is an explicit, reviewed entry (with
a reason), never an implicit gap; and every mapping entry must reference a real
route/tool so a rename is caught instead of leaving dead weight.
"""
from __future__ import annotations

from typing import Dict, Set

#: MCP memory tool -> the REST memory route name(s) providing the same
#: capability. A tool maps to more than one route where REST splits a capability
#: by URL (workspace vs artifact scope).
_MCP_TO_REST_ROUTES: Dict[str, Set[str]] = {
    "memory.get": {"memory-entry-detail"},
    "memory.forget": {"memory-entry-detail"},
    "memory.write": {"workspace-memory-entries", "artifact-memory"},
    "memory.list": {"workspace-memory-entries", "artifact-memory"},
    "memory.query": {"workspace-memory-search"},
    "memory.digest": {"workspace-memory-digest", "artifact-memory-digest"},
    "memory.ask": {"workspace-memory-ask"},
    "memory.promote": {"memory-entry-promote"},
    "memory.overview": {"system-memory-workspace-overview"},
    "memory.projection": {"system-memory-projection"},
    "memory.settings": {"system-memory-settings"},
    "memory.export": {"system-memory-entries-export", "system-memory-entries"},
    "memory.delete_workspace": {"system-memory-workspace-delete"},
}

#: MCP memory tools with no REST route by design (reason mandatory).
_MCP_TOOLS_WITHOUT_REST_ROUTE: Dict[str, str] = {
    "memory.remember_interaction": (
        "explicit consolidation trigger (#1300); the automatic path is the "
        "interview outbox -> MemoryProjector, which has no REST endpoint"
    ),
}

#: REST memory routes with no MCP tool by design (reason mandatory). These are
#: required to exist — a rename/removal here is a real drift.
_REST_ROUTES_WITHOUT_MCP_TOOL: Dict[str, str] = {
    "system-memory-settings-reset": (
        "Django-superuser-only reset of the deployment-global override; "
        "deliberately not exposed on the MCP surface"
    ),
    "workspace-memory-settings": (
        "per-workspace enable/disable toggle — a workspace-configuration/UI "
        "concern, not part of the agent-facing memory surface"
    ),
    "memory-self-service": (
        "self-service summary over the caller's OWN user memory; the MCP "
        "surface already reaches that data through memory.list/memory.get"
    ),
}

#: REST memory routes owned by a PARALLEL stream (#1300 REST half / #1302) that
#: may or may not be present in this worktree. Exempt when present, but not
#: required to exist — the reverse direction (a route without a pendant) is
#: still reported by :func:`test_every_rest_memory_route_has_a_pendant_or_a_reason`.
_DEFERRED_REST_ROUTES_WITHOUT_MCP_TOOL: Dict[str, str] = {
    "system-memory-consolidations": (
        "per-trigger-source consolidation counter (the REST half of #1300, "
        "landed by the event/projector stream); a metrics read, not an "
        "agent-facing memory tool"
    ),
}


def _rest_memory_routes() -> Dict[str, str]:
    """Return ``{route name: path}`` for every memory route in ``rest_api.urls``."""
    from rest_api.urls import urlpatterns

    routes: Dict[str, str] = {}
    for pattern in urlpatterns:
        name = getattr(pattern, "name", None)
        path = str(getattr(pattern, "pattern", ""))
        if not name or "memory" not in path:
            continue
        routes[name] = path
    return routes


def _mcp_memory_tools() -> Set[str]:
    """Every live MCP tool in the ``memory`` namespace."""
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    return {
        tool["name"]
        for tool in build_manifest()["tools"]
        if tool["name"].startswith("memory.")
    }


def test_every_mcp_memory_tool_is_mapped_or_declared_route_less() -> None:
    """A new ``memory.*`` tool must be classified, not silently unmapped."""
    tools = _mcp_memory_tools()
    classified = set(_MCP_TO_REST_ROUTES) | set(_MCP_TOOLS_WITHOUT_REST_ROUTE)

    unmapped = sorted(tools - classified)
    assert not unmapped, (
        f"MCP memory tools with no REST mapping: {unmapped}. Add them to "
        "_MCP_TO_REST_ROUTES (or _MCP_TOOLS_WITHOUT_REST_ROUTE with a reason)."
    )
    stale = sorted(classified - tools)
    assert not stale, f"mapping names non-existent MCP tools: {stale}"


def test_every_mapped_route_name_exists() -> None:
    """A typo'd/renamed route name is dead weight — report it."""
    routes = _rest_memory_routes()
    referenced = {name for names in _MCP_TO_REST_ROUTES.values() for name in names}
    missing = sorted(referenced - set(routes))
    assert not missing, f"_MCP_TO_REST_ROUTES names unknown routes: {missing}"


def test_every_exempt_route_exists() -> None:
    """The no-MCP-pendant allowlist must reference real routes, or it is stale."""
    routes = _rest_memory_routes()
    missing = sorted(set(_REST_ROUTES_WITHOUT_MCP_TOOL) - set(routes))
    assert not missing, f"_REST_ROUTES_WITHOUT_MCP_TOOL names unknown routes: {missing}"


def test_every_rest_memory_route_has_a_pendant_or_a_reason() -> None:
    """The core guard: report every REST memory route without an MCP counterpart."""
    routes = _rest_memory_routes()
    covered = {name for names in _MCP_TO_REST_ROUTES.values() for name in names}
    exempt = set(_REST_ROUTES_WITHOUT_MCP_TOOL) | set(
        _DEFERRED_REST_ROUTES_WITHOUT_MCP_TOOL
    )
    unclassified = sorted(set(routes) - covered - exempt)
    assert not unclassified, (
        "REST memory routes without an MCP counterpart: "
        f"{[(n, routes[n]) for n in unclassified]}. Add a tool mapping or list "
        "the route in _REST_ROUTES_WITHOUT_MCP_TOOL with a reason."
    )
