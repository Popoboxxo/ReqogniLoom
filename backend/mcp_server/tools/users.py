"""
COMP-MC-011 UsersToolGroup — 4 admin user-management MCP tools (REQ-L1-046).

leaf_id : COMP-MC-011
req_id  : REQ-L1-046 (admin umbrella — user management is an admin operation),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-011 (structured error response),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented (admin-only; write tools are audited):

  user.create        (write)  — create a new user
  user.assign_role   (write)  — assign a role to an existing user in a workspace
  user.list          (read)   — list users (tenant-scoped)
  user.deactivate    (write)  — deactivate a user (is_active=False)

Architecture
------------
* The ``user.*`` namespace is owned by this group; no other group handles
  it. The prefix-based router (ADR-L3-MC002-03) dispatches any
  ``user.<x>`` tool to this group via the ``"user"`` prefix registered in
  ``tool_registry._ensure_groups()``.

* Admin role enforcement: each handler checks
  ``auth_context.has_role("admin")`` at the very top. The check returns a
  ``PERMISSION_DENIED`` ``ToolResult`` directly so the caller never sees a
  DB round-trip or a stack trace.

* ``user.assign_role`` delegates to ``AuthorizationService.assign_role``
  (COMP-AT-002) for the actual role-assignment logic; the wrapper adds
  parameter validation, error mapping and the MCP-level audit entry. No
  business logic is duplicated.

* ``user.create`` writes a new ``persistence.User`` row directly. There is
  no existing user-creation service in the codebase (verified at
  implementation time — only ``User.objects.create`` call sites in tests
  and the ``seed_demo`` management command), so the handler uses the same
  ``User.objects.create`` + ``set_password`` + ``save`` pattern. This is
  consistent with the seed flow and the existing tests.

* ``user.deactivate`` uses the simple MVP path: ``is_active=False``. It
  does NOT call ``AuthorizationService.suspend_approver_assignments`` per
  workspace, because (a) that operation is workspace-scoped and the
  handler does not have a workspace_id, and (b) suspending approver
  assignments in every workspace the user touches is a destructive
  side-effect that the caller should opt into explicitly. Future
  enhancement: a separate workspace-scoped tool that suspends a user's
  approver assignments.

* ``user.list`` queries the ``User`` model directly. ``User`` does NOT
  inherit from ``TenantScopedModel`` (membership in a tenant is
  optional), so the query does not require a tenant context. The handler
  filters by ``tenant_id`` (default = ``auth_context.tenant_id``) and
  applies the optional ``is_active`` filter and the page-size limit.

Error mapping (REQ-L2-MC-011):
  NotFoundError           -> NOT_FOUND
  PermissionDeniedError   -> PERMISSION_DENIED
  ValidationError / ValueError / ParameterError -> VALIDATION_ERROR

Parameters accepted by ``user.create``:
    username : unique username (required)
    email    : unique email    (required)
    password : password, >= 8 chars (required; hashed via Django hasher)
    role     : initial role name (optional, default "viewer"; informational,
               the role is NOT auto-assigned to a workspace — caller must
               use ``user.assign_role`` to grant workspace access)
    preset   : active preset (optional, default "basic"; reserved for
               future use, currently NOT enforced because the user is
               not yet a member of any workspace at creation time)

Parameters accepted by ``user.assign_role``:
    user_id     : UUID of the target user         (required)
    workspace_id: UUID of the target workspace    (required)
    role        : role to assign (admin/editor/viewer/approver) (required)
    preset      : active workspace preset (required, gates Approver)

Parameters accepted by ``user.list``:
    tenant_id : UUID of the tenant to scope to (optional,
                defaults to auth_context.tenant_id)
    is_active : bool filter; if None, returns both (optional)
    limit     : page size, 1..500, default 100 (optional)

Parameters accepted by ``user.deactivate``:
    user_id : UUID of the user to deactivate (required)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from auth_tenancy.services import AuthorizationService

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

from persistence.models import Tenant, User
from persistence.tenancy import TenantContext

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
# Constants
# ---------------------------------------------------------------------------

_VALID_ROLES = frozenset(
    {ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, ROLE_APPROVER}
)

_LIST_MAX_LIMIT: int = 500
_LIST_DEFAULT_LIMIT: int = 100

# Minimum password length. Django's default validators allow shorter
# passwords; we tighten this for the MCP admin tool because the
# user-creation path is privileged and must enforce sane defaults.
_PASSWORD_MIN_LENGTH: int = 8


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _user_to_dict(user: User) -> Dict[str, Any]:
    """Serialise a User ORM object to a JSON-safe dict.

    Never includes the password hash; the MCP response must not leak
    credential material even to the admin caller.
    """
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "created_at": (
            user.created_at.isoformat()
            if getattr(user, "created_at", None) is not None
            else None
        ),
    }


def _normalize_role(raw: Any) -> str:
    """Return a normalised role string or raise ParameterError.

    Empty / non-string values become a ParameterError. Unknown role
    names also become a ParameterError.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ParameterError(
            "Parameter 'role' must be a non-empty string."
        )
    normalized = raw.strip().lower()
    if normalized not in _VALID_ROLES:
        raise ParameterError(
            f"Parameter 'role' must be one of {sorted(_VALID_ROLES)}, "
            f"got {raw!r}."
        )
    return normalized


# ---------------------------------------------------------------------------
# UsersToolGroup
# ---------------------------------------------------------------------------


class UsersToolGroup(BaseToolGroup):
    """COMP-MC-011 — User-management MCP tool group (4 tools, admin-only)."""

    _TOOL_MAP = {
        "user.create": "_handle_user_create",
        "user.assign_role": "_handle_user_assign_role",
        "user.list": "_handle_user_list",
        "user.deactivate": "_handle_user_deactivate",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "user.create",
            "description": "Create a new user (admin-only, write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Unique username."},
                    "email": {"type": "string", "description": "Unique email address."},
                    "password": {"type": "string", "description": "Password, at least 8 characters."},
                    "role": {
                        "type": "string",
                        "description": "Informational initial role hint (default 'viewer').",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Informational active preset hint (default 'basic').",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Optional tenant UUID (superuser callers only).",
                    },
                },
                "required": ["username", "email", "password"],
            },
        },
        {
            "name": "user.assign_role",
            "description": "Assign a role to a user in a workspace (admin-only, write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the target user."},
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "role": {
                        "type": "string",
                        "enum": ["admin", "editor", "viewer", "approver"],
                        "description": "Role to assign.",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Active workspace preset (gates the approver role).",
                    },
                },
                "required": ["user_id", "workspace_id", "role", "preset"],
            },
        },
        {
            "name": "user.list",
            "description": "List users, tenant-scoped (admin-only, read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tenant_id": {
                        "type": "string",
                        "description": "Optional tenant UUID (defaults to caller's tenant).",
                    },
                    "is_active": {
                        "type": "boolean",
                        "description": "Optional active-state filter; omit to return both.",
                    },
                    "limit": {"type": "integer", "description": "Page size (1..500, default 100)."},
                },
            },
        },
        {
            "name": "user.deactivate",
            "description": "Deactivate a user (is_active=False), admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the user to deactivate."},
                },
                "required": ["user_id"],
            },
        },
    ]

    def __init__(
        self, authz_service: Optional[AuthorizationService] = None
    ) -> None:
        self._authz_service = authz_service or AuthorizationService()

    # ------------------------------------------------------------------
    # Common admin gate
    # ------------------------------------------------------------------

    @staticmethod
    def _check_admin(auth_context: AuthContext) -> Optional[ToolResult]:
        """Return a ``PERMISSION_DENIED`` ToolResult if the caller is not admin.

        Returns ``None`` when the caller has the admin role (i.e. the
        gate is open). The result is intentionally a ``ToolResult`` (not
        an exception) because the ``BaseToolGroup.execute_tool``
        dispatcher only maps ``ParameterError`` -> ``VALIDATION_ERROR``;
        anything else falls through to ``INTERNAL_ERROR``. Returning a
        ``ToolResult`` keeps the MCP response clean.
        """
        if auth_context.has_role("admin"):
            return None
        return ToolResult.error(
            "PERMISSION_DENIED",
            f"Permission denied: role 'admin' required, "
            f"user has {auth_context.active_roles}",
        )

    @staticmethod
    def _caller_is_superuser(user_id: UUID) -> bool:
        """Return whether the calling user is a Django superuser.

        Used to allow a platform-level admin to create users in any
        tenant by passing an explicit ``tenant_id`` instead of having it
        auto-injected from the auth context.
        """
        try:
            user = User.objects.filter(id=user_id).first()
        except Exception:
            return False
        return bool(user and user.is_superuser)

    # ------------------------------------------------------------------
    # user.create (write, audited)
    # ------------------------------------------------------------------

    def _handle_user_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.create — create a new user (admin-only, write).

        Required params:
            username : unique username.
            email    : unique email.
            password : password, >= 8 chars (hashed via Django's default hasher).

        Optional:
            role   : informational, default "viewer". NOTE: this is
                     stored as a hint only; the role is NOT auto-assigned
                     to any workspace. Use ``user.assign_role`` for that.
            preset : informational, default "basic". Reserved for
                     future use.

        Behaviour:
            - tenant is auto-set to ``auth_context.tenant_id`` unless the
              caller is a Django superuser, in which case ``tenant_id``
              must be supplied explicitly.
            - the user row is created with ``is_active=True``.
            - an audit entry is written via ``write_mcp_audit``.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        username = params.get("username")
        if not isinstance(username, str) or not username.strip():
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Required parameter 'username' is missing or empty.",
            )
        username = username.strip()

        email = params.get("email")
        if not isinstance(email, str) or not email.strip():
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Required parameter 'email' is missing or empty.",
            )
        email = email.strip()

        password = params.get("password")
        if not isinstance(password, str) or not password:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Required parameter 'password' is missing or empty.",
            )
        if len(password) < _PASSWORD_MIN_LENGTH:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'password' must be at least "
                f"{_PASSWORD_MIN_LENGTH} characters.",
            )

        # role is optional and informational
        role_raw = params.get("role", ROLE_VIEWER)
        if role_raw in (None, ""):
            role = ROLE_VIEWER
        else:
            try:
                role = _normalize_role(role_raw)
            except ParameterError as exc:
                return ToolResult.error("VALIDATION_ERROR", str(exc))

        # preset is optional and reserved; we accept it but do not enforce
        # it (no workspace has been chosen yet at creation time).
        preset = params.get("preset", "basic")
        if preset is None or (isinstance(preset, str) and not preset.strip()):
            preset = "basic"
        elif not isinstance(preset, str):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'preset' must be a string.",
            )
        else:
            preset = preset.strip().lower()

        # Tenant resolution: superuser may pass tenant_id; non-superuser
        # is forced to the auth context's tenant.
        is_superuser = self._caller_is_superuser(auth_context.user_id)
        tenant_id_param = optional_uuid(params, "tenant_id")
        if tenant_id_param is not None:
            if not is_superuser:
                return ToolResult.error(
                    "PERMISSION_DENIED",
                    "Parameter 'tenant_id' is only honoured for superuser "
                    "callers. Non-superuser admins must create users in "
                    "their own tenant.",
                )
            tenant_id = tenant_id_param
        else:
            tenant_id = auth_context.tenant_id

        # Validate tenant exists (raises NotFoundError otherwise)
        try:
            tenant = Tenant.objects.filter(id=tenant_id).first()
        except Exception as exc:
            logger.exception("user.create: tenant lookup failed")
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        if tenant is None:
            return ToolResult.error(
                "NOT_FOUND",
                f"Tenant with id {tenant_id!r} not found.",
            )

        # Uniqueness pre-checks (User has unique=True on username and email)
        if User.objects.filter(username__iexact=username).exists():
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Username {username!r} is already taken.",
            )
        if User.objects.filter(email__iexact=email).exists():
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Email {email!r} is already in use.",
            )

        try:
            user = User.objects.create(
                username=username,
                email=email,
                tenant=tenant,
                is_active=True,
            )
            user.set_password(password)
            user.save(update_fields=["password", "modified_at", "version"])
        except (ValueError, TypeError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except Exception as exc:
            logger.exception("user.create: DB error")
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="user.create",
            entity_type="User",
            entity_id=user.id,
            tool_name="user.create",
            api_key=api_key,
            details={
                "username": user.username,
                "email": user.email,
                "tenant_id": str(tenant.id),
                "role_hint": role,
                "preset_hint": preset,
            },
        )

        return ToolResult.ok({"user": _user_to_dict(user)})

    # ------------------------------------------------------------------
    # user.assign_role (write, audited)
    # ------------------------------------------------------------------

    def _handle_user_assign_role(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.assign_role — assign a role to a user in a workspace (admin-only).

        Required params:
            user_id     : UUID of the target user.
            workspace_id: UUID of the target workspace.
            role        : role to assign (admin/editor/viewer/approver).
            preset      : active workspace preset (gates Approver).

        The actual role-assignment is delegated to
        :meth:`AuthorizationService.assign_role`; the wrapper only adds
        parameter validation, error mapping and the MCP-level audit
        entry. ``AuthorizationService.assign_role`` re-checks the admin
        role as defence in depth.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        target_user_id = require_uuid(params, "user_id")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            role = _normalize_role(params.get("role"))
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        preset = params.get("preset")
        if not isinstance(preset, str) or not preset.strip():
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Required parameter 'preset' is missing or empty.",
            )
        preset = preset.strip().lower()

        # Tenant context must be set so that AuthorizationService's
        # UserRole queries (which use the tenant-scoped manager) work.
        TenantContext.set_tenant(auth_context.tenant_id)

        # target_is_member: a user is "a member of the workspace" iff
        # they have at least one active (non-suspended) role in that
        # workspace. This matches the convention used by the rest of
        # the codebase: any active role assignment implies membership.
        target_is_member = UserRole.objects.filter(
            user_id=target_user_id,
            workspace_id=workspace_id,
            suspended_at__isnull=True,
        ).exists()

        try:
            user_role = self._authz_service.assign_role(
                actor_roles=auth_context.active_roles,
                target_user_id=target_user_id,
                workspace_id=workspace_id,
                tenant_id=auth_context.tenant_id,
                role=role,
                preset=preset,
                assigned_by_user_id=auth_context.user_id,
                target_is_member=target_is_member,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="user.assign_role",
            entity_type="UserRole",
            entity_id=user_role.id,
            tool_name="user.assign_role",
            api_key=api_key,
            details={
                "target_user_id": str(target_user_id),
                "workspace_id": str(workspace_id),
                "role": role,
                "preset": preset,
            },
        )

        return ToolResult.ok(
            {
                "assignment": {
                    "id": str(user_role.id),
                    "user_id": str(user_role.user_id),
                    "workspace_id": str(user_role.workspace_id),
                    "role": user_role.role,
                    "suspended_at": (
                        user_role.suspended_at.isoformat()
                        if user_role.suspended_at
                        else None
                    ),
                }
            }
        )

    # ------------------------------------------------------------------
    # user.list (read)
    # ------------------------------------------------------------------

    def _handle_user_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.list — list users (admin-only, read).

        Optional params:
            tenant_id : tenant to scope to. Defaults to
                        ``auth_context.tenant_id``. A superuser caller
                        may pass an explicit tenant id to query any
                        tenant; a non-superuser caller that passes a
                        foreign tenant id is rejected.
            is_active : bool filter; if None, returns both.
            limit     : page size, 1..500, default 100.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        # Tenant resolution: superuser can override, non-superuser forced.
        is_superuser = self._caller_is_superuser(auth_context.user_id)
        tenant_id_param = optional_uuid(params, "tenant_id")
        if tenant_id_param is not None:
            if not is_superuser and tenant_id_param != auth_context.tenant_id:
                return ToolResult.error(
                    "PERMISSION_DENIED",
                    "Parameter 'tenant_id' must equal the caller's tenant "
                    "unless the caller is a superuser.",
                )
            tenant_id = tenant_id_param
        else:
            tenant_id = auth_context.tenant_id

        # is_active filter
        is_active_raw = params.get("is_active")
        if is_active_raw is None or is_active_raw == "":
            is_active_filter: Optional[bool] = None
        elif isinstance(is_active_raw, bool):
            is_active_filter = is_active_raw
        elif isinstance(is_active_raw, str):
            lowered = is_active_raw.strip().lower()
            if lowered in ("true", "1", "yes"):
                is_active_filter = True
            elif lowered in ("false", "0", "no"):
                is_active_filter = False
            else:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Parameter 'is_active' must be a boolean.",
                )
        else:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'is_active' must be a boolean.",
            )

        # limit
        limit_raw = params.get("limit", _LIST_DEFAULT_LIMIT)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'limit' must be an integer.",
            )
        if limit < 1 or limit > _LIST_MAX_LIMIT:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'limit' must be in 1..{_LIST_MAX_LIMIT}.",
            )

        try:
            qs = User.objects.filter(tenant_id=tenant_id)
            if is_active_filter is not None:
                qs = qs.filter(is_active=is_active_filter)
            rows = list(qs.order_by("username")[:limit])
        except Exception as exc:
            logger.exception("user.list: DB error")
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        return ToolResult.ok(
            {
                "users": [_user_to_dict(u) for u in rows],
                "count": len(rows),
                "tenant_id": str(tenant_id),
            }
        )

    # ------------------------------------------------------------------
    # user.deactivate (write, audited)
    # ------------------------------------------------------------------

    def _handle_user_deactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.deactivate — deactivate a user (admin-only, write).

        Required params:
            user_id : UUID of the user to deactivate.

        MVP behaviour: sets ``is_active=False``. Does NOT call
        ``AuthorizationService.suspend_approver_assignments`` because
        that operation is workspace-scoped and this handler does not
        have a ``workspace_id``. Future enhancement: a workspace-scoped
        variant of this tool that also suspends approver assignments.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        target_user_id = require_uuid(params, "user_id")

        try:
            user = User.objects.filter(id=target_user_id).first()
        except Exception as exc:
            logger.exception("user.deactivate: DB error")
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        if user is None:
            return ToolResult.error(
                "NOT_FOUND",
                f"User with id {target_user_id!r} not found.",
            )

        # No self-protection rule at MVP. A future enhancement could
        # reject deactivation of the last active admin in the tenant,
        # but that requires cross-cutting role queries that the
        # current handler does not perform. See the module docstring.

        was_active = user.is_active
        if was_active:
            try:
                user.is_active = False
                user.save(update_fields=["is_active", "modified_at", "version"])
            except Exception as exc:
                logger.exception("user.deactivate: save failed")
                return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="user.deactivate",
            entity_type="User",
            entity_id=user.id,
            tool_name="user.deactivate",
            api_key=api_key,
            details={
                "username": user.username,
                "was_active": was_active,
            },
        )

        return ToolResult.ok(
            {
                "deactivated": True,
                "user": _user_to_dict(user),
            }
        )


__all__ = ["UsersToolGroup"]
