"""
COMP-MC-011 UsersToolGroup — 9 admin/tenant-admin user-management MCP tools
(REQ-L1-046, multi-user management design spec).

leaf_id : COMP-MC-011
req_id  : REQ-L1-046 (admin umbrella — user management is an admin operation),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-011 (structured error response),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented (write tools are audited):

  user.create             (write)  — create a new user (tenant-admin-only)
  user.assign_role        (write)  — assign a role to a user in a workspace
                                      (workspace-admin or tenant-admin)
  user.list               (read)   — list users (tenant-scoped, admin-only)
  user.deactivate         (write)  — deactivate a user (tenant-admin-only,
                                      last-admin protected)
  user.activate           (write)  — reactivate a user (tenant-admin-only)
  user.suspend_role       (write)  — soft-suspend a workspace role
                                      (workspace-admin or tenant-admin,
                                      last-admin protected)
  user.reactivate_role    (write)  — clear a workspace role's suspension
                                      (workspace-admin or tenant-admin)
  user.assign_tenant_admin(write)  — grant tenant-admin (tenant-admin-only)
  user.revoke_tenant_admin(write)  — revoke tenant-admin (tenant-admin-only,
                                      last-admin protected)

Architecture
------------
* The ``user.*`` namespace is owned by this group; no other group handles
  it. The prefix-based router (ADR-L3-MC002-03) dispatches any
  ``user.<x>`` tool to this group via the ``"user"`` prefix registered in
  ``tool_registry._ensure_groups()``.

* Admin gates come in two shapes:
  - Workspace-scoped: ``_check_admin`` checks
    ``auth_context.has_role("admin")`` (workspace-scoped ``UserRole``).
    Still used by ``user.list``.
  - Tenant-scoped: ``self._authz_service.is_tenant_admin(...)`` (a
    ``TenantRole`` check) — used directly by every tool that is
    tenant-admin-exclusive (``user.create``/``.deactivate``/``.activate``/
    ``.assign_tenant_admin``/``.revoke_tenant_admin``), and passed as
    ``actor_is_tenant_admin`` into ``AuthorizationService.assign_role``/
    ``.suspend_role``/``.reactivate_role`` for the tools where EITHER a
    workspace-admin OR a tenant-admin may act.
  ``user.assign_role``/``.suspend_role``/``.reactivate_role`` deliberately
  do NOT call ``_check_admin`` at all (closed gap, multi-user management
  Task 9): a workspace-scoped pre-gate would deny a pure tenant-admin (a
  caller holding only ``TenantRole(admin)``, zero workspace-level
  ``UserRole`` anywhere) before the service's own tenant-admin elevation
  branch is ever reached. The service methods perform the real
  authorization check themselves (admin-in-``actor_roles`` OR
  ``actor_is_tenant_admin`` OR, for ``assign_role`` only, the SEC-05
  first-admin-bootstrap exception) — mirrors the REST-layer precedent in
  ``rest_api.user_management_views.UserViewSet`` and
  ``auth_tenancy.rest_workspace_members.WorkspaceMemberRoleTransitionView``,
  both of which dropped their own coarse pre-gate for the equivalent
  actions for the same reason. The registry-level write-RBAC gate
  (``ToolRegistry._is_tenant_admin_exempt`` in ``mcp_server/tool_registry.py``)
  was fixed the same way, for the same underlying gap one layer up.

* ``user.create``/``.deactivate``/``.activate`` delegate to
  :class:`auth_tenancy.services.user_account.UserAccountService`, the
  single place that may flip ``User.is_active`` or create a ``User`` row
  (multi-user management design spec) — no direct ``User.objects.create``/
  ``.save()`` in this module. ``UserAccountService`` performs its own
  validation (uniqueness, password length, string normalisation) and
  raises ``ValueError`` for any failure; this module does not duplicate
  that validation, it only maps the exception to ``VALIDATION_ERROR``.

* ``user.assign_role``/``.suspend_role``/``.reactivate_role`` delegate to
  the matching :class:`AuthorizationService` method (COMP-AT-002); the
  wrapper adds parameter validation, error mapping and the MCP-level audit
  entry. No business logic is duplicated.

* ``user.assign_tenant_admin``/``.revoke_tenant_admin`` delegate to
  :class:`AuthorizationService.assign_tenant_admin`/``.revoke_tenant_admin``.
  These are inherently tenant-scoped (no ``workspace_id``), so they check
  ``is_tenant_admin(...)`` directly rather than via ``_check_admin``.

* ``user.list`` queries the ``User`` model directly. ``User`` does NOT
  inherit from ``TenantScopedModel`` (membership in a tenant is
  optional), so the query does not require a tenant context. The handler
  filters by ``tenant_id`` (default = ``auth_context.tenant_id``) and
  applies the optional ``is_active`` filter and the page-size limit.

Error mapping (REQ-L2-MC-011):
  NotFoundError / User.DoesNotExist        -> NOT_FOUND
  PermissionDeniedError / PermissionDenied -> PERMISSION_DENIED
  LastAdminError                           -> LAST_ADMIN
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
    preset      : active workspace preset (optional; NO LONGER
                  authoritative for the Approver gate — see the tool's
                  schema and handler docstring)

Parameters accepted by ``user.list``:
    tenant_id : UUID of the tenant to scope to (optional,
                defaults to auth_context.tenant_id)
    is_active : bool filter; if None, returns both (optional)
    limit     : page size, 1..500, default 100 (optional)

Parameters accepted by ``user.deactivate`` / ``user.activate``:
    user_id : UUID of the target user (required)

Parameters accepted by ``user.suspend_role`` / ``user.reactivate_role``:
    user_id      : UUID of the target user      (required)
    workspace_id : UUID of the target workspace (required)
    role         : role name to suspend/reactivate (required)

Parameters accepted by ``user.assign_tenant_admin`` / ``user.revoke_tenant_admin``:
    user_id : UUID of the target user (required; tenant is implicit from
              ``auth_context.tenant_id``)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from auth_tenancy.errors import PermissionDenied as AuthTenancyPermissionDenied
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from auth_tenancy.services import AuthorizationService
from auth_tenancy.services.authorization import LastAdminError
from auth_tenancy.services.user_account import UserAccountService

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

from persistence.models import User
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
        "user.activate": "_handle_user_activate",
        "user.suspend_role": "_handle_user_suspend_role",
        "user.reactivate_role": "_handle_user_reactivate_role",
        "user.assign_tenant_admin": "_handle_user_assign_tenant_admin",
        "user.revoke_tenant_admin": "_handle_user_revoke_tenant_admin",
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
                        "description": (
                            "Active workspace preset. NOTE: no longer "
                            "authoritative for the Approver-role gate — "
                            "AuthorizationService.assign_role now resolves "
                            "the workspace's real preset tier itself, "
                            "straight from the database, and ignores any "
                            "value supplied here. Kept for backward "
                            "compatibility with existing callers only."
                        ),
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
            "description": "Deactivate a user (is_active=False), tenant-admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the user to deactivate."},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "user.activate",
            "description": "Activate a user (is_active=True), tenant-admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the user to activate."},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "user.suspend_role",
            "description": "Suspend a user's workspace role (reversible), admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the target user."},
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "role": {
                        "type": "string",
                        "enum": ["admin", "editor", "viewer", "approver"],
                        "description": "Role to suspend.",
                    },
                },
                "required": ["user_id", "workspace_id", "role"],
            },
        },
        {
            "name": "user.reactivate_role",
            "description": "Reactivate a suspended workspace role, admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the target user."},
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "role": {
                        "type": "string",
                        "enum": ["admin", "editor", "viewer", "approver"],
                        "description": "Role to reactivate.",
                    },
                },
                "required": ["user_id", "workspace_id", "role"],
            },
        },
        {
            "name": "user.assign_tenant_admin",
            "description": "Grant tenant-admin to a user, tenant-admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the target user."},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "user.revoke_tenant_admin",
            "description": "Revoke tenant-admin from a user, tenant-admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the target user."},
                },
                "required": ["user_id"],
            },
        },
    ]

    def __init__(
        self, authz_service: Optional[AuthorizationService] = None
    ) -> None:
        self._authz_service = authz_service or AuthorizationService()
        self._accounts = UserAccountService()

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
        """user.create — create a new user (tenant-admin-only, write).

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

        Delegates the actual creation to
        :meth:`UserAccountService.create` (tenant-admin-guarded), matching
        the design spec's permission matrix (§3: ``user.create`` is
        tenant-admin-exclusive, not merely workspace-admin). All
        username/email/password validation is performed by the service —
        this handler does not duplicate it, it only maps ``ValueError`` to
        ``VALIDATION_ERROR`` (mirrors ``rest_api.user_management_views.
        UserViewSet.create``).
        """
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

        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=tenant_id
        )
        try:
            user = self._accounts.create(
                actor_is_tenant_admin=is_admin,
                tenant_id=tenant_id,
                username=username,
                email=email,
                password=password,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error(
                "PERMISSION_DENIED",
                "Permission denied: tenant-admin role required.",
            )
        except ValueError as exc:
            # UserAccountService.create documents ValueError as its
            # validation-failure contract (bad/duplicate username/email,
            # weak password, unknown tenant). Anything else (DB errors,
            # programming bugs) is NOT masked here — it propagates and is
            # caught by BaseToolGroup.execute_tool's outer catch-all
            # (INTERNAL_ERROR, logged), matching how
            # rest_api.user_management_views.UserViewSet.create only
            # narrowly catches ValueError too.
            return ToolResult.error("VALIDATION_ERROR", str(exc))

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
                "tenant_id": str(tenant_id),
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
        """user.assign_role — assign a role to a user in a workspace.

        Required params:
            user_id     : UUID of the target user.
            workspace_id: UUID of the target workspace.
            role        : role to assign (admin/editor/viewer/approver).
            preset      : accepted but NO LONGER authoritative for the
                          Approver gate (see note below).

        The actual role-assignment is delegated to
        :meth:`AuthorizationService.assign_role`; the wrapper only adds
        parameter validation, error mapping and the MCP-level audit
        entry. No admin pre-gate is applied in this handler (see below) —
        ``AuthorizationService.assign_role`` performs the real
        authorization check itself (admin-in-workspace OR tenant-admin OR
        the SEC-05 first-admin-bootstrap exception), so this handler is a
        thin, defence-preserving wrapper, not the authority.

        Closed gap (multi-user management Task 9): this handler used to
        gate on ``self._check_admin(auth_context)`` — a workspace-scoped
        check (``auth_context.active_roles``) — before ever calling the
        service. That denied a pure tenant-admin (a caller holding only
        ``TenantRole(admin)``, zero workspace-level ``UserRole``
        anywhere) even though the service already has a tenant-admin
        elevation branch. Removing the pre-gate here (letting
        ``AuthorizationService.assign_role``'s own
        admin-in-``actor_roles``-OR-``actor_is_tenant_admin``-OR-bootstrap
        check be the sole authority) mirrors the REST-layer fix already
        applied to ``auth_tenancy.rest_workspace_members.
        WorkspaceMembersView.post`` for the identical reason. No defence
        is lost: the service still denies any caller who is neither a
        workspace-admin, a tenant-admin, nor a first-admin-bootstrap
        candidate.

        Preset note (fix round, N/A - Task 9 point 5): the caller-supplied
        ``preset`` is no longer authoritative for the Approver-role gate —
        :meth:`AuthorizationService.assign_role` resolves the workspace's
        REAL preset tier fresh from the database for that one decision
        (fix round 2, N-3 in ``authorization.py``). ``preset`` is still
        accepted (kept required for backward compatibility with existing
        callers) but is effectively decorative for anything but the
        (now-ignored) value logged historically; the audit entry below no
        longer records it, to avoid misrepresenting what the actual
        authorization decision was based on.
        """
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
        # UserRole/TenantRole queries (which use the tenant-scoped manager)
        # work.
        TenantContext.set_tenant(auth_context.tenant_id)

        # A pure tenant-admin (TenantRole(admin), no workspace-level role)
        # may assign roles in any workspace of their own tenant (multi-user
        # management design spec §3). Resolved via self._authz_service (the
        # injected AuthorizationService, real in production / a test double
        # in unit tests) rather than a fresh AuthorizationService() — this
        # keeps the same dependency-injection seam the rest of this handler
        # already relies on for testability.
        actor_is_tenant_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

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
                actor_is_tenant_admin=actor_is_tenant_admin,
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
        except (PermissionDeniedError, AuthTenancyPermissionDenied) as exc:
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
                # Task 9 point 5: the caller-supplied `preset` is no longer
                # what the Approver gate actually decided on (see the
                # handler docstring) — recording it here would misrepresent
                # the real authorization basis, so it is omitted rather
                # than logging a value the service ignored.
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
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

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
        """user.deactivate — deactivate a user (tenant-admin-only, write).

        Required params:
            user_id : UUID of the user to deactivate.

        Delegates to :meth:`UserAccountService.deactivate`, last-admin
        protected at BOTH workspace and tenant scope (see that method's
        docstring). The admin gate here is tenant-admin ONLY, not
        workspace-admin (matches ``rest_api.user_management_views.
        UserViewSet.deactivate`` and the design spec's permission matrix
        §3) — this handler does NOT also call ``_check_admin``.

        Ordering note (fix found via ``test_mcp_rbac_role_matrix.py``'s
        server-side admin-gate drift test): the service's own permission
        check MUST run before any existence check is surfaced to the
        caller. An earlier version of this handler pre-fetched the target
        via ``User.objects.filter(...).first()`` and returned NOT_FOUND
        immediately when that lookup failed — for a non-admin caller
        targeting a non-existent id, that leaked "this id does not
        exist" to a caller who was never authorized to ask in the first
        place, and (worse) inverted the expected PERMISSION_DENIED for a
        non-admin caller into a NOT_FOUND. The pre-fetch below is now
        informational ONLY (captures ``was_active`` for the audit entry)
        — it never gates or returns early; ``UserAccountService.deactivate``
        is the sole authority for both the permission check (which it
        performs FIRST) and the existence check.
        """
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

        try:
            pre_user = User.objects.filter(id=target_user_id).first()
        except Exception:
            pre_user = None
        was_active = pre_user.is_active if pre_user is not None else None

        try:
            self._accounts.deactivate(
                actor_is_tenant_admin=is_admin,
                actor_tenant_id=auth_context.tenant_id,
                target_user_id=target_user_id,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error(
                "PERMISSION_DENIED",
                "Permission denied: tenant-admin role required.",
            )
        except LastAdminError as exc:
            return ToolResult.error("LAST_ADMIN", str(exc))
        except User.DoesNotExist:
            return ToolResult.error(
                "NOT_FOUND",
                f"User with id {target_user_id!r} not found.",
            )

        user = User.objects.filter(id=target_user_id).first()
        if user is None:
            return ToolResult.error(
                "NOT_FOUND",
                f"User with id {target_user_id!r} not found.",
            )
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

    # ------------------------------------------------------------------
    # user.activate (write, audited)
    # ------------------------------------------------------------------

    def _handle_user_activate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.activate — activate a user (tenant-admin-only, write).

        Required params:
            user_id : UUID of the target user.

        Delegates to :meth:`UserAccountService.activate`. No last-admin
        check (activating never removes an admin). Mirrors
        ``_handle_user_deactivate``'s structure and error mapping.
        """
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

        try:
            self._accounts.activate(
                actor_is_tenant_admin=is_admin,
                actor_tenant_id=auth_context.tenant_id,
                target_user_id=target_user_id,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error(
                "PERMISSION_DENIED",
                "Permission denied: tenant-admin role required.",
            )
        except User.DoesNotExist:
            return ToolResult.error(
                "NOT_FOUND",
                f"User with id {target_user_id!r} not found.",
            )

        user = User.objects.filter(id=target_user_id).first()
        if user is None:
            # Defensive: activate() already confirmed the row exists, but
            # a concurrent hard-delete between the update and this
            # read-back is not impossible.
            return ToolResult.error(
                "NOT_FOUND",
                f"User with id {target_user_id!r} not found.",
            )

        write_mcp_audit(
            ctx=auth_context,
            operation="user.activate",
            entity_type="User",
            entity_id=user.id,
            tool_name="user.activate",
            api_key=api_key,
            details={"username": user.username},
        )

        return ToolResult.ok({"activated": True, "user": _user_to_dict(user)})

    # ------------------------------------------------------------------
    # user.suspend_role / user.reactivate_role (write, audited)
    # ------------------------------------------------------------------

    def _handle_user_suspend_role(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.suspend_role — soft-suspend a workspace role assignment.

        Required params:
            user_id      : UUID of the target user.
            workspace_id : UUID of the target workspace.
            role         : role name to suspend.

        Delegates to :meth:`AuthorizationService.suspend_role`
        (workspace-admin OR tenant-admin, last-admin protected). No
        ``_check_admin`` pre-gate here — same rationale as
        ``_handle_user_assign_role``: a workspace-scoped pre-gate would
        deny a pure tenant-admin before the service's own elevation
        branch is reached. The service is the sole authority.
        """
        target_user_id = require_uuid(params, "user_id")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            role = _normalize_role(params.get("role"))
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        actor_is_tenant_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

        try:
            self._authz_service.suspend_role(
                actor_roles=auth_context.active_roles,
                actor_is_tenant_admin=actor_is_tenant_admin,
                target_user_id=target_user_id,
                workspace_id=workspace_id,
                role=role,
            )
        except (PermissionDeniedError, AuthTenancyPermissionDenied) as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except LastAdminError as exc:
            return ToolResult.error("LAST_ADMIN", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="user.suspend_role",
            entity_type="UserRole",
            entity_id=target_user_id,
            tool_name="user.suspend_role",
            api_key=api_key,
            details={
                "target_user_id": str(target_user_id),
                "workspace_id": str(workspace_id),
                "role": role,
            },
        )

        return ToolResult.ok({"suspended": True})

    def _handle_user_reactivate_role(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.reactivate_role — clear a workspace role's suspension.

        Required params:
            user_id      : UUID of the target user.
            workspace_id : UUID of the target workspace.
            role         : role name to reactivate.

        Delegates to :meth:`AuthorizationService.reactivate_role`
        (workspace-admin OR tenant-admin). No ``_check_admin`` pre-gate —
        see ``_handle_user_suspend_role``.
        """
        target_user_id = require_uuid(params, "user_id")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            role = _normalize_role(params.get("role"))
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        actor_is_tenant_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

        try:
            self._authz_service.reactivate_role(
                actor_roles=auth_context.active_roles,
                actor_is_tenant_admin=actor_is_tenant_admin,
                target_user_id=target_user_id,
                workspace_id=workspace_id,
                role=role,
            )
        except (PermissionDeniedError, AuthTenancyPermissionDenied) as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="user.reactivate_role",
            entity_type="UserRole",
            entity_id=target_user_id,
            tool_name="user.reactivate_role",
            api_key=api_key,
            details={
                "target_user_id": str(target_user_id),
                "workspace_id": str(workspace_id),
                "role": role,
            },
        )

        return ToolResult.ok({"reactivated": True})

    # ------------------------------------------------------------------
    # user.assign_tenant_admin / user.revoke_tenant_admin (write, audited)
    # ------------------------------------------------------------------

    def _handle_user_assign_tenant_admin(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.assign_tenant_admin — grant tenant-admin (tenant-admin-only).

        Required params:
            user_id : UUID of the target user (tenant is implicit from
                      ``auth_context.tenant_id``).

        Inherently tenant-scoped (no ``workspace_id``), so this checks
        ``is_tenant_admin(...)`` directly rather than via
        ``_check_admin``.
        """
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

        try:
            self._authz_service.assign_tenant_admin(
                actor_is_tenant_admin=is_admin,
                target_user_id=target_user_id,
                tenant_id=auth_context.tenant_id,
                assigned_by_user_id=auth_context.user_id,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error(
                "PERMISSION_DENIED",
                "Permission denied: tenant-admin role required.",
            )
        except User.DoesNotExist:
            return ToolResult.error(
                "NOT_FOUND",
                f"User with id {target_user_id!r} not found.",
            )

        write_mcp_audit(
            ctx=auth_context,
            operation="user.assign_tenant_admin",
            entity_type="TenantRole",
            entity_id=target_user_id,
            tool_name="user.assign_tenant_admin",
            api_key=api_key,
            details={"target_user_id": str(target_user_id)},
        )

        return ToolResult.ok({"granted": True})

    def _handle_user_revoke_tenant_admin(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.revoke_tenant_admin — revoke tenant-admin (tenant-admin-only).

        Required params:
            user_id : UUID of the target user.

        Last-admin protected at tenant scope
        (:meth:`AuthorizationService.revoke_tenant_admin`). Inherently
        tenant-scoped, so this checks ``is_tenant_admin(...)`` directly.
        """
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

        try:
            self._authz_service.revoke_tenant_admin(
                actor_is_tenant_admin=is_admin,
                target_user_id=target_user_id,
                tenant_id=auth_context.tenant_id,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error(
                "PERMISSION_DENIED",
                "Permission denied: tenant-admin role required.",
            )
        except LastAdminError as exc:
            return ToolResult.error("LAST_ADMIN", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="user.revoke_tenant_admin",
            entity_type="TenantRole",
            entity_id=target_user_id,
            tool_name="user.revoke_tenant_admin",
            api_key=api_key,
            details={"target_user_id": str(target_user_id)},
        )

        return ToolResult.ok({"revoked": True})


__all__ = ["UsersToolGroup"]
