"""
MCP Tool Group for Stakeholder Needs.
"""
from typing import Any, Dict, Optional

from application.ai_derivation_service import AiDerivationService
from application.base import NotFoundError, ValidationError
from application.requirement_service import RequirementService
from application.stakeholder_need_service import StakeholderNeedService
from auth_tenancy.context import AuthContext
from mcp_server.tools.ai_derivation import (
    _MODE_POLICY_SCHEMA_PROPERTIES,
    derive_requirements_from_need,
)
from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
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
        "needs.query": "_handle_query",
        "needs.create": "_handle_create",
        "needs.update": "_handle_update",
        "needs.get_traces": "_handle_get_traces",
        "needs.derive_requirements": "_handle_derive",
        "needs.outdate": "_handle_outdate",
        "needs.reactivate": "_handle_reactivate",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "needs.read",
            "description": "Fetch a single StakeholderNeed by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the stakeholder need."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "needs.query",
            "description": "List StakeholderNeeds for a workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "include_deleted": {
                        "type": "boolean",
                        "description": "Include soft-deleted needs (default: false).",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "needs.create",
            "description": "Create a new StakeholderNeed (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "title": {"type": "string", "description": "Need title."},
                    "description": {"type": "string", "description": "Need description."},
                    "category": {"type": "string", "description": "Need category."},
                    "moscow_priority": {
                        "type": "string",
                        "description": "MoSCoW priority (Must/Should/Could/Won't).",
                    },
                },
                "required": ["workspace_id", "title"],
            },
        },
        {
            "name": "needs.update",
            "description": "Update an existing StakeholderNeed (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the stakeholder need."},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "status": {
                        "type": "string",
                        "description": (
                            "READ-ONLY (REQ-143). Ignored on write — the "
                            "WorkflowEngine owns the lifecycle state. Present "
                            "for backward compatibility only."
                        ),
                    },
                    "moscow_priority": {"type": "string"},
                    "change_reason": {"type": "string", "description": "Reason for the change."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "needs.get_traces",
            "description": "List incoming and outgoing TraceLinks for a StakeholderNeed.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the stakeholder need."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "needs.derive_requirements",
            "description": (
                "Propose system requirement drafts for a StakeholderNeed (LLM). "
                "Synchronous — mode='preview' (default) returns drafts only; "
                "mode='write' persists each draft as a Requirement and links "
                "it back to the need via a 'derives-from' trace link. "
                "Equivalent to ai_derivation.derive_requirements_from_need "
                "(fix #112 — this tool used to dispatch an async task that "
                "sent the LLM only the need's UUID, persisted nothing, and "
                "had no reachable task-status endpoint)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the stakeholder need."},
                    "n": {
                        "type": "integer",
                        "description": (
                            "Optional upper bound on requirement drafts. Omit to "
                            "use the workspace's configured "
                            "max_requirements_per_need (default 3)."
                        ),
                    },
                    **_MODE_POLICY_SCHEMA_PROPERTIES,
                },
                "required": ["id"],
            },
        },
        {
            "name": "needs.outdate",
            "description": "Soft-delete a StakeholderNeed via the workflow engine's outdate escape hatch (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the stakeholder need."},
                    "reason": {"type": "string", "description": "Optional audit reason."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "needs.reactivate",
            "description": "Restore an outdated StakeholderNeed to its previous state (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the stakeholder need."},
                },
                "required": ["id"],
            },
        },
    ]

    def __init__(
        self,
        service: Optional[StakeholderNeedService] = None,
        ai_derivation_service: Optional[AiDerivationService] = None,
        requirement_service: Optional[RequirementService] = None,
    ) -> None:
        self._service = service or StakeholderNeedService()
        # fix #112: needs.derive_requirements delegates to the same
        # AiDerivationService/RequirementService pair the working
        # ai_derivation.derive_requirements_from_need tool uses, instead of
        # the broken StakeholderNeedService.derive_requirements_async path
        # (UUID-only prompt, no persistence, unreachable task status).
        self._ai_derivation_service = ai_derivation_service or AiDerivationService()
        self._requirement_service = requirement_service or RequirementService()

    def _handle_read(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        need_id = require_uuid(params, "id")
        try:
            need = self._service.get(auth_context, need_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"need": _need_to_dict(need)})

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """needs.query — list StakeholderNeeds, optionally filtered by workspace."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for needs.query.",
            )
        include_deleted = bool(params.get("include_deleted", False))
        needs = self._service.list_by_workspace(
            auth_context, workspace_id, include_deleted=include_deleted
        )
        return ToolResult.ok({
            "needs": [_need_to_dict(n) for n in needs],
            "count": len(needs),
        })

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
        
        # Use Unset magic value if not provided.
        # REQ-143: `status` is deliberately excluded — the WorkflowEngine is the
        # single source of truth for the lifecycle state. A client-sent `status`
        # is ignored (not an error) and the response reflects the true value.
        kwargs = {}
        for f in ["title", "description", "category", "moscow_priority"]:
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
        from application.trace_link_service import TraceLinkService

        # Validate need exists. ADR-01 (#124): the tenant-scoped lookup lives in
        # StakeholderNeedService.get(), which runs the exact same
        # select_related("artifact") query and exposes artifact_id on the DTO —
        # no behaviour change, only the layering violation goes. The lookup is
        # kept in its own try block so that a NotFoundError raised further down
        # by TraceLinkService still maps to INTERNAL_ERROR, exactly as it did
        # when this was a StakeholderNeed.DoesNotExist catch.
        try:
            need_dto = self._service.get(ctx=auth_context, need_id=need_id)
        except NotFoundError:
            return ToolResult.error("NOT_FOUND", f"StakeholderNeed {need_id} not found.")

        artifact_id = need_dto.artifact_id
        try:
            trace_service = TraceLinkService()
            # query_trace_links returns NeighborResult objects whose neighbor is
            # exposed as `entity_id` (not source_id/target_id). Upstream = incoming
            # (links pointing at this artifact), downstream = outgoing.
            incoming = trace_service.query_trace_links(
                entity_id=artifact_id, direction="upstream", ctx=auth_context
            )
            outgoing = trace_service.query_trace_links(
                entity_id=artifact_id, direction="downstream", ctx=auth_context
            )

            return ToolResult.ok({
                "source_need": str(need_id),
                "incoming_traces": [{"source": str(t.entity_id), "type": t.link_type} for t in incoming],
                "outgoing_traces": [{"target": str(t.entity_id), "type": t.link_type} for t in outgoing],
            })
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_derive(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Derive system requirement drafts from this stakeholder need (LLM).

        fix #112: delegates to the shared
        :func:`mcp_server.tools.ai_derivation.derive_requirements_from_need`
        implementation — the same context-building (real need title/text,
        not just the UUID), persistence and mode/policy semantics as
        ``ai_derivation.derive_requirements_from_need`` — instead of the
        previous ``StakeholderNeedService.derive_requirements_async`` path,
        which sent the LLM only the need's UUID, never persisted a result,
        and returned a task_id with no reachable status endpoint. The tool's
        public parameter stays ``id`` (unchanged, backward compatible); it is
        forwarded internally as ``need_id`` for the shared implementation.
        """
        need_id = require_uuid(params, "id")
        shared_params = dict(params)
        shared_params["need_id"] = str(need_id)
        return derive_requirements_from_need(
            service=self._ai_derivation_service,
            requirement_service=self._requirement_service,
            params=shared_params,
            auth_context=auth_context,
            api_key=api_key,
        )

    def _handle_outdate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """needs.outdate — soft-delete via the workflow engine (write, audited)."""
        need_id = require_uuid(params, "id")
        reason: str = params.get("reason", "")

        try:
            need = self._service.get(auth_context, need_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        from workflow.services import outdate

        try:
            outdate(
                item_id=need_id,
                item_type="StakeholderNeed",
                workspace_id=need.workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="outdate",
            entity_type="StakeholderNeed",
            entity_id=need_id,
            tool_name="needs.outdate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(need_id), "status": "outdated"})

    def _handle_reactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """needs.reactivate — restore a previously outdated StakeholderNeed (write, audited)."""
        need_id = require_uuid(params, "id")

        try:
            need = self._service.get(auth_context, need_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        from workflow.services import reactivate

        try:
            result = reactivate(
                item_id=need_id,
                item_type="StakeholderNeed",
                workspace_id=need.workspace_id,
                ctx=auth_context,
            )
        except ValueError as exc:
            return ToolResult.error("INVALID_STATE", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="reactivate",
            entity_type="StakeholderNeed",
            entity_id=need_id,
            tool_name="needs.reactivate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(need_id), "status": result.new_state})


__all__ = ["StakeholderNeedsToolGroup"]
