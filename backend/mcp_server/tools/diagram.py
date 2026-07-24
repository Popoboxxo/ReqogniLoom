"""
COMP-MC-003-style DiagramToolGroup — Diagram MCP tool group (Phase 1 Task 5).

leaf_id : COMP-DS-001 (DiagramManager, wrapped via diagram.services)
req_id  : REQ-L2-DS-001, REQ-L3-DM-001..004, REQ-L2-MC-012 (MCP audit trail)

Tools implemented:
  diagram.create      — create a new diagram + initial version (write, audited)
  diagram.get         — fetch a diagram (header + current/specific version)
  diagram.update      — append a new immutable version (write, audited)
  diagram.query       — list diagrams for a workspace
  diagram.outdate     — soft-delete via the workflow engine (write, audited)
  diagram.reactivate  — restore a previously outdated diagram (write, audited)

Unlike ``RequirementsToolGroup``/``StakeholderNeedsToolGroup``, ``diagram/
services.py`` exposes module-level functions rather than an
ApplicationService class — this tool group calls those functions directly
instead of wrapping a service instance (ADR-L3-MC003-01 analog: dedicated
handler method per tool, own tool group).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from auth_tenancy.context import AuthContext

from diagram.models import Diagram
from diagram.services import (
    DiagramResult,
    DiagramValidationError,
    create_diagram,
    delete_diagram,
    get_diagram,
    get_diagram_header,
    list_diagrams,
    update_diagram,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


def _diagram_header_to_dict(diagram: Diagram) -> Dict[str, Any]:
    """Serialise a Diagram header (no version payload) for MCP responses."""
    return {
        "id": str(diagram.id),
        "name": diagram.name,
        "diagram_type": diagram.diagram_type,
        "description": diagram.description,
        "workspace_id": str(diagram.workspace_id) if diagram.workspace_id else None,
        "current_version": (
            str(diagram.current_version_id) if diagram.current_version_id else None
        ),
    }


class DiagramToolGroup(BaseToolGroup):
    """Diagram tool group (6 tools) — wraps ``diagram.services`` module functions."""

    _TOOL_MAP = {
        "diagram.create": "_handle_create",
        "diagram.get": "_handle_get",
        "diagram.update": "_handle_update",
        "diagram.query": "_handle_query",
        "diagram.outdate": "_handle_outdate",
        "diagram.reactivate": "_handle_reactivate",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "diagram.create",
            "description": "Create a new diagram with its initial version (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the owning workspace."},
                    "name": {"type": "string", "description": "Diagram name."},
                    "diagram_type": {
                        "type": "string",
                        "description": "One of 'block' | 'flow' | 'context' | 'canvas' | 'mermaid'.",
                    },
                    "payload_format": {
                        "type": "string",
                        "description": "One of 'mermaid' | 'plantuml' | 'json' | 'canvas_stroke'.",
                    },
                    "content": {"type": "string", "description": "Raw diagram payload string."},
                    "description": {"type": "string", "description": "Optional free-text description."},
                    "target_id": {
                        "type": "string",
                        "description": "Optional target Artifact UUID for a 'documents' TraceLink.",
                    },
                },
                "required": ["name", "diagram_type", "payload_format", "content"],
            },
        },
        {
            "name": "diagram.get",
            "description": "Fetch a diagram by ID (current or a specific version).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the diagram."},
                    "version_number": {
                        "type": "integer",
                        "description": "Optional specific version. Defaults to current.",
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "diagram.update",
            "description": "Append a new immutable version to an existing diagram (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the diagram."},
                    "payload_format": {"type": "string", "description": "New payload format."},
                    "content": {"type": "string", "description": "New raw payload string."},
                    "target_id": {
                        "type": "string",
                        "description": "Optional target Artifact UUID for an additional TraceLink.",
                    },
                },
                "required": ["id", "payload_format", "content"],
            },
        },
        {
            "name": "diagram.query",
            "description": "List diagrams for a workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "include_deleted": {
                        "type": "boolean",
                        "description": "If true, include outdated (soft-deleted) diagrams. Defaults to false.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "diagram.outdate",
            "description": "Soft-delete a diagram via the workflow engine's outdate escape hatch (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the diagram."},
                    "reason": {"type": "string", "description": "Optional audit reason."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "diagram.reactivate",
            "description": "Restore an outdated diagram to its previous state (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the diagram."},
                },
                "required": ["id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # Tenant/user resolution — diagram/services.py's create/update take
    # ORM Tenant/User objects, not bare ids (TenantScopedModel requirement).
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_tenant(auth_context: AuthContext) -> Any:
        from persistence.models import Tenant

        return Tenant.objects.get(id=auth_context.tenant_id)

    @staticmethod
    def _resolve_user(auth_context: AuthContext) -> Optional[Any]:
        from persistence.models import User

        return User.objects.filter(id=auth_context.user_id).first()

    # ------------------------------------------------------------------
    # diagram.create
    # ------------------------------------------------------------------

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """diagram.create — create a new diagram + initial version (write, audited)."""
        name = require_param(params, "name")
        diagram_type = require_param(params, "diagram_type")
        payload_format = require_param(params, "payload_format")
        content = require_param(params, "content")
        description: str = params.get("description", "")
        workspace_id = optional_uuid(params, "workspace_id")
        target_id = optional_uuid(params, "target_id")

        tenant = self._resolve_tenant(auth_context)
        user = self._resolve_user(auth_context)

        try:
            diagram = create_diagram(
                name=str(name),
                diagram_type=str(diagram_type),
                payload_format=str(payload_format),
                content=str(content),
                tenant=tenant,
                description=str(description),
                created_by=user,
                target_id=target_id,
                workspace_id=workspace_id,
            )
        except DiagramValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="Diagram",
            entity_id=diagram.id,
            tool_name="diagram.create",
            api_key=api_key,
        )
        return ToolResult.ok({"diagram": _diagram_header_to_dict(diagram)})

    # ------------------------------------------------------------------
    # diagram.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """diagram.get — fetch a diagram (current or a specific version)."""
        diagram_id = require_uuid(params, "id")
        version_number = params.get("version_number")

        try:
            result: DiagramResult = get_diagram(
                diagram_id=diagram_id, version_number=version_number
            )
        except Diagram.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"Diagram {diagram_id} not found.")

        diagram = result.diagram
        version = result.version
        payload = _diagram_header_to_dict(diagram)
        payload.update(
            {
                "payload_format": version.payload_format if version else None,
                "content": version.payload if version else None,
                "version_number": version.version_number if version else None,
            }
        )
        return ToolResult.ok({"diagram": payload})

    # ------------------------------------------------------------------
    # diagram.update
    # ------------------------------------------------------------------

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """diagram.update — append a new immutable version (write, audited)."""
        diagram_id = require_uuid(params, "id")
        payload_format = require_param(params, "payload_format")
        content = require_param(params, "content")
        target_id = optional_uuid(params, "target_id")

        user = self._resolve_user(auth_context)

        try:
            new_version = update_diagram(
                diagram_id=diagram_id,
                payload_format=str(payload_format),
                content=str(content),
                modified_by=user,
                target_id=target_id,
            )
        except Diagram.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"Diagram {diagram_id} not found.")
        except DiagramValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="Diagram",
            entity_id=diagram_id,
            tool_name="diagram.update",
            api_key=api_key,
        )
        return ToolResult.ok(
            {
                "diagram": {
                    "id": str(diagram_id),
                    "version_number": new_version.version_number,
                    "payload_format": new_version.payload_format,
                    "content": new_version.payload,
                }
            }
        )

    # ------------------------------------------------------------------
    # diagram.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """diagram.query — list diagrams for a workspace."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for diagram.query.",
            )
        include_deleted = bool(params.get("include_deleted", False))

        diagrams = list_diagrams(
            workspace_id=workspace_id,
            tenant_id=auth_context.tenant_id,
            include_deleted=include_deleted,
        )
        return ToolResult.ok(
            {
                "diagrams": [_diagram_header_to_dict(d) for d in diagrams],
                "count": len(diagrams),
            }
        )

    # ------------------------------------------------------------------
    # diagram.outdate
    # ------------------------------------------------------------------

    def _handle_outdate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """diagram.outdate — soft-delete via the workflow engine (write, audited)."""
        diagram_id = require_uuid(params, "id")
        reason: str = params.get("reason", "")

        try:
            diagram = get_diagram_header(diagram_id, auth_context.tenant_id)
        except Diagram.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"Diagram {diagram_id} not found.")

        if diagram.workspace_id is None:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Diagram {diagram_id} has no workspace assigned; workflow unavailable.",
            )

        from workflow.services import outdate

        try:
            outdate(
                item_id=diagram_id,
                item_type="Diagram",
                workspace_id=diagram.workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="outdate",
            entity_type="Diagram",
            entity_id=diagram_id,
            tool_name="diagram.outdate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(diagram_id), "status": "outdated"})

    # ------------------------------------------------------------------
    # diagram.reactivate
    # ------------------------------------------------------------------

    def _handle_reactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """diagram.reactivate — restore a previously outdated diagram (write, audited)."""
        diagram_id = require_uuid(params, "id")

        try:
            diagram = get_diagram_header(diagram_id, auth_context.tenant_id)
        except Diagram.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"Diagram {diagram_id} not found.")

        if diagram.workspace_id is None:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Diagram {diagram_id} has no workspace assigned; workflow unavailable.",
            )

        from workflow.services import reactivate

        try:
            result = reactivate(
                item_id=diagram_id,
                item_type="Diagram",
                workspace_id=diagram.workspace_id,
                ctx=auth_context,
            )
        except ValueError as exc:
            return ToolResult.error("INVALID_STATE", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="reactivate",
            entity_type="Diagram",
            entity_id=diagram_id,
            tool_name="diagram.reactivate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(diagram_id), "status": result.new_state})


__all__ = ["DiagramToolGroup"]
