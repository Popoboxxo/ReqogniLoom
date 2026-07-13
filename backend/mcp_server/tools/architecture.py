"""
COMP-MC-004 ArchitectureToolGroup — 5 architecture.* MCP tools.

leaf_id : COMP-MC-004
req_id  : REQ-L2-MC-002 (5 Architecture Tools),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented:
  architecture.get      — fetch single ArchitectureElement by ID
  architecture.query    — list ArchitectureElements with optional workspace filter
  architecture.create   — create a new ArchitectureElement (write, audited)
  architecture.update   — update an ArchitectureElement (write, audited)
  architecture.link     — create a TraceLink between arch element and target (write, audited)

Interface contracts implemented:
  IF-MC-INT-003  — inbound: execute_tool(tool_name, params, auth_context) -> ToolResult
  IF-MC-EXT-OUT-003 — outbound: ApplicationService (ArchitectureService, TraceLinkService)

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-004_ArchitectureToolGroup/
      L3_COMP-MC-004_ArchitectureToolGroup_Architecture.md

ADR-L3-MC004-01: TraceLink via separate create_trace_link call.
ADR-L3-MC004-02: Dedicated handler method per tool.
ADR-L3-MC004-03: link_type validated against VALID_LINK_TYPES before service call.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.services import (
    ArchitectureService,
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    TraceLinkService,
    ValidationError,
    VALID_LINK_TYPES,
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


def _arch_el_to_dict(el: Any) -> Dict[str, Any]:
    """Serialise an ArchitectureElement ORM object to a dict."""
    result: Dict[str, Any] = {
        "id": str(el.id),
        "title": el.title,
        "description": el.description,
        "element_type": el.element_type,
        "version": el.version,
    }
    if hasattr(el, "artifact") and el.artifact:
        result["workspace_id"] = str(el.artifact.workspace_id)
    return result


class ArchitectureToolGroup(BaseToolGroup):
    """COMP-MC-004 — Architecture tool group (5 tools)."""

    _TOOL_MAP = {
        "architecture.get": "_handle_get",
        "architecture.query": "_handle_query",
        "architecture.create": "_handle_create",
        "architecture.update": "_handle_update",
        "architecture.link": "_handle_link",
    }

    def __init__(
        self,
        service: Optional[ArchitectureService] = None,
        trace_service: Optional[TraceLinkService] = None,
    ) -> None:
        self._service = service or ArchitectureService()
        self._trace_service = trace_service or TraceLinkService()

    # ------------------------------------------------------------------
    # architecture.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.get — fetch a single ArchitectureElement by UUID."""
        arch_id = require_uuid(params, "id")
        try:
            el = self._service.get_architecture_element(arch_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"architecture_element": _arch_el_to_dict(el)})

    # ------------------------------------------------------------------
    # architecture.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.query — list ArchitectureElements by workspace."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for architecture.query.",
            )
        try:
            elements = self._service.list_architecture_elements(workspace_id, auth_context)
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({
            "architecture_elements": [_arch_el_to_dict(el) for el in elements],
            "count": len(elements),
        })

    # ------------------------------------------------------------------
    # architecture.create
    # ------------------------------------------------------------------

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.create — create a new ArchitectureElement (write, audited)."""
        title = require_param(params, "title")
        workspace_id = require_uuid(params, "workspace_id")
        description: str = params.get("description", "")
        element_type: str = params.get("element_type", "component")

        try:
            el = self._service.create_architecture_element(
                workspace_id=workspace_id,
                title=str(title),
                ctx=auth_context,
                description=description,
                element_type=element_type,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="ArchitectureElement",
            entity_id=el.id,
            tool_name="architecture.create",
            api_key=api_key,
        )
        return ToolResult.ok({"architecture_element": _arch_el_to_dict(el)})

    # ------------------------------------------------------------------
    # architecture.update
    # ------------------------------------------------------------------

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.update — update an ArchitectureElement (write, audited)."""
        arch_id = require_uuid(params, "id")
        data: Dict[str, Any] = params.get("data") or {}
        # expected_version is required for optimistic locking
        expected_version = data.get("expected_version") or params.get("expected_version")
        if expected_version is None:
            expected_version = 1  # fallback for agents not tracking versions

        try:
            expected_version = int(expected_version)
        except (TypeError, ValueError):
            return ToolResult.error("VALIDATION_ERROR", "'expected_version' must be an integer.")

        try:
            el = self._service.update_architecture_element(
                arch_el_id=arch_id,
                ctx=auth_context,
                expected_version=expected_version,
                title=data.get("title"),
                description=data.get("description"),
                element_type=data.get("element_type"),
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except OptimisticLockError as exc:
            return ToolResult.error("VALIDATION_ERROR", f"Version conflict: {exc}")
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="ArchitectureElement",
            entity_id=el.id,
            tool_name="architecture.update",
            api_key=api_key,
        )
        return ToolResult.ok({"architecture_element": _arch_el_to_dict(el)})

    # ------------------------------------------------------------------
    # architecture.link
    # ------------------------------------------------------------------

    def _handle_link(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """architecture.link — create TraceLink between arch element and target.

        ADR-L3-MC004-01: TraceLink is created via TraceLinkService, not as
        an update to ArchitectureElement itself.
        ADR-L3-MC004-03: link_type validated against VALID_LINK_TYPES.
        """
        arch_id = require_uuid(params, "arch_id")
        target_id = require_uuid(params, "target_id")
        link_type = require_param(params, "link_type")

        # Validate link_type (ADR-L3-MC004-03)
        if link_type not in VALID_LINK_TYPES:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Invalid link_type '{link_type}'. Valid types: {sorted(VALID_LINK_TYPES)}",
            )

        try:
            trace_link = self._trace_service.create_trace_link(
                source_id=arch_id,
                target_id=target_id,
                link_type=link_type,
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        trace_link_id = str(trace_link.id) if hasattr(trace_link, "id") else str(arch_id)

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="TraceLink",
            entity_id=UUID(trace_link_id),
            tool_name="architecture.link",
            api_key=api_key,
            details={
                "source_id": str(arch_id),
                "target_id": str(target_id),
                "link_type": link_type,
            },
        )
        return ToolResult.ok({
            "trace_link": {
                "id": trace_link_id,
                "source_id": str(arch_id),
                "target_id": str(target_id),
                "link_type": link_type,
            }
        })


__all__ = ["ArchitectureToolGroup"]
