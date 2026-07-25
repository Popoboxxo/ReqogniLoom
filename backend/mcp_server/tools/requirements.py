"""
COMP-MC-003 RequirementsToolGroup — 6 requirement.* MCP tools.

leaf_id : COMP-MC-003
req_id  : REQ-L2-MC-001 (6 Requirements Tools),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented:
  requirement.get        — fetch single requirement by ID
  requirement.query      — list requirements with optional workspace filter
  requirement.create     — create a new requirement (write, audited)
  requirement.update     — update an existing requirement (write, audited)
  requirement.decompose  — AI decomposition (requires LLM, audited)
  requirement.validate   — AI validation (requires LLM, audited)

Interface contracts implemented:
  IF-MC-INT-002  — inbound: execute_tool(tool_name, params, auth_context) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService (RequirementService) direct calls

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-003_RequirementsToolGroup/
      L3_COMP-MC-003_RequirementsToolGroup_Architecture.md

ADR-L3-MC003-01: Dedicated handler method per tool.
ADR-L3-MC003-02: Early LLM-availability check before ApplicationService call.
ADR-L3-MC003-03: Audit via ApplicationService._audit (already called by service).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from auth_tenancy.context import AuthContext

from application.services import (
    LlmNotConfiguredError,
    NotFoundError,
    RequirementService,
    ValidationError,
    PermissionDeniedError,
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


def _requirement_to_dict(req: Any) -> Dict[str, Any]:
    """Serialise a Requirement ORM object to a dict for MCP response."""
    result: Dict[str, Any] = {
        "id": str(req.id),
        "title": req.title,
        "description": req.description,
        "category": req.category,
        "status": req.status,
        "version": req.version,
    }
    if hasattr(req, "artifact") and req.artifact:
        result["workspace_id"] = str(req.artifact.workspace_id)
    return result


def _check_llm_configured() -> bool:
    """Return True if an LLM provider is configured."""
    return bool(
        os.environ.get("LLM_PROVIDER")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )


class RequirementsToolGroup(BaseToolGroup):
    """COMP-MC-003 — Requirements tool group (8 tools)."""

    _TOOL_MAP = {
        "requirement.get": "_handle_get",
        "requirement.query": "_handle_query",
        "requirement.create": "_handle_create",
        "requirement.update": "_handle_update",
        "requirement.decompose": "_handle_decompose",
        "requirement.validate": "_handle_validate",
        "requirement.derive": "_handle_derive",
        "requirement.check_consistency": "_handle_check_consistency",
        "requirement.outdate": "_handle_outdate",
        "requirement.reactivate": "_handle_reactivate",
    }
    
    _TOOL_SCHEMAS = [
        {
            "name": "requirement.get",
            "description": "Fetch a single requirement by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the requirement."}
                },
                "required": ["id"]
            }
        },
        {
            "name": "requirement.query",
            "description": "List requirements with optional workspace filter.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "include_outdated": {
                        "type": "boolean",
                        "description": "If true, include outdated (soft-deleted) requirements. Defaults to false.",
                    },
                }
            }
        },
        {
            "name": "requirement.create",
            "description": "Create a new requirement.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"}
                },
                "required": ["workspace_id", "title"]
            }
        },
        {
            "name": "requirement.update",
            "description": (
                "Update an existing requirement. Note: `status` is read-only "
                "(REQ-143) — the WorkflowEngine owns the lifecycle state; use the "
                "transitions endpoint to change it."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the requirement."},
                    # #21: fields are read from the nested `data` object by
                    # _handle_update (params["data"]), not from top-level
                    # properties — the schema previously advertised flat
                    # title/description/category/status properties that the
                    # handler silently ignored, and omitted `change_reason`
                    # entirely, making requirement.update unusable under an
                    # `extended` preset workspace (change_reason: mandatory).
                    "data": {
                        "type": "object",
                        "description": (
                            "Fields to update. `status` is READ-ONLY (REQ-143) "
                            "and ignored if present — the WorkflowEngine owns "
                            "the lifecycle state; use the transitions endpoint "
                            "instead."
                        ),
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "category": {"type": "string"},
                            "change_reason": {
                                "type": "string",
                                "description": (
                                    "Reason for the change. Required when the "
                                    "workspace's change_reason preset policy "
                                    "is 'mandatory' (e.g. extended preset)."
                                ),
                            },
                        },
                    },
                },
                "required": ["id"]
            }
        },
        {
            "name": "requirement.decompose",
            "description": "AI decomposition of a requirement.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "string", "description": "UUID of the requirement."}
                },
                "required": ["requirement_id"]
            }
        },
        {
            "name": "requirement.validate",
            "description": "AI validation of a requirement.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "string", "description": "UUID of the requirement."}
                },
                "required": ["requirement_id"]
            }
        },
        {
            "name": "requirement.derive",
            "description": "Derive a requirement.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent_requirement_id": {"type": "string", "description": "UUID of the parent requirement."},
                    "architecture_element_id": {"type": "string", "description": "UUID of the ArchitectureElement to derive onto."},
                    "title": {"type": "string", "description": "Title of the derived child requirement."},
                    "description": {"type": "string", "description": "Optional description of the derived child requirement."}
                },
                "required": ["parent_requirement_id", "architecture_element_id", "title"]
            }
        },
        {
            "name": "requirement.check_consistency",
            "description": "AI consistency check across a workspace's requirements.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."}
                },
                "required": ["workspace_id"]
            }
        },
        {
            "name": "requirement.outdate",
            "description": "Soft-delete a requirement via the workflow engine's outdate escape hatch (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the requirement."},
                    "reason": {"type": "string", "description": "Optional audit reason."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "requirement.reactivate",
            "description": "Restore an outdated requirement to its previous state (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the requirement."},
                },
                "required": ["id"],
            },
        },
    ]

    def __init__(self, service: Optional[RequirementService] = None) -> None:
        self._service = service or RequirementService()

    # ------------------------------------------------------------------
    # requirement.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.get — fetch a single requirement by UUID."""
        req_id = require_uuid(params, "id")
        try:
            req = self._service.get_requirement(req_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"requirement": _requirement_to_dict(req)})

    # ------------------------------------------------------------------
    # requirement.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.query — list requirements, optionally filtered by workspace."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for requirement.query.",
            )
        include_outdated = bool(params.get("include_outdated", False))
        try:
            reqs = self._service.list_requirements(
                workspace_id, auth_context, include_deleted=include_outdated
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({
            "requirements": [_requirement_to_dict(r) for r in reqs],
            "count": len(reqs),
        })

    # ------------------------------------------------------------------
    # requirement.create
    # ------------------------------------------------------------------

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.create — create a new requirement (write, audited)."""
        title = require_param(params, "title")
        workspace_id = require_uuid(params, "workspace_id")
        description: str = params.get("description", "")
        category: str = params.get("category", "")
        parent_id = optional_uuid(params, "parent_id")

        try:
            req = self._service.create_requirement(
                workspace_id=workspace_id,
                title=str(title),
                ctx=auth_context,
                description=description,
                category=category,
                parent_id=parent_id,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        # MCP audit entry (REQ-L2-MC-012) — ApplicationService already wrote
        # an internal audit entry; write additional MCP-specific one with
        # agent identity + api_key_hash + tool_name.
        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="Requirement",
            entity_id=req.id,
            tool_name="requirement.create",
            api_key=api_key,
        )
        return ToolResult.ok({"requirement": _requirement_to_dict(req)})

    # ------------------------------------------------------------------
    # requirement.update
    # ------------------------------------------------------------------

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.update — update an existing requirement (write, audited)."""
        req_id = require_uuid(params, "id")
        data: Dict[str, Any] = params.get("data") or {}

        try:
            req = self._service.update_requirement(
                requirement_id=req_id,
                ctx=auth_context,
                title=data.get("title"),
                description=data.get("description"),
                category=data.get("category"),
                change_reason=data.get("change_reason"),
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="Requirement",
            entity_id=req.id,
            tool_name="requirement.update",
            api_key=api_key,
        )
        return ToolResult.ok({"requirement": _requirement_to_dict(req)})

    # ------------------------------------------------------------------
    # requirement.outdate
    # ------------------------------------------------------------------

    def _handle_outdate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.outdate — soft-delete via the workflow engine (write, audited)."""
        req_id = require_uuid(params, "id")
        reason: str = params.get("reason", "")

        try:
            req = self._service.get_requirement(req_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        from workflow.services import outdate

        try:
            outdate(
                item_id=req_id,
                item_type="Requirement",
                workspace_id=req.artifact.workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="outdate",
            entity_type="Requirement",
            entity_id=req_id,
            tool_name="requirement.outdate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(req_id), "status": "outdated"})

    # ------------------------------------------------------------------
    # requirement.reactivate
    # ------------------------------------------------------------------

    def _handle_reactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.reactivate — restore a previously outdated requirement (write, audited)."""
        req_id = require_uuid(params, "id")

        try:
            req = self._service.get_requirement(req_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        from workflow.services import reactivate

        try:
            result = reactivate(
                item_id=req_id,
                item_type="Requirement",
                workspace_id=req.artifact.workspace_id,
                ctx=auth_context,
            )
        except ValueError as exc:
            return ToolResult.error("INVALID_STATE", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="reactivate",
            entity_type="Requirement",
            entity_id=req_id,
            tool_name="requirement.reactivate",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(req_id), "status": result.new_state})

    # ------------------------------------------------------------------
    # requirement.decompose
    # ------------------------------------------------------------------

    def _handle_decompose(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.decompose — AI-powered decomposition (LLM required)."""
        # ADR-L3-MC003-02: Early LLM check
        if not _check_llm_configured():
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "requirement.decompose requires an LLM provider. "
                "Set LLM_PROVIDER env variable.",
            )

        req_id = require_uuid(params, "requirement_id")

        try:
            result = self._service.decompose(
                requirement_id=req_id,
                ctx=auth_context,
            )
        except LlmNotConfiguredError:
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "LLM provider not configured for decomposition.",
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="decompose",
            entity_type="Requirement",
            entity_id=req_id,
            tool_name="requirement.decompose",
            api_key=api_key,
        )
        return ToolResult.ok({
            "parent_id": str(result.parent_id),
            "children": [
                {"id": str(c.id), "title": c.title, "description": c.description}
                for c in result.children
            ],
        })

    # ------------------------------------------------------------------
    # requirement.derive
    # ------------------------------------------------------------------

    def _handle_derive(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.derive — derive a child requirement onto a mandatory
        ArchitectureElement (single-child decomposition, no LLM required)."""
        parent_id = require_uuid(params, "parent_requirement_id")
        architecture_element_id = require_uuid(params, "architecture_element_id")
        title = require_param(params, "title")
        description: str = params.get("description", "")

        try:
            result = self._service.derive_requirement(
                parent_requirement_id=parent_id,
                architecture_element_id=architecture_element_id,
                title=str(title),
                ctx=auth_context,
                description=description,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        child = result.children[0]
        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="Requirement",
            entity_id=child.id,
            tool_name="requirement.derive",
            api_key=api_key,
        )
        return ToolResult.ok({
            "requirement": {
                "id": str(child.id),
                "title": child.title,
                "description": child.description,
            },
            "parent_requirement_id": str(result.parent_id),
            "architecture_element_id": str(architecture_element_id),
            "trace_link_ids": [str(tl_id) for tl_id in result.trace_link_ids],
        })

    # ------------------------------------------------------------------
    # requirement.check_consistency
    # ------------------------------------------------------------------

    def _handle_check_consistency(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.check_consistency — AI consistency check across a workspace.

        REQ-089: exposes the previously unreachable ``check_consistency``
        capability as a callable MCP tool. Delegates to the service, which
        forwards each requirement's title/content to the provider (REQ-046).
        Asynchronous — returns a ``task_id`` to poll via ``requirement`` status.
        """
        # ADR-L3-MC003-02: Early LLM check
        if not _check_llm_configured():
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "requirement.check_consistency requires an LLM provider. "
                "Set LLM_PROVIDER env variable.",
            )

        workspace_id = require_uuid(params, "workspace_id")

        try:
            result = self._service.check_consistency(workspace_id, auth_context)
        except LlmNotConfiguredError:
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "LLM provider not configured for consistency check.",
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="check_consistency",
            entity_type="Workspace",
            entity_id=workspace_id,
            tool_name="requirement.check_consistency",
            api_key=api_key,
        )
        return ToolResult.ok({
            "workspace_id": str(workspace_id),
            "consistency_result": result,
        })

    # ------------------------------------------------------------------
    # requirement.validate
    # ------------------------------------------------------------------

    def _handle_validate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """requirement.validate — AI-powered validation (LLM required)."""
        # ADR-L3-MC003-02: Early LLM check
        if not _check_llm_configured():
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "requirement.validate requires an LLM provider. "
                "Set LLM_PROVIDER env variable.",
            )

        req_id = require_uuid(params, "requirement_id")

        # REQ-089: route through the service's content-bearing entry point.
        # RequirementService.validate_requirement fetches the requirement and
        # forwards its title/description to the provider (REQ-046) instead of
        # this tool calling validate_artifact() with an ID only.
        try:
            validation_result = self._service.validate_requirement(
                req_id, auth_context
            )
        except LlmNotConfiguredError:
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "LLM provider not configured for validation.",
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="validate",
            entity_type="Requirement",
            entity_id=req_id,
            tool_name="requirement.validate",
            api_key=api_key,
        )
        return ToolResult.ok({
            "requirement_id": str(req_id),
            "validation_result": validation_result,
        })


__all__ = ["RequirementsToolGroup"]
