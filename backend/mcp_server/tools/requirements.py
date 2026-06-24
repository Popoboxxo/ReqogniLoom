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
from uuid import UUID

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
    ParameterError,
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
    """COMP-MC-003 — Requirements tool group (6 tools)."""

    _TOOL_MAP = {
        "requirement.get": "_handle_get",
        "requirement.query": "_handle_query",
        "requirement.create": "_handle_create",
        "requirement.update": "_handle_update",
        "requirement.decompose": "_handle_decompose",
        "requirement.validate": "_handle_validate",
    }

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
        try:
            reqs = self._service.list_requirements(workspace_id, auth_context)
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

        # ApplicationService does not yet expose a standalone validate method.
        # Delegate to LlmAdapter directly if available, else raise configured error.
        try:
            from llm_adapter.services import validate_artifact  # type: ignore[import]

            validation_result = validate_artifact(str(req_id), ctx=auth_context)
        except ImportError:
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "LLM adapter not installed. Cannot validate requirement.",
            )
        except LlmNotConfiguredError:
            return ToolResult.error(
                "LLM_NOT_CONFIGURED",
                "LLM provider not configured for validation.",
            )
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
            "validation_result": validation_result if isinstance(validation_result, dict)
            else {"result": str(validation_result)},
        })


__all__ = ["RequirementsToolGroup"]
