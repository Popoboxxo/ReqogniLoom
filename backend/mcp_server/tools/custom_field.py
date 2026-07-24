"""
COMP-MC-? CustomFieldToolGroup — read-only CustomField MCP tool group (Phase 1 Task 6).

leaf_id : COMP-MC-006 (CustomField, read-only)
req_id  : REQ-L2-MC-??? (MCP audit trail for read operations)

Tools implemented:
  custom_field.get     — fetch a custom field definition by ID (read)
  custom_field.query   — list custom field definitions for a workspace (read)

Deliberately NOT implemented:
  custom_field.create   — write operations forbidden to protect workspace configuration
  custom_field.update   — write operations forbidden to protect workspace configuration
  custom_field.delete   — write operations forbidden to protect workspace configuration
  custom_field.outdate  — write operations forbidden to protect workspace configuration

Wraps ``CustomFieldService`` read methods directly (ADR-L3-MC003-01 analog:
dedicated handler method per tool, own tool group).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from auth_tenancy.context import AuthContext

from application.custom_field_service import CustomFieldService
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    optional_uuid,
    require_uuid,
)

logger = logging.getLogger(__name__)


def _definition_to_dict(definition: Any) -> Dict[str, Any]:
    """Serialise a CustomFieldDefinition for MCP responses."""
    return {
        "id": str(definition.id),
        "workspace_id": str(definition.workspace_id) if definition.workspace_id else None,
        "name": definition.name,
        "field_type": definition.field_type,
        "is_required": definition.is_required,
        "options": definition.options or [],
        "order": definition.order,
        "version": definition.version,
        "created_by_id": str(definition.created_by_id) if definition.created_by_id else None,
        "modified_by_id": str(definition.modified_by_id) if definition.modified_by_id else None,
    }


class CustomFieldToolGroup(BaseToolGroup):
    """CustomField tool group (2 read-only tools) — wraps ``CustomFieldService`` methods."""

    _TOOL_MAP = {
        "custom_field.get": "_handle_get",
        "custom_field.query": "_handle_query",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "custom_field.get",
            "description": "Fetch a custom field definition by ID (read-only).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the custom field definition."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "custom_field.query",
            "description": "List custom field definitions for a workspace (read-only).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                },
                "required": ["workspace_id"],
            },
        },
    ]

    @staticmethod
    def _get_service() -> CustomFieldService:
        """Return a CustomFieldService instance."""
        return CustomFieldService()

    # ------------------------------------------------------------------
    # custom_field.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """custom_field.get — fetch a custom field definition by ID (read-only)."""
        definition_id = require_uuid(params, "id")
        service = self._get_service()

        try:
            definition = service.get_definition(auth_context, definition_id)
        except Exception as exc:
            # CustomFieldService.get_definition raises NotFoundError or similar
            return ToolResult.error("NOT_FOUND", str(exc))

        return ToolResult.ok({"definition": _definition_to_dict(definition)})

    # ------------------------------------------------------------------
    # custom_field.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """custom_field.query — list custom field definitions for a workspace (read-only)."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for custom_field.query.",
            )
        service = self._get_service()

        try:
            definitions = service.list_definitions(auth_context, workspace_id)
            return ToolResult.ok(
                {
                    "definitions": [_definition_to_dict(d) for d in definitions],
                    "count": len(definitions),
                }
            )
        except Exception as exc:
            logger.exception("Error listing custom field definitions for workspace=%s", workspace_id)
            return ToolResult.error("INTERNAL_ERROR", str(exc))


__all__ = ["CustomFieldToolGroup"]
