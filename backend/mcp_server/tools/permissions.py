"""
COMP-MC-008 PermissionsToolGroup — 4 item-permission MCP tools (REQ-L1-039).

leaf_id : COMP-MC-008
req_id  : REQ-L1-039 (ItemPermissionStore),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented (admin-only; write tools are audited):

  permissions.set_rule   (write)  — grant a rule (upsert)
  permissions.list       (read)   — list rules for a (user, workspace) pair
  permissions.revoke     (write)  — revoke a rule by id
  permissions.check      (read)   — evaluate the caller's effective permission

Architecture:

* The ``permissions.*`` namespace is owned by this group; there is no other
  group that handles it. The registry's prefix-based router (ADR-L3-MC002-03)
  dispatches any ``permissions.<x>`` tool to this group via the
  ``"permissions"`` prefix registered in ``tool_registry._ensure_groups``.
* All four handlers delegate to the existing :class:`ItemPermissionService`
  (the same service the REST adapter uses) and never duplicate the business
  logic. The MCP wrapper adds parameter validation, error mapping and the
  MCP-specific audit entry on write tools.
* The ``check`` tool is read-only and is callable by any authenticated
  caller; it does NOT require the admin role. The other three tools
  require admin (the service enforces the gate via
  ``ServiceBase._assert_permission(ctx, "admin")``).
* ``set_rule`` and ``revoke`` are added to ``_WRITE_TOOL_PREFIXES`` in
  ``tool_registry`` so the RBAC layer treats them as writes.

Error mapping (REQ-L2-MC-011):
  NotFoundError           -> NOT_FOUND
  PermissionDeniedError   -> PERMISSION_DENIED
  ValidationError / ValueError / ParameterError -> VALIDATION_ERROR
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

from auth_tenancy.models import ItemPermission
from auth_tenancy.services import ItemPermissionService

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    optional_uuid,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _permission_to_dict(perm: ItemPermission) -> Dict[str, Any]:
    """Serialise an ItemPermission row to a JSON-safe dict."""
    return {
        "id": str(perm.id),
        "user_id": str(perm.user_id),
        "workspace_id": str(perm.workspace_id),
        "artifact_id": str(perm.artifact_id) if perm.artifact_id else None,
        "permission_level": perm.permission_level,
        "granted_by": str(perm.granted_by_id) if perm.granted_by_id else None,
    }


# ---------------------------------------------------------------------------
# PermissionsToolGroup
# ---------------------------------------------------------------------------


class PermissionsToolGroup(BaseToolGroup):
    """COMP-MC-008 — Item-permission MCP tool group (4 tools)."""

    _TOOL_MAP = {
        "permissions.set_rule": "_handle_set_rule",
        "permissions.list": "_handle_list",
        "permissions.revoke": "_handle_revoke",
        "permissions.check": "_handle_check",
    }

    def __init__(self, service: Optional[ItemPermissionService] = None) -> None:
        self._service = service or ItemPermissionService()

    # ------------------------------------------------------------------
    # permissions.set_rule (write)
    # ------------------------------------------------------------------

    def _handle_set_rule(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """permissions.set_rule — grant or upsert a permission rule (REQ-L1-039).

        Required params:
            workspace_id: UUID of the target workspace.
            user_id:      UUID of the user receiving the rule.
            permission_level: one of "read" | "write" | "none".

        Optional:
            artifact_id: UUID of the specific artifact; omit for a
                workspace-wide default rule.
        """
        workspace_id = require_uuid(params, "workspace_id")
        user_id = require_uuid(params, "user_id")
        level = params.get("permission_level")
        if not isinstance(level, str) or not level.strip():
            raise ParameterError(
                "Required parameter 'permission_level' is missing or empty."
            )
        artifact_id = optional_uuid(params, "artifact_id")

        try:
            permission = self._service.grant_permission(
                auth_context,
                user_id=user_id,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                level=level.strip().lower(),
                granted_by_user_id=auth_context.user_id,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="permissions.set_rule",
            entity_type="ItemPermission",
            entity_id=permission.id,
            tool_name="permissions.set_rule",
            api_key=api_key,
            details={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "artifact_id": str(artifact_id) if artifact_id else None,
                "permission_level": level,
            },
        )
        return ToolResult.ok({"permission": _permission_to_dict(permission)})

    # ------------------------------------------------------------------
    # permissions.list (read)
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """permissions.list — list rules for a (user, workspace) pair.

        Required params:
            workspace_id: UUID of the target workspace.
            user_id:      UUID of the user whose rules to list.

        Optional:
            artifact_id: filter to a specific artifact (post-fetch, admin).
        """
        workspace_id = require_uuid(params, "workspace_id")
        user_id = require_uuid(params, "user_id")
        artifact_filter = optional_uuid(params, "artifact_id")

        try:
            rules = self._service.list_permissions(
                auth_context,
                user_id=user_id,
                workspace_id=workspace_id,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if artifact_filter is not None:
            rules = [r for r in rules if r.artifact_id == artifact_filter]

        return ToolResult.ok(
            {"permissions": [_permission_to_dict(r) for r in rules]}
        )

    # ------------------------------------------------------------------
    # permissions.revoke (write)
    # ------------------------------------------------------------------

    def _handle_revoke(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """permissions.revoke — revoke a permission rule by id (REQ-L1-039).

        Required params:
            permission_id: UUID of the row to delete.

        Note: like the REST adapter, the service signature uses a
        (user, workspace, artifact) triple. We look up the row here by id
        (under the unscoped manager) and forward the triple, so the
        service signature stays RBAC-clean.
        """
        permission_id = require_uuid(params, "permission_id")

        perm = (
            ItemPermission.unscoped
            .filter(id=permission_id)
            .first()
        )
        if perm is None:
            return ToolResult.error(
                "NOT_FOUND",
                f"ItemPermission with id {permission_id!r} not found.",
            )

        try:
            deleted = self._service.revoke_permission(
                auth_context,
                user_id=perm.user_id,
                workspace_id=perm.workspace_id,
                artifact_id=perm.artifact_id,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if not deleted:
            return ToolResult.error(
                "NOT_FOUND",
                f"ItemPermission with id {permission_id!r} not found.",
            )

        write_mcp_audit(
            ctx=auth_context,
            operation="permissions.revoke",
            entity_type="ItemPermission",
            entity_id=UUID(str(permission_id)),
            tool_name="permissions.revoke",
            api_key=api_key,
            details={
                "user_id": str(perm.user_id),
                "workspace_id": str(perm.workspace_id),
                "artifact_id": str(perm.artifact_id) if perm.artifact_id else None,
            },
        )
        return ToolResult.ok(
            {"revoked": True, "permission_id": str(permission_id)}
        )

    # ------------------------------------------------------------------
    # permissions.check (read)
    # ------------------------------------------------------------------

    def _handle_check(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """permissions.check — evaluate the caller's effective permission.

        Required params:
            workspace_id:     UUID of the target workspace.
            permission_level: the level being queried — "read" or "write".
                              Determines what "is_allowed" means for the
                              caller (it is True if the effective decision
                              is at least as strong as the queried level).

        Optional:
            artifact_id: UUID of the specific artifact; omit for a
                workspace-wide check.
        """
        workspace_id = require_uuid(params, "workspace_id")
        level_raw = params.get("permission_level")
        if not isinstance(level_raw, str) or not level_raw.strip():
            raise ParameterError(
                "Required parameter 'permission_level' is missing or empty."
            )
        level = level_raw.strip().lower()
        if level not in ("read", "write"):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Field 'permission_level' must be 'read' or 'write'.",
            )
        artifact_id = optional_uuid(params, "artifact_id")

        try:
            decision = self._service.check_permission(
                user_id=auth_context.user_id,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        # "is_allowed" semantics: True iff the effective decision is at
        # least as strong as the queried level. write >= read >= deny.
        is_allowed = (
            decision.level == level
            or (level == "read" and decision.level == "write")
        )

        return ToolResult.ok(
            {
                "decision": {
                    "level": decision.level,
                    "reason": decision.reason,
                    "is_allowed": is_allowed,
                },
                "queried_level": level,
            }
        )


__all__ = ["PermissionsToolGroup"]
