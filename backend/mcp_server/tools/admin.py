"""
COMP-MC-007 AdminToolGroup — 3 workspace lifecycle MCP tools (REQ-L1-042).

leaf_id : COMP-MC-007
req_id  : REQ-L1-042 (Workspace-Lifecycle MCP-Wrapper),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented (admin-only, write, audited):
  workspace.close       — soft-delete a workspace (is_active=False)
  workspace.reactivate  — undo a soft-delete
  workspace.delete      — hard-delete with captcha confirmation

Architecture:
- Tools use the ``workspace.*`` namespace, sharing the prefix with the
  existing ``workspace.get_context`` tool owned by ``CrossCuttingToolGroup``.
- To avoid breaking ``workspace.get_context`` while still routing lifecycle
  tools here, ``AdminToolGroup`` is registered under the ``workspace``
  prefix in ``tool_registry._ensure_groups()`` and forwards non-handled
  tool names to a wrapped ``CrossCuttingToolGroup`` instance (fallthrough).
- All three handlers delegate to the existing ``WorkspaceService``
  lifecycle methods (``close_workspace``, ``reactivate_workspace``,
  ``delete_workspace``) and never duplicate the business logic
  (transaction wrapping, audit hooks, cascade order, captcha check).

ADR-L3-MC007-01: Reuse ``WorkspaceService`` strictly — MCP wrapper is a
  thin handler that adds parameter validation, error mapping and the
  MCP-specific audit log entry.
ADR-L3-MC007-02: ``workspace.*`` namespace shared with ``CrossCuttingToolGroup``
  via prefix fallthrough (this group owns lifecycle tools, the wrapped
  group owns ``workspace.get_context``).
ADR-L3-MC007-03: Hard-delete requires the same captcha confirmation text
  as the REST API; the check happens inside ``WorkspaceService.delete_workspace``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.services import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    WorkspaceService,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    require_param,
    require_uuid,
    write_mcp_audit,
)
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

logger = logging.getLogger(__name__)


def _workspace_to_dict(workspace: Any) -> Dict[str, Any]:
    """Serialise a Workspace ORM object to a dict for MCP response.

    Only fields that are stable across the workspace lifecycle are returned;
    the wrapper intentionally does not leak internal columns.
    """
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "is_active": bool(workspace.is_active),
        "closed_at": (
            workspace.closed_at.isoformat()
            if getattr(workspace, "closed_at", None) is not None
            else None
        ),
        "closed_by": (
            str(workspace.closed_by_id)
            if getattr(workspace, "closed_by_id", None) is not None
            else None
        ),
    }


class AdminToolGroup(BaseToolGroup):
    """COMP-MC-007 — Workspace-lifecycle admin tool group (3 tools).

    All three tools are admin-only write operations. The underlying
    ``WorkspaceService`` enforces the admin role and writes an
    ``AuditLogEntry``; the MCP layer additionally writes an MCP-specific
    audit entry with the agent identity and api-key hash
    (REQ-L2-MC-012).
    """

    _TOOL_MAP = {
        "workspace.close": "_handle_close",
        "workspace.reactivate": "_handle_reactivate",
        "workspace.delete": "_handle_delete",
    }

    def __init__(
        self,
        service: Optional[WorkspaceService] = None,
        cross_cutting: Optional[CrossCuttingToolGroup] = None,
    ) -> None:
        self._service = service or WorkspaceService()
        # Wrapped read-side group for fallthrough (e.g. workspace.get_context)
        self._cross_cutting = cross_cutting or CrossCuttingToolGroup()

    # ------------------------------------------------------------------
    # Dispatcher override (ADR-L3-MC007-02)
    # ------------------------------------------------------------------

    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        auth_context: AuthContext,
        api_key: str,
    ) -> ToolResult:
        """Dispatch *tool_name* to the lifecycle handler or fall through.

        Tools present in ``_TOOL_MAP`` are handled directly. Any other
        ``workspace.*`` tool is forwarded to the wrapped
        ``CrossCuttingToolGroup`` so that read-only tools like
        ``workspace.get_context`` keep working without a second registry
        entry.
        """
        if tool_name in self._TOOL_MAP:
            return super().execute_tool(
                tool_name=tool_name,
                params=params,
                auth_context=auth_context,
                api_key=api_key,
            )
        # Fallthrough for shared namespace
        return self._cross_cutting.execute_tool(
            tool_name=tool_name,
            params=params,
            auth_context=auth_context,
            api_key=api_key,
        )

    # ------------------------------------------------------------------
    # workspace.close
    # ------------------------------------------------------------------

    def _handle_close(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """workspace.close — soft-delete a workspace (REQ-L1-042).

        Sets ``is_active=False`` and records ``closed_at``/``closed_by``.
        Data is preserved; the workspace can be reactivated later.
        Requires admin role — enforced inside ``WorkspaceService``.
        """
        workspace_id = require_uuid(params, "workspace_id")

        try:
            workspace = self._service.close_workspace(workspace_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="workspace.close",
            entity_type="Workspace",
            entity_id=workspace.id,
            tool_name="workspace.close",
            api_key=api_key,
        )
        return ToolResult.ok({"workspace": _workspace_to_dict(workspace)})

    # ------------------------------------------------------------------
    # workspace.reactivate
    # ------------------------------------------------------------------

    def _handle_reactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """workspace.reactivate — undo a workspace close (REQ-L1-042).

        Sets ``is_active=True`` and clears ``closed_at``/``closed_by``.
        Requires admin role — enforced inside ``WorkspaceService``.
        """
        workspace_id = require_uuid(params, "workspace_id")

        try:
            workspace = self._service.reactivate_workspace(workspace_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="workspace.reactivate",
            entity_type="Workspace",
            entity_id=workspace.id,
            tool_name="workspace.reactivate",
            api_key=api_key,
        )
        return ToolResult.ok({"workspace": _workspace_to_dict(workspace)})

    # ------------------------------------------------------------------
    # workspace.delete
    # ------------------------------------------------------------------

    def _handle_delete(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """workspace.delete — hard-delete a workspace (REQ-L1-042).

        Requires ``confirmation_text`` to match the workspace name
        (case-sensitive) — the captcha check happens inside
        ``WorkspaceService.delete_workspace``. The MCP wrapper does NOT
        duplicate the validation; it only forwards the parameter.
        """
        workspace_id = require_uuid(params, "workspace_id")
        confirmation_text = require_param(params, "confirmation_text")

        try:
            self._service.delete_workspace(
                workspace_id=workspace_id,
                confirmation_text=str(confirmation_text),
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="workspace.delete",
            entity_type="Workspace",
            entity_id=UUID(str(workspace_id)),
            tool_name="workspace.delete",
            api_key=api_key,
        )
        return ToolResult.ok(
            {"deleted": True, "workspace_id": str(workspace_id)}
        )


__all__ = ["AdminToolGroup"]
