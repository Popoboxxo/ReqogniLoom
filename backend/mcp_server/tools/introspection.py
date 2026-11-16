"""Tool-catalogue introspection (MCP-Modernisierung, spec section 6.2).

``tool.list_groups`` reports which tool groups exist and how many tools each
holds. It is always visible and never filtered by ``ApiKey.tool_groups`` (see
``mcp_server.tool_registry._ALWAYS_VISIBLE_TOOLS``): a client whose manifest was
narrowed still needs a way to learn what else it could ask for, and group names
plus counts are pure metadata — no tenant data, no security value.

Counts come from the registry's own schema build, so this cannot drift from
``tools/list``. Groups with no schemas (the ``resource``/``prompt`` capability
pseudo-tools) are omitted by construction: they are not part of the tool
surface at all.

Requirements: REQ-L2-MC-006, REQ-L2-MC-009.
"""
from __future__ import annotations

import logging
from typing import Any

from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup

logger = logging.getLogger(__name__)


class IntrospectionToolGroup(BaseToolGroup):
    """Catalogue metadata about the MCP tool surface (1 tool, read-only)."""

    _TOOL_MAP = {"tool.list_groups": "_handle_list_groups"}

    _TOOL_SCHEMAS = [
        {
            "name": "tool.list_groups",
            "description": (
                "List every MCP tool group with its tool count. Always visible, "
                "never narrowed by an API key's tool_groups curation — call it "
                "to discover which group names exist before configuring a key's "
                "tool_groups list. Note that tool_groups only changes what "
                "tools/list advertises; every tool your role and key scope "
                "permit stays callable by name."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        }
    ]

    def _handle_list_groups(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """tool.list_groups — every group name with its tool count."""
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._ensure_groups()

        counts: dict[str, int] = {}
        seen_group_ids: set[int] = set()
        for group in registry._groups.values():
            if id(group) in seen_group_ids:
                continue
            seen_group_ids.add(id(group))
            if not hasattr(group, "get_tool_schemas"):
                continue
            for schema in group.get_tool_schemas():
                name = schema.get("name", "")
                if "." not in name:
                    continue
                prefix = name.split(".", 1)[0]
                counts[prefix] = counts.get(prefix, 0) + 1

        groups = [
            {"name": prefix, "tool_count": count}
            for prefix, count in sorted(counts.items())
        ]
        return ToolResult.ok({"groups": groups, "count": len(groups)})


__all__ = ["IntrospectionToolGroup"]
