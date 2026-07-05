"""
MCP Tool Group for Stakeholder Needs.
"""
from typing import Any, Dict, Optional

from application.base import NotFoundError, ValidationError
from application.stakeholder_need_service import StakeholderNeedService
from auth_tenancy.context import AuthContext
from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    optional_uuid,
    require_param,
    require_uuid,
)


def _need_to_dict(n: Any) -> dict:
    return {
        "id": str(n.id),
        "workspace_id": str(n.workspace_id),
        "title": n.title,
        "description": n.description,
        "category": n.category,
        "status": n.status,
        "moscow_priority": n.moscow_priority,
        "version": n.version,
    }


class StakeholderNeedsToolGroup(BaseToolGroup):
    """Stakeholder Needs tool group."""

    _TOOL_MAP = {
        "needs.read": "_handle_read",
        "needs.create": "_handle_create",
        "needs.update": "_handle_update",
        "needs.get_traces": "_handle_get_traces",
        "needs.derive_requirements": "_handle_derive",
    }

    def __init__(self, service: Optional[StakeholderNeedService] = None) -> None:
        self._service = service or StakeholderNeedService()

    def _handle_read(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        need_id = require_uuid(params, "id")
        try:
            need = self._service.get(auth_context, need_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"need": _need_to_dict(need)})

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        title = require_param(params, "title")
        workspace_id = require_uuid(params, "workspace_id")
        description = params.get("description", "")
        category = params.get("category", "")
        moscow_priority = params.get("moscow_priority")

        try:
            need = self._service.create(
                ctx=auth_context,
                workspace_id=workspace_id,
                title=title,
                description=description,
                category=category,
                moscow_priority=moscow_priority,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
            
        return ToolResult.ok({"need": _need_to_dict(need)})

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        need_id = require_uuid(params, "id")
        change_reason = params.get("change_reason", "Update via MCP")
        
        # Use Unset magic value if not provided
        from application.stakeholder_need_service import _UNSET
        
        kwargs = {}
        for f in ["title", "description", "category", "status", "moscow_priority"]:
            if f in params:
                kwargs[f] = params[f]

        try:
            need = self._service.update(
                ctx=auth_context,
                need_id=need_id,
                change_reason=change_reason,
                **kwargs,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
            
        return ToolResult.ok({"need": _need_to_dict(need)})

    def _handle_get_traces(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        need_id = require_uuid(params, "id")
        # For now, just return a placeholder or query the application layer
        from application.trace_link_service import TraceLinkService
        try:
            need = self._service.get(auth_context, need_id)
            # Fetch traces for the artifact ID
            # This requires fetching the DB model to get the artifact ID
            from persistence.models import StakeholderNeed
            need_model = StakeholderNeed.objects.get(id=need_id, tenant_id=auth_context.tenant_id)
            artifact_id = need_model.artifact_id
            
            trace_service = TraceLinkService()
            incoming = trace_service.list_incoming(artifact_id, auth_context)
            outgoing = trace_service.list_outgoing(artifact_id, auth_context)
            
            return ToolResult.ok({
                "incoming_traces": [{"source": str(t.source_id), "type": t.link_type} for t in incoming],
                "outgoing_traces": [{"target": str(t.target_id), "type": t.link_type} for t in outgoing],
            })
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_derive(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Derive system requirements from this stakeholder need (Foundation for AI)."""
        need_id = require_uuid(params, "id")
        
        return ToolResult.ok({
            "status": "not_implemented",
            "message": "AI derivation foundation is set up. Use requirement.create and manual traceability for now.",
            "source_need": str(need_id)
        })

__all__ = ["StakeholderNeedsToolGroup"]
