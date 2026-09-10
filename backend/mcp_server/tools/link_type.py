"""LinkTypeToolGroup — MCP access to the tenant link-type catalog.

Mirrors the ``workflow.*`` / ``attribute_definition.*`` groups: five tools over
``application.link_type_facade.LinkTypeFacade``, no ORM here (ADR-01).

Every payload is primitive-only. The transport serialises with stdlib
``json.dumps``, which raises on a ``UUID`` or ``datetime`` and reaches the
client as an opaque INTERNAL_ERROR — the facade already returns ``str`` ids, so
nothing here re-introduces them. No payload uses a top-level ``content`` key,
which collides with the JSON-RPC result envelope.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, optional_uuid

from application.link_type_facade import LinkTypeFacade
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError

logger = logging.getLogger(__name__)

_WORKSPACE_PROP = {
    "workspace_id": {
        "type": "string",
        "description": "UUID of the workspace whose catalog is addressed.",
    }
}
_KEY_PROP = {
    "key": {
        "type": "string",
        "description": "Link-type key, e.g. 'verifies' or a tenant-defined one.",
    }
}
_DEFINITION_PROP = {
    "definition": {
        "type": "object",
        "description": (
            "definition_json: label (de/en x downstream/upstream/neutral), "
            "allowed_pairs, coverage_relevant, suspect_rule "
            "(none | target_change_flags_source | source_change_flags_target | "
            "parent_change_flags_children), impact_weight, manual_creatable, "
            "system_owned, active, built_in."
        ),
    }
}


class LinkTypeToolGroup(BaseToolGroup):
    """Five tools over the link-type catalog (2 read, 3 write)."""

    _TOOL_MAP = {
        "link_type.list": "_handle_list",
        "link_type.get": "_handle_get",
        "link_type.create": "_handle_create",
        "link_type.update": "_handle_update",
        "link_type.reset": "_handle_reset",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "link_type.list",
            "description": (
                "List the trace-link types available in a workspace, with their "
                "allowed endpoint pairs (read-only). Call this before "
                "traceability.create_link to learn which link_type values and "
                "artifact-type combinations the workspace accepts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": dict(_WORKSPACE_PROP),
                "required": ["workspace_id"],
            },
        },
        {
            "name": "link_type.get",
            "description": "Fetch one link-type definition of a workspace (read-only).",
            "inputSchema": {
                "type": "object",
                "properties": {**_WORKSPACE_PROP, **_KEY_PROP},
                "required": ["workspace_id", "key"],
            },
        },
        {
            "name": "link_type.create",
            "description": (
                "Create a tenant-wide link type (write, audited, admin only). "
                "suspect_rule must be one of the four supported behaviours."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_KEY_PROP, **_DEFINITION_PROP},
                "required": ["key", "definition"],
            },
        },
        {
            "name": "link_type.update",
            "description": (
                "Update a link type (write, audited, admin only). With "
                "workspace_id the change is a workspace override; without it "
                "the tenant-wide default is edited and propagated to every "
                "workspace still on the default."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_WORKSPACE_PROP, **_KEY_PROP, **_DEFINITION_PROP},
                "required": ["key", "definition"],
            },
        },
        {
            "name": "link_type.reset",
            "description": (
                "Reset a workspace override back to the tenant default "
                "(write, audited, admin only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_WORKSPACE_PROP, **_KEY_PROP},
                "required": ["workspace_id", "key"],
            },
        },
    ]

    @staticmethod
    def _facade() -> LinkTypeFacade:
        return LinkTypeFacade()

    @staticmethod
    def _guard(func, *args, **kwargs) -> ToolResult:
        """Run a facade call, mapping domain exceptions onto ToolResult codes."""
        try:
            return ToolResult.ok(func(*args, **kwargs))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except Exception as exc:  # noqa: BLE001 — transport boundary
            logger.exception("link_type tool failed")
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for link_type.list.",
            )
        return self._guard(
            lambda: {
                "link_types": self._facade().list_workspace(auth_context, workspace_id)
            }
        )

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = optional_uuid(params, "workspace_id")
        key = (params or {}).get("key")
        if not workspace_id or not key:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameters 'workspace_id' and 'key' are required for link_type.get.",
            )

        def _get():
            rows = self._facade().list_workspace(auth_context, workspace_id)
            match = next((row for row in rows if row["key"] == key), None)
            if match is None:
                available = ", ".join(sorted(row["key"] for row in rows))
                raise NotFoundError(
                    f"Link type '{key}' not found in this workspace. "
                    f"Available: {available or '(none)'}."
                )
            return {"link_type": match}

        return self._guard(_get)

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        key = (params or {}).get("key")
        definition = (params or {}).get("definition")
        if not key:
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'key' is required for link_type.create."
            )
        return self._guard(
            lambda: {
                "link_type": self._facade().create_global(auth_context, key, definition)
            }
        )

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        key = (params or {}).get("key")
        definition = (params or {}).get("definition")
        workspace_id = optional_uuid(params, "workspace_id")
        if not key:
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'key' is required for link_type.update."
            )
        if workspace_id:
            return self._guard(
                lambda: {
                    "link_type": self._facade().update_workspace(
                        auth_context, workspace_id, key, definition
                    )
                }
            )
        return self._guard(
            lambda: {
                "link_type": self._facade().update_global(auth_context, key, definition)
            }
        )

    def _handle_reset(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = optional_uuid(params, "workspace_id")
        key = (params or {}).get("key")
        if not workspace_id or not key:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameters 'workspace_id' and 'key' are required for link_type.reset.",
            )
        return self._guard(
            lambda: {
                "link_type": self._facade().reset_workspace(
                    auth_context, workspace_id, key
                )
            }
        )


__all__ = ["LinkTypeToolGroup"]
