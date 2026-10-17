"""
MCP tree-display configuration tool group — configurable navigation tree
(Issue #1257).

leaf_id : COMP-MC-003 (RequirementsToolGroup sibling; own namespace)
req_id  : REQ-003 (Einheitliches Tree-Modul), Issue #1257

Tools implemented:

  tree_display_config.get (read)  — the effective / per-level selection of the
                                    fields the navigation tree renders.
  tree_display_config.set (write) — store (or reset) one level's selection for
                                    one artifact type.

Both tools delegate exclusively to ``TreeDisplayConfigService`` (Layer 2) — they
never touch the ORM themselves, the same ADR-01 discipline every tool group
follows. ``get`` mirrors the REST ``GET /api/v1/{users/me|system|workspaces/<id>}
/tree-display-config/`` endpoints; ``set`` mirrors their ``PATCH``.

Read scoping (``mcp_server/workspace_scope.py``):

  * ``tree_display_config.get`` reads the caller's own selection (identified by
    the credential) or the tenant-wide default — neither is workspace data — so
    it is listed in ``TENANT_SCOPED_READ_TOOLS``. When the caller passes a
    ``workspace_id`` (workspace scope), the dispatcher gate applies as usual;
    the entry is documentation for the coverage ratchet, not a runtime bypass.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.tree_display_config_service import (
    SCOPE_USER,
    SCOPE_WORKSPACE,
    WRITABLE_SCOPES,
    TreeDisplayConfigService,
)
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, ParameterError, optional_uuid
from persistence.errors import PermissionDeniedError, ValidationError

#: ``effective`` is a *read* resolution outcome (it walks user → workspace →
#: global → default). ``default`` names the built-in fallback for a UI legend.
_READ_SCOPES: tuple[str, ...] = ("effective",) + WRITABLE_SCOPES + ("default",)


def _parse_fields(raw: Any) -> list[Any] | None:
    """Return the ``fields`` parameter as a list, or ``None`` for a reset.

    ``None``/absent and the explicit JSON ``null`` are both "reset this level for
    this item type"; anything that is not a list is a caller error.
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        return list(raw)
    raise ParameterError(
        "Parameter 'fields' must be an array of field keys/objects, or null "
        "to reset."
    )


class TreeDisplayConfigToolGroup(BaseToolGroup):
    """COMP-MC-003 — tree-display configuration MCP tool group (1 read, 1 write)."""

    _TOOL_MAP = {
        "tree_display_config.get": "_handle_get",
        "tree_display_config.set": "_handle_set",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "tree_display_config.get",
            "description": (
                "Read the navigation tree's field selection (Issue #1257). "
                "``scope=\"effective\"`` (default) resolves user > workspace > "
                "global > built-in default and reports which level supplied the "
                "value; any other scope returns that level's stored value. "
                "``item_type`` is required for the effective scope and optional "
                "otherwise (omitted = the whole {item_type: [...]} map). The "
                "response carries the selectable-field catalogue so a caller can "
                "render a picker. Identical to the REST "
                "GET .../tree-display-config/ endpoints."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": list(_READ_SCOPES),
                        "description": (
                            "effective | user | workspace | global | default. "
                            "Default: effective."
                        ),
                    },
                    "item_type": {
                        "type": "string",
                        "description": (
                            "Artifact type, e.g. \"Requirement\" or \"Adr\". "
                            "Required when scope is \"effective\"."
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace whose override participates "
                            "(workspace scope and the workspace level of the "
                            "effective resolution)."
                        ),
                    },
                },
            },
        },
        {
            "name": "tree_display_config.set",
            "description": (
                "Store (or reset) the navigation tree's field selection for one "
                "artifact type on one level (Issue #1257). ``fields`` is an "
                "ordered array of field keys (see the catalogue from "
                "``tree_display_config.get``) or {\"key\", \"width\"} objects; "
                "``null`` resets the level so resolution falls back to the next "
                "one. Scope \"user\" is self-service; \"workspace\" requires write "
                "authority in the workspace (workspace_id required); \"global\" "
                "requires the admin role. Identical to the REST PATCH endpoints."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": list(WRITABLE_SCOPES),
                        "description": "user | workspace | global.",
                    },
                    "item_type": {
                        "type": "string",
                        "description": "Artifact type to configure.",
                    },
                    "fields": {
                        "type": ["array", "null"],
                        "items": {},
                        "description": (
                            "Ordered field keys or {\"key\",\"width\"} objects; "
                            "null resets the level for this item type."
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace; required for scope "
                            "\"workspace\"."
                        ),
                    },
                },
                "required": ["scope", "item_type", "fields"],
            },
        },
    ]

    def _service(self) -> TreeDisplayConfigService:
        return TreeDisplayConfigService()

    def _handle_get(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """tree_display_config.get — the effective / per-level selection."""
        scope = str(params.get("scope") or "effective").strip().lower()
        if scope not in _READ_SCOPES:
            raise ParameterError(
                f"Parameter 'scope' must be one of {list(_READ_SCOPES)}."
            )
        item_type = params.get("item_type")
        item_type = str(item_type).strip() if item_type else None
        workspace_id = optional_uuid(params, "workspace_id")

        service = self._service()
        try:
            if scope == "effective":
                if not item_type:
                    raise ParameterError(
                        "Parameter 'item_type' is required for scope 'effective'."
                    )
                return ToolResult.ok(
                    service.get_config(
                        auth_context,
                        item_type=item_type,
                        workspace_id=workspace_id,
                    )
                )
            return ToolResult.ok(
                service.get_scope(
                    auth_context,
                    scope=scope,
                    item_type=item_type,
                    workspace_id=workspace_id,
                )
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

    def _handle_set(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """tree_display_config.set — store/reset one level's selection."""
        scope = str(params.get("scope") or "").strip().lower()
        if scope not in WRITABLE_SCOPES:
            raise ParameterError(
                f"Parameter 'scope' must be one of {list(WRITABLE_SCOPES)}."
            )
        item_type = params.get("item_type")
        if not item_type or not str(item_type).strip():
            raise ParameterError("Parameter 'item_type' is required.")
        item_type = str(item_type).strip()

        fields = _parse_fields(params.get("fields"))
        workspace_id: UUID | None = optional_uuid(params, "workspace_id")
        if scope == SCOPE_WORKSPACE and workspace_id is None:
            raise ParameterError(
                "Parameter 'workspace_id' is required for scope 'workspace'."
            )
        if scope == SCOPE_USER and workspace_id is not None:
            raise ParameterError(
                "Scope 'user' must not carry a workspace_id."
            )

        service = self._service()
        try:
            return ToolResult.ok(
                service.set_config(
                    auth_context,
                    scope=scope,
                    item_type=item_type,
                    fields=fields,
                    workspace_id=workspace_id,
                )
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))


__all__ = ["TreeDisplayConfigToolGroup"]
