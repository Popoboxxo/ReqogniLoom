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
* ``check`` combines TWO layers (fix #716): the base RBAC matrix
  (:class:`~auth_tenancy.services.AuthorizationService`) and the item-level
  override (:class:`ItemPermissionService`). Previously it answered using
  ONLY the item-level layer, which closed-world-defaults to "deny" when no
  explicit :class:`~auth_tenancy.models.ItemPermission` row exists — making
  a plain Viewer with zero item-level rules look permanently denied even
  though the RBAC matrix already grants them ``read``. See
  :meth:`PermissionsToolGroup._handle_check` for the combination rule.
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
from auth_tenancy.services import (
    NO_RULE_REASON,
    AuthorizationService,
    ItemPermissionService,
    Operation,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    mcp_audit_handoff,
    optional_uuid,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


# Ordering for combining the RBAC and item-level permission layers in
# ``_handle_check`` (fix #716): higher rank = more permissive. Per
# ``auth_tenancy.services.item_permission``'s module docstring, an item-level
# rule "cannot broaden what RBAC already permits — it can only further
# restrict at the item level", so the combined/effective level is always the
# LOWER-ranked (more restrictive) of the two when an explicit item rule
# exists.
_LEVEL_RANK: Dict[str, int] = {"deny": 0, "read": 1, "write": 2}


def _more_restrictive_level(level_a: str, level_b: str) -> str:
    """Return whichever of two permission levels ranks lower (more restrictive)."""
    return level_a if _LEVEL_RANK[level_a] <= _LEVEL_RANK[level_b] else level_b


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

    _TOOL_SCHEMAS = [
        {
            "name": "permissions.set_rule",
            "description": "Grant or upsert an item-permission rule (admin-only, write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "user_id": {"type": "string", "description": "UUID of the user receiving the rule."},
                    "permission_level": {
                        "type": "string",
                        "enum": ["read", "write", "none"],
                        "description": "Permission level to grant.",
                    },
                    "artifact_id": {
                        "type": "string",
                        "description": "Optional artifact UUID; omit for a workspace-wide default rule.",
                    },
                },
                "required": ["workspace_id", "user_id", "permission_level"],
            },
        },
        {
            "name": "permissions.list",
            "description": "List permission rules for a (user, workspace) pair (admin-only, read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "user_id": {"type": "string", "description": "UUID of the user."},
                    "artifact_id": {
                        "type": "string",
                        "description": "Optional artifact UUID to filter on.",
                    },
                },
                "required": ["workspace_id", "user_id"],
            },
        },
        {
            "name": "permissions.revoke",
            "description": "Revoke a permission rule by its ID (admin-only, write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "permission_id": {
                        "type": "string",
                        "description": "UUID of the permission row to delete.",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace the permission row belongs to. "
                            "Required so the admin-role check is narrowed to this "
                            "workspace specifically (ToolRegistry resolves "
                            "workspace-scoped roles from this param) — without it "
                            "the check falls back to a tenant-wide role aggregate, "
                            "letting an admin of any one workspace revoke rules in "
                            "any other workspace of the same tenant."
                        ),
                    },
                },
                "required": ["permission_id", "workspace_id"],
            },
        },
        {
            "name": "permissions.check",
            "description": "Evaluate the caller's effective permission (read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "permission_level": {
                        "type": "string",
                        "enum": ["read", "write"],
                        "description": "Permission level being queried.",
                    },
                    "artifact_id": {
                        "type": "string",
                        "description": "Optional artifact UUID; omit for a workspace-wide check.",
                    },
                },
                "required": ["workspace_id", "permission_level"],
            },
        },
    ]

    def __init__(
        self,
        service: Optional[ItemPermissionService] = None,
        authz_service: Optional[AuthorizationService] = None,
    ) -> None:
        self._service = service or ItemPermissionService()
        self._authz_service = authz_service or AuthorizationService()

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
            # Codeberg #313: suppress grant_permission's single internal
            # _audit() call for the same entity — write_mcp_audit below is
            # the sole entry.
            with mcp_audit_handoff():
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
            workspace_id: UUID of the workspace the row belongs to — also
                narrows the admin-role check to that workspace (see the
                schema's own description for why this is security-relevant,
                not just a filter convenience).

        Note: like the REST adapter, the service signature uses a
        (user, workspace, artifact) triple. We look up the row here by id
        (under the unscoped manager, explicitly filtered by tenant AND the
        caller-supplied workspace_id — code review finding: previously
        neither filter was applied, so this lookup could return another
        tenant's row entirely, in addition to the workspace-scoping gap
        described above) and forward the triple, so the service signature
        stays RBAC-clean.
        """
        permission_id = require_uuid(params, "permission_id")
        workspace_id = require_uuid(params, "workspace_id")

        perm = (
            ItemPermission.unscoped
            .filter(
                id=permission_id,
                tenant_id=auth_context.tenant_id,
                workspace_id=workspace_id,
            )
            .first()
        )
        if perm is None:
            return ToolResult.error(
                "NOT_FOUND",
                f"ItemPermission with id {permission_id!r} not found.",
            )

        try:
            # Codeberg #313: suppress revoke_permission's single internal
            # _audit() call for the same entity — write_mcp_audit below is
            # the sole entry.
            with mcp_audit_handoff():
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

        Fix #716: the effective decision combines two layers instead of
        answering from the item-level layer alone:

        1. Base RBAC (:meth:`AuthorizationService.decide_access`) — the
           Admin/Editor/Viewer/Approver matrix that the rest of the system
           (REST ``RbacPermission``, MCP write-gates) actually enforces.
        2. Item-level override (:meth:`ItemPermissionService.check_permission`)
           — an OPT-IN, admin-granted per-artifact/per-workspace rule.

        Per :mod:`auth_tenancy.services.item_permission`'s module docstring,
        an item-level rule "cannot broaden what RBAC already permits — it
        can only further restrict at the item level":

        - No explicit item rule exists for this caller (the service's own
          closed-world default, :data:`NO_RULE_REASON`) -> the item layer is
          silent and the base RBAC decision governs alone. This is the fix:
          previously ANY caller without an item-level row was reported as
          "deny", even one whose role already grants the queried level.
        - An explicit item rule exists (artifact- or workspace-scoped,
          including an explicit "none"/deny override) -> the effective level
          is the more restrictive of the two, never more permissive than
          RBAC (so an explicit deny rule, or a rule below the caller's RBAC
          level, still correctly restricts access; a rule ABOVE the
          caller's RBAC level cannot escalate it).
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
            item_decision = self._service.check_permission(
                user_id=auth_context.user_id,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        read_decision = self._authz_service.decide_access(
            auth_context.active_roles, Operation.READ
        )
        write_decision = self._authz_service.decide_access(
            auth_context.active_roles, Operation.WRITE
        )
        if write_decision.allow:
            rbac_level, rbac_reason = "write", write_decision.decision_reason
        elif read_decision.allow:
            rbac_level, rbac_reason = "read", read_decision.decision_reason
        else:
            rbac_level, rbac_reason = "deny", read_decision.decision_reason

        if item_decision.reason == NO_RULE_REASON:
            effective_level, effective_reason = rbac_level, rbac_reason
        else:
            effective_level = _more_restrictive_level(
                rbac_level, item_decision.level
            )
            effective_reason = (
                item_decision.reason
                if effective_level == item_decision.level
                else rbac_reason
            )

        # "is_allowed" semantics: True iff the effective decision is at
        # least as strong as the queried level. write >= read >= deny.
        is_allowed = (
            effective_level == level
            or (level == "read" and effective_level == "write")
        )

        return ToolResult.ok(
            {
                "decision": {
                    "level": effective_level,
                    "reason": effective_reason,
                    "is_allowed": is_allowed,
                },
                "queried_level": level,
            }
        )


__all__ = ["PermissionsToolGroup"]
