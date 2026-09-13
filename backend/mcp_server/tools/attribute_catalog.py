"""AttributeCatalogToolGroup — MCP surface for the central attribute catalog.

Attribut v3 WS5 (#942, spec section 8). Modelled on
``mcp_server/tools/attribute_definition.py``.

Eight tools:

  attribute_catalog.list             — list/filter catalog entries (read, admin)
  attribute_catalog.search           — name search (+ category/tags) (read, admin)
  attribute_catalog.create           — create an entry (write, admin)
  attribute_catalog.update           — partially update an entry (write, admin)
  attribute_catalog.deprecate        — set/lift the deprecated flag (write, admin)
  attribute_catalog.add_to_definition — copy an entry into a definition (write, admin)
  attribute_catalog.export           — download a catalog document (read, admin)
  attribute_catalog.import           — merge a catalog document (write, admin)

Fail-closed writes: the registry's RBAC gate treats every unrecognised tool as a
write (``tool_registry._is_write_tool``), and ``list``/``search``/``export``
are explicitly registered as read-only there. The service additionally asserts
the ``admin`` role on every operation, so a non-admin gets
``PERMISSION_DENIED`` and never a silent success.

No ORM in this module (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access_mcp_tools``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from auth_tenancy.context import AuthContext

from application.attribute_catalog_service import (
    AttributeCatalogNotFound,
    AttributeCatalogService,
)
from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeSchemaError,
)
from application.base import PermissionDeniedError
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_param, require_uuid
from presets.exceptions import CrossTenantWorkspaceError

logger = logging.getLogger(__name__)


def _tags_from_params(params: Dict[str, Any]) -> Optional[List[str]]:
    tags = params.get("tags")
    if tags is None:
        return None
    if not isinstance(tags, list):
        raise AttributeSchemaError(["'tags' must be a list of strings"])
    return [str(tag) for tag in tags]


class AttributeCatalogToolGroup(BaseToolGroup):
    """Central attribute-catalog tool group (3 read + 5 write tools)."""

    _TOOL_MAP = {
        "attribute_catalog.list": "_handle_list",
        "attribute_catalog.search": "_handle_search",
        "attribute_catalog.create": "_handle_create",
        "attribute_catalog.update": "_handle_update",
        "attribute_catalog.deprecate": "_handle_deprecate",
        "attribute_catalog.add_to_definition": "_handle_add_to_definition",
        "attribute_catalog.export": "_handle_export",
        "attribute_catalog.import": "_handle_import",
    }

    @staticmethod
    def _get_service() -> AttributeCatalogService:
        return AttributeCatalogService()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        filter_properties = {
            "query": {"type": "string", "description": "Name substring (case-insensitive)."},
            "category": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "include_deprecated": {"type": "boolean", "default": False},
        }
        entry_id_property = {"type": "string", "description": "Catalog entry UUID."}
        return [
            {
                "name": "attribute_catalog.list",
                "description": "List the tenant's attribute-catalog entries (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": dict(filter_properties),
                    "required": [],
                },
            },
            {
                "name": "attribute_catalog.search",
                "description": (
                    "Search the attribute catalog by name substring "
                    "(admin-only)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": dict(filter_properties),
                    "required": ["query"],
                },
            },
            {
                "name": "attribute_catalog.create",
                "description": "Create an attribute-catalog entry (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "definition": {
                            "type": "object",
                            "description": "One kind='extended' attribute block.",
                        },
                        "category": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "label": {"type": "object"},
                        "help_text": {"type": "object"},
                        "origin": {"type": "string"},
                    },
                    "required": ["name", "definition"],
                },
            },
            {
                "name": "attribute_catalog.update",
                "description": "Partially update an attribute-catalog entry (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entry_id": entry_id_property,
                        "name": {"type": "string"},
                        "definition": {"type": "object"},
                        "category": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "label": {"type": "object"},
                        "help_text": {"type": "object"},
                        "origin": {"type": "string"},
                        "deprecated": {"type": "boolean"},
                    },
                    "required": ["entry_id"],
                },
            },
            {
                "name": "attribute_catalog.deprecate",
                "description": "Mark an entry deprecated (or lift it) (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entry_id": entry_id_property,
                        "deprecated": {"type": "boolean", "default": True},
                    },
                    "required": ["entry_id"],
                },
            },
            {
                "name": "attribute_catalog.add_to_definition",
                "description": (
                    "Copy an entry's attribute block into a global (preset) or "
                    "workspace definition, resolving name collisions "
                    "(admin-only)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entry_id": entry_id_property,
                        "item_type": {"type": "string"},
                        "preset": {
                            "type": "string",
                            "enum": ["minimal", "standard", "extended"],
                        },
                        "workspace_id": {"type": "string"},
                        "on_collision": {
                            "type": "string",
                            "enum": ["skip", "overwrite", "rename"],
                            "default": "skip",
                        },
                    },
                    "required": ["entry_id", "item_type"],
                },
            },
            {
                "name": "attribute_catalog.export",
                "description": "Download the catalog as a re-importable document (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_deprecated": {"type": "boolean", "default": True},
                    },
                    "required": [],
                },
            },
            {
                "name": "attribute_catalog.import",
                "description": "Merge a catalog document into this tenant (admin-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document": {
                            "type": "object",
                            "description": "attribute_catalog.export's output.",
                        },
                        "on_collision": {
                            "type": "string",
                            "enum": ["skip", "overwrite", "rename"],
                            "default": "skip",
                        },
                    },
                    "required": ["document"],
                },
            },
        ]

    # ---- Handlers ---------------------------------------------------------

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            entries = self._get_service().list_entries(
                auth_context,
                query=params.get("query") or None,
                category=params.get("category") or None,
                tags=_tags_from_params(params),
                include_deprecated=bool(params.get("include_deprecated", False)),
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"entries": entries, "count": len(entries)})

    def _handle_search(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        query = require_param(params, "query")
        try:
            entries = self._get_service().search_entries(
                auth_context,
                query=query,
                category=params.get("category") or None,
                tags=_tags_from_params(params),
                include_deprecated=bool(params.get("include_deprecated", False)),
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"entries": entries, "count": len(entries)})

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        name = require_param(params, "name")
        definition = params.get("definition")
        if not isinstance(definition, dict):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'definition' must be an object."
            )
        try:
            entry = self._get_service().create_entry(
                auth_context,
                name=name,
                definition=definition,
                category=params.get("category") or "",
                tags=params.get("tags"),
                label=params.get("label"),
                help_text=params.get("help_text"),
                origin=params.get("origin") or "",
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"entry": entry})

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        entry_id = require_uuid(params, "entry_id")
        kwargs: Dict[str, Any] = {
            key: params[key]
            for key in (
                "name", "definition", "category", "tags", "label",
                "help_text", "origin", "deprecated",
            )
            if key in params
        }
        try:
            entry = self._get_service().update_entry(
                auth_context, entry_id, **kwargs
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeCatalogNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"entry": entry})

    def _handle_deprecate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        entry_id = require_uuid(params, "entry_id")
        try:
            entry = self._get_service().deprecate_entry(
                auth_context,
                entry_id,
                deprecated=bool(params.get("deprecated", True)),
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeCatalogNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"entry": entry})

    def _handle_add_to_definition(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        entry_id = require_uuid(params, "entry_id")
        item_type = require_param(params, "item_type")
        workspace_id = (
            require_uuid(params, "workspace_id")
            if params.get("workspace_id")
            else None
        )
        try:
            result = self._get_service().add_to_definition(
                auth_context,
                entry_id,
                item_type,
                preset=params.get("preset") or None,
                workspace_id=workspace_id,
                on_collision=params.get("on_collision") or "skip",
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (AttributeCatalogNotFound, AttributeDefinitionNotFound) as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        except CrossTenantWorkspaceError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok(result)

    def _handle_export(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        try:
            document = self._get_service().export_catalog(
                auth_context,
                include_deprecated=bool(params.get("include_deprecated", True)),
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"document": document})

    def _handle_import(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        document = params.get("document")
        if not isinstance(document, dict):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'document' must be an object."
            )
        try:
            summary = self._get_service().import_catalog(
                auth_context,
                document,
                on_collision=params.get("on_collision") or "skip",
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"summary": summary})


__all__ = ["AttributeCatalogToolGroup"]
