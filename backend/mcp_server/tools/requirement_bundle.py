"""
RequirementBundleToolGroup — requirement_bundle.* MCP tools (Requirement
Bundle Export, Plan 1 Task 6).

Tools implemented:
  requirement_bundle.export            — grouped requirement export by
                                          architecture element (ALLOCATED_TO)
  requirement_bundle.attribute_schema  — list available/visible attributes

Interface contracts implemented:
  IF-MC-INT-003     — inbound: execute_tool(tool_name, params, auth_context,
                       api_key) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService
    (RequirementBundleQueryService, AttributeVisibilityConfigService)

Both tools are read-only (no persistence, no audit entry) — mirrors
architecture.get/query, not architecture.create/update. Registered in
``mcp_server/tool_registry.py``'s ``_READ_ONLY_TOOL_NAMES`` so they stay
outside the WRITE RBAC gate.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from auth_tenancy.context import AuthContext

from application.attribute_visibility_service import AttributeVisibilityConfigService
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.requirement_bundle_formatters import (
    format_bundle_csv,
    format_bundle_json,
    format_bundle_markdown,
)
from application.requirement_bundle_service import RequirementBundleQueryService

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_uuid

logger = logging.getLogger(__name__)

_OUTPUT_FORMATS = ("json", "markdown", "csv")


class RequirementBundleToolGroup(BaseToolGroup):
    """requirement_bundle tool group (2 tools)."""

    _TOOL_MAP = {
        "requirement_bundle.export": "_handle_export",
        "requirement_bundle.attribute_schema": "_handle_attribute_schema",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "requirement_bundle.export",
            "description": (
                "Export every Requirement ALLOCATED_TO the given "
                "ArchitectureElement or its ALLOCATED_TO sub-elements, up to "
                "a configurable depth."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "root_id": {"type": "string", "description": "UUID of the root ArchitectureElement."},
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "depth": {
                        "type": "integer",
                        "description": "0 = only requirements directly allocated to root; omit for full hierarchy.",
                    },
                    "filter_mode": {
                        "type": "string",
                        "enum": ["all", "visible", "custom"],
                        "description": "Attribute selection mode. Defaults to 'all'.",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Field names to include; required when filter_mode='custom'.",
                    },
                    "format": {
                        "type": "string",
                        "enum": list(_OUTPUT_FORMATS),
                        "description": "Output format. Defaults to 'json'.",
                    },
                },
                "required": ["root_id", "workspace_id"],
            },
        },
        {
            "name": "requirement_bundle.attribute_schema",
            "description": (
                "List available attributes for an entity type, with current "
                "visibility. Response shape: {\"attributes\": [...], "
                "\"count\": N} - note this differs from the REST "
                "AttributeSchemaView endpoint, which returns the same "
                "attribute list as a bare top-level JSON array (no "
                "wrapping object); ToolResult requires a dict, so the MCP "
                "and REST payload shapes are not interchangeable."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Optional entity type filter, e.g. 'Requirement'. Omit for all known types.",
                    },
                },
                "required": [],
            },
        },
    ]

    # ------------------------------------------------------------------
    # requirement_bundle.export
    # ------------------------------------------------------------------

    def _handle_export(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement_bundle.export — raw (non-AI) requirement bundle export."""
        root_id = require_uuid(params, "root_id")
        workspace_id = require_uuid(params, "workspace_id")

        depth_param = params.get("depth")
        depth = None
        if depth_param is not None:
            try:
                depth = int(depth_param)
            except (TypeError, ValueError):
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Parameter 'depth' must be an integer, got {depth_param!r}",
                )

        filter_mode = params.get("filter_mode", "all")
        fields = params.get("fields")

        output_format = params.get("format", "json")
        if output_format not in _OUTPUT_FORMATS:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Invalid format {output_format!r}; expected one of {_OUTPUT_FORMATS}",
            )

        try:
            result = RequirementBundleQueryService().get_bundle(
                auth_context,
                root_id=root_id,
                workspace_id=workspace_id,
                depth=depth,
                filter_mode=filter_mode,
                fields=fields,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            # Covers BundleDepthExceededError too (subclass of ValidationError).
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if output_format == "json":
            return ToolResult.ok(format_bundle_json(result))
        if output_format == "markdown":
            return ToolResult.ok(
                {"format": "markdown", "content": format_bundle_markdown(result)}
            )
        return ToolResult.ok({"format": "csv", "content": format_bundle_csv(result)})

    # ------------------------------------------------------------------
    # requirement_bundle.attribute_schema
    # ------------------------------------------------------------------

    def _handle_attribute_schema(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement_bundle.attribute_schema — discover valid field names."""
        entity_type = params.get("entity_type")
        try:
            schema = AttributeVisibilityConfigService().describe_schema(
                auth_context, entity_type=entity_type
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"attributes": schema, "count": len(schema)})


__all__ = ["RequirementBundleToolGroup"]
