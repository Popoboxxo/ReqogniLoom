"""
MCP create-dialog form-definition tool group — configurable "new artifact"
dialog (Issue #1263).

leaf_id : COMP-MC-003 (TreeDisplayConfigToolGroup sibling; own namespace)
req_id  : REQ-003, Issue #1263

Tools implemented:

  create_form_definition.get (read)    — the effective / per-level form
                                         definition of the create dialog (which
                                         fields are visible, their order,
                                         requiredness and default).
  create_form_definition.set (write)   — store (or reset) one level's definition
                                         for one artifact type.
  create_form_definition.export (read) — serialize one level's definition as a
                                         portable, versioned document.
  create_form_definition.import (write)— import such a document into one level
                                         (same validation as ``set``).

Both tools delegate exclusively to ``CreateFormConfigService`` (Layer 2) — they
never touch the ORM themselves, the same ADR-01 discipline every tool group
follows. ``get`` mirrors the REST ``GET /api/v1/{users/me|system|workspaces/<id>}
/create-form-config/`` endpoints; ``set`` mirrors their ``PATCH``.

Read scoping (``mcp_server/workspace_scope.py``):

  * ``create_form_definition.get`` reads the caller's own definition (identified
    by the credential) or the tenant-wide default — neither is workspace data —
    so it is listed in ``TENANT_SCOPED_READ_TOOLS``. When the caller passes a
    ``workspace_id`` (workspace scope), the dispatcher gate applies as usual;
    the entry is documentation for the coverage ratchet, not a runtime bypass.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, ParameterError, optional_uuid

from application.create_form_config_service import (
    SCOPE_USER,
    SCOPE_WORKSPACE,
    WRITABLE_SCOPES,
    CreateFormConfigService,
)
from persistence.errors import PermissionDeniedError, ValidationError

#: ``effective`` is a *read* resolution outcome (it walks user → workspace →
#: global → definition default). ``default`` names the built-in fallback.
_READ_SCOPES: tuple[str, ...] = ("effective",) + WRITABLE_SCOPES + ("default",)


def _parse_fields(raw: Any) -> Optional[List[Any]]:
    """Return the ``fields`` parameter as a list, or ``None`` for a reset.

    ``None``/absent and the explicit JSON ``null`` are both "reset this level for
    this item type"; anything that is not a list is a caller error.
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        return list(raw)
    raise ParameterError(
        "Parameter 'fields' must be an array of field entries, or null to reset."
    )


class CreateFormConfigToolGroup(BaseToolGroup):
    """COMP-MC-003 — create-dialog form definition MCP tool group (1 read, 1 write)."""

    _TOOL_MAP = {
        "create_form_definition.get": "_handle_get",
        "create_form_definition.set": "_handle_set",
        "create_form_definition.export": "_handle_export",
        "create_form_definition.import": "_handle_import",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "create_form_definition.get",
            "description": (
                "Read the create dialog's form definition (Issue #1263): which "
                "fields are visible, their order, requiredness and default. "
                "``scope=\"effective\"`` (default) resolves user > workspace > "
                "global > definition default and reports which level supplied "
                "the value; any other scope returns that level's stored value. "
                "``item_type`` is required for the effective scope and optional "
                "otherwise (omitted = the whole {item_type: [...]} map). The "
                "response carries the definition-derived catalogue so a caller "
                "can render a picker. Identical to the REST "
                "GET .../create-form-config/ endpoints."
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
                            "UUID of the workspace whose attribute definition "
                            "supplies the base fields and whose override "
                            "participates in the effective resolution."
                        ),
                    },
                },
            },
        },
        {
            "name": "create_form_definition.set",
            "description": (
                "Store (or reset) the create dialog's form definition for one "
                "artifact type on one level (Issue #1263). ``fields`` is an "
                "ordered array of {\"field_key\", \"visible\", \"required\", "
                "\"order\", \"default\"} entries over the catalogue from "
                "``create_form_definition.get``; ``null`` resets the level so "
                "resolution falls back to the next one. Scope \"user\" is "
                "self-service; \"workspace\" requires write authority in the "
                "workspace (workspace_id required); \"global\" requires the admin "
                "role. Identical to the REST PATCH endpoints."
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
                            "Ordered field entries; null resets the level for "
                            "this item type."
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
        {
            "name": "create_form_definition.export",
            "description": (
                "Serialize one level's create-dialog form definition as a "
                "portable, versioned document (Issue #1263). Round-trips through "
                "``create_form_definition.import``. ``fields`` is the level's "
                "stored entries, or null when it inherits."
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
                        "description": "Artifact type to export.",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace; required for scope "
                            "\"workspace\"."
                        ),
                    },
                },
                "required": ["scope", "item_type"],
            },
        },
        {
            "name": "create_form_definition.import",
            "description": (
                "Import a document produced by "
                "``create_form_definition.export`` into one level (Issue #1263). "
                "Validated exactly like an edited definition. ``fields: null`` "
                "resets the level. Scope \"user\" is self-service; \"workspace\" "
                "requires write authority; \"global\" requires the admin role."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": list(WRITABLE_SCOPES),
                    },
                    "item_type": {"type": "string"},
                    "document": {
                        "type": "object",
                        "description": (
                            "The exported document ({schema_version, item_type, "
                            "scope, fields})."
                        ),
                    },
                    "workspace_id": {"type": "string"},
                },
                "required": ["scope", "item_type", "document"],
            },
        },
    ]

    def _service(self) -> CreateFormConfigService:
        return CreateFormConfigService()

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """create_form_definition.get — the effective / per-level form."""
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
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """create_form_definition.set — store/reset one level's form."""
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
        workspace_id: Optional[UUID] = optional_uuid(params, "workspace_id")
        if scope == SCOPE_WORKSPACE and workspace_id is None:
            raise ParameterError(
                "Parameter 'workspace_id' is required for scope 'workspace'."
            )
        if scope == SCOPE_USER and workspace_id is not None:
            raise ParameterError("Scope 'user' must not carry a workspace_id.")

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

    def _handle_export(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """create_form_definition.export — one level as a versioned document."""
        scope, item_type, workspace_id = self._level_params(params)
        try:
            return ToolResult.ok(
                self._service().export_config(
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

    def _handle_import(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """create_form_definition.import — load a versioned document into a level."""
        scope, item_type, workspace_id = self._level_params(params)
        document = params.get("document")
        if not isinstance(document, dict):
            raise ParameterError("Parameter 'document' must be an object.")
        try:
            return ToolResult.ok(
                self._service().import_config(
                    auth_context,
                    scope=scope,
                    item_type=item_type,
                    payload=document,
                    workspace_id=workspace_id,
                )
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

    @staticmethod
    def _level_params(
        params: Dict[str, Any],
    ) -> "tuple[str, str, Optional[UUID]]":
        """Shared ``scope``/``item_type``/``workspace_id`` normalization."""
        scope = str(params.get("scope") or "").strip().lower()
        if scope not in WRITABLE_SCOPES:
            raise ParameterError(
                f"Parameter 'scope' must be one of {list(WRITABLE_SCOPES)}."
            )
        item_type = params.get("item_type")
        if not item_type or not str(item_type).strip():
            raise ParameterError("Parameter 'item_type' is required.")
        workspace_id: Optional[UUID] = optional_uuid(params, "workspace_id")
        if scope == SCOPE_WORKSPACE and workspace_id is None:
            raise ParameterError(
                "Parameter 'workspace_id' is required for scope 'workspace'."
            )
        if scope == SCOPE_USER and workspace_id is not None:
            raise ParameterError("Scope 'user' must not carry a workspace_id.")
        return scope, str(item_type).strip(), workspace_id


__all__ = ["CreateFormConfigToolGroup"]
