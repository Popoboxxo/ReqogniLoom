"""
Tests for COMP-MC-011 UsersToolGroup (REQ-L1-046 admin/tenant-admin user
management, multi-user management design spec).

Covers the nine MCP tools exposed under the ``user.*`` namespace:

* user.create              — write, tenant-admin-gated, audited, error mapping
* user.assign_role         — write, workspace-admin OR tenant-admin gated,
                              audited, error mapping, delegates to
                              AuthorizationService.assign_role
* user.list                — read,  workspace-admin OR tenant-admin gated
                              (Fix Round 1, I-4), error mapping
* user.deactivate           — write, tenant-admin-gated, audited, error
                              mapping, last-admin protected
* user.activate             — write, tenant-admin-gated, audited
* user.suspend_role         — write, workspace-admin OR tenant-admin gated,
                              audited, last-admin protected
* user.reactivate_role      — write, workspace-admin OR tenant-admin gated,
                              audited
* user.assign_tenant_admin  — write, tenant-admin-gated, audited
* user.revoke_tenant_admin  — write, tenant-admin-gated, audited, last-admin
                              protected

Plus wiring tests: tool map, write-prefix registration, namespace routing
via the real ``ToolRegistry`` and ``ProtocolHandler`` E2E pipeline, and
dedicated REAL-service (unmocked) E2E tests that prove the Task 9 gap
closure: a pure tenant-admin (only a ``TenantRole``, zero workspace-level
``UserRole`` anywhere) can call the tenant-admin-elevated tools through the
FULL dispatch pipeline (``ToolRegistry.dispatch_request``'s write-RBAC gate
+ the ``UsersToolGroup`` handler + the ``AuthorizationService``/
``UserAccountService`` layer), while a caller with NEITHER a workspace role
NOR tenant-admin status NOR bootstrap eligibility is still denied.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod, IdentityClaims
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.errors import PermissionDenied as AuthTenancyPermissionDenied
from auth_tenancy.models import ApiKey, ROLE_ADMIN, ROLE_VIEWER, TenantRole, UserRole
from auth_tenancy.services import AuthorizationService
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from auth_tenancy.services.authorization import LastAdminError

from application.base import (
    NotFoundError,
    PermissionDeniedError,
)

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User

from mcp_server.protocol_handler import ERROR_CODE_MAP, ProtocolHandler
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.users import UsersToolGroup


# ---------------------------------------------------------------------------
# Shared fixtures / data
# ---------------------------------------------------------------------------


ADMIN_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=(ROLE_ADMIN,),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

EDITOR_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("editor",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

VIEWER_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=(ROLE_VIEWER,),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

VALID_API_KEY = "reqlo_test_admin_key"
TARGET_USER_ID = UUID("00000000-0000-0000-0000-0000000000a1")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-0000000000b1")
USER_ROLE_ID = UUID("00000000-0000-0000-0000-0000000000c1")


def _mock_user(
    *,
    id_val: UUID = None,
    username: str = "alice",
    email: str = "alice@test.local",
    is_active: bool = True,
    is_staff: bool = False,
    is_superuser: bool = False,
    tenant_id: UUID = None,
) -> MagicMock:
    """Build a MagicMock that mimics a persistence.User ORM instance."""
    u = MagicMock()
    u.id = id_val or uuid4()
    u.username = username
    u.email = email
    u.is_active = is_active
    u.is_staff = is_staff
    u.is_superuser = is_superuser
    u.tenant_id = tenant_id or ADMIN_CTX.tenant_id
    u.created_at = None
    return u


def _mock_user_role(
    *,
    id_val: UUID = None,
    user_id: UUID = None,
    workspace_id: UUID = None,
    role: str = ROLE_VIEWER,
    suspended_at=None,
) -> MagicMock:
    """Build a MagicMock that mimics an auth_tenancy.UserRole ORM instance."""
    ur = MagicMock()
    ur.id = id_val or USER_ROLE_ID
    ur.user_id = user_id or TARGET_USER_ID
    ur.workspace_id = workspace_id or WORKSPACE_ID
    ur.role = role
    ur.suspended_at = suspended_at
    return ur


def _group(
    authz: MagicMock | None = None, accounts: MagicMock | None = None
) -> tuple:
    """Build a UsersToolGroup with mocked AuthorizationService/UserAccountService.

    Returns ``(group, authz_mock, accounts_mock)``. ``group._accounts`` is
    always replaced with a mock (never the real ``UserAccountService``) so
    unit tests never hit the database through the service layer.
    """
    svc = authz or MagicMock()
    group = UsersToolGroup(authz_service=svc)
    group._accounts = accounts if accounts is not None else MagicMock()
    return group, svc, group._accounts


def _configure_caller_not_superuser(mock_user_objects: MagicMock) -> None:
    """Configure ``User.objects`` mock so the caller is found but is_superuser=False.

    The handler calls ``User.objects.filter(id=auth_context.user_id).first()``
    to check whether the caller is a Django superuser. By default MagicMock
    returns a truthy MagicMock for ``.first()`` (so ``is_superuser`` evaluates
    truthy), which breaks the test scenario for a non-superuser caller.
    This helper sets up the mock so the caller lookup returns a real
    ``is_superuser=False`` flag.
    """
    caller = MagicMock()
    caller.is_superuser = False
    # First ``.filter(...)`` call in the handler is the id-based caller
    # lookup. Subsequent ``.filter(...)`` calls in some handlers do
    # uniqueness checks via ``.exists()`` — the default MagicMock for
    # ``.exists()`` is truthy, which is wrong, so we explicitly set it.
    mock_user_objects.filter.return_value.first.return_value = caller
    mock_user_objects.filter.return_value.exists.return_value = False


# ---------------------------------------------------------------------------
# Permission-denied error mapping (assign_role/create/deactivate no longer
# have a handler-level pre-gate — the service raises, the handler maps).
# ---------------------------------------------------------------------------


class TestPermissionDeniedMapping:
    """Every write handler maps a service-layer PermissionDenied to
    ``PERMISSION_DENIED`` — ``user.list`` is the only tool that still has
    its own workspace-scoped pre-gate (``_check_admin``), which since Fix
    Round 1 (I-4) also falls through for a tenant-admin caller."""

    def test_user_create_maps_service_permission_denied(self):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = False
        accounts.create.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.create",
            params={
                "username": "newbie",
                "email": "newbie@test.local",
                "password": "abcdefgh",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        accounts.create.assert_called_once()
        assert accounts.create.call_args.kwargs["actor_is_tenant_admin"] is False

    def test_user_list_with_viewer_role_returns_permission_denied(self):
        group, authz, _ = _group()
        # Fix Round 1 (I-4): user.list now falls through to a
        # tenant-admin check when _check_admin denies. Must also be false
        # here so this stays a "no standing at all" scenario.
        authz.is_tenant_admin.return_value = False
        result = group.execute_tool(
            tool_name="user.list",
            params={},
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @patch("mcp_server.tools.users.User.objects")
    def test_user_deactivate_maps_service_permission_denied(self, mock_user_objects):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = False
        u = _mock_user(is_active=True)
        mock_user_objects.filter.return_value.first.return_value = u
        accounts.deactivate.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": str(u.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_user_assign_role_maps_service_permission_denied(
        self, mock_set_tenant, mock_userrole_objects
    ):
        group, authz, _ = _group()
        authz.assign_role.side_effect = AuthTenancyPermissionDenied()
        mock_userrole_objects.filter.return_value.exists.return_value = False

        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
                "preset": "extended",
            },
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        # Unlike the old pre-gated behaviour, the service IS now called —
        # it is the sole authority (Task 9 gap closure).
        authz.assign_role.assert_called_once()


# ---------------------------------------------------------------------------
# user.create
# ---------------------------------------------------------------------------


class TestUserCreate:
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_user_create_delegates_to_service_and_audits(self, mock_audit):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = True
        created = _mock_user(
            id_val=UUID("00000000-0000-0000-0000-0000000000d1"),
            username="newbie",
            email="newbie@test.local",
        )
        accounts.create.return_value = created

        result = group.execute_tool(
            tool_name="user.create",
            params={
                "username": "newbie",
                "email": "newbie@test.local",
                "password": "abcdefgh",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["user"]["username"] == "newbie"
        assert result.data["user"]["is_active"] is True
        accounts.create.assert_called_once_with(
            actor_is_tenant_admin=True,
            tenant_id=ADMIN_CTX.tenant_id,
            username="newbie",
            email="newbie@test.local",
            password="abcdefgh",
        )
        # Audit was written
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "user.create"
        assert audit_kwargs["operation"] == "user.create"
        assert audit_kwargs["entity_type"] == "User"
        assert audit_kwargs["details"]["tenant_id"] == str(ADMIN_CTX.tenant_id)

    def test_user_create_missing_username_returns_validation_error(self):
        group, _, accounts = _group()
        result = group.execute_tool(
            tool_name="user.create",
            params={"email": "x@y.z", "password": "abcdefgh"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        accounts.create.assert_not_called()

    def test_user_create_missing_email_returns_validation_error(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.create",
            params={"username": "x", "password": "abcdefgh"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_create_short_password_returns_validation_error(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.create",
            params={"username": "x", "email": "x@y.z", "password": "short"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "8" in result.message

    def test_user_create_unknown_role_returns_validation_error(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.create",
            params={
                "username": "x",
                "email": "x@y.z",
                "password": "abcdefgh",
                "role": "wizard",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_create_service_value_error_returns_validation_error(self):
        """UserAccountService.create's own validation (uniqueness, password
        length, ...) is authoritative — the handler only maps ValueError,
        it does not duplicate the check."""
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = True
        accounts.create.side_effect = ValueError("Username 'alice' is already taken.")

        result = group.execute_tool(
            tool_name="user.create",
            params={
                "username": "alice",
                "email": "alice@test.local",
                "password": "abcdefgh",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "already taken" in result.message

    @patch("mcp_server.tools.users.User.objects")
    def test_user_create_tenant_id_as_non_superuser_returns_permission_denied(
        self, mock_user_objects
    ):
        """Non-superuser caller passing tenant_id must be rejected."""
        group, _, accounts = _group()
        _configure_caller_not_superuser(mock_user_objects)
        result = group.execute_tool(
            tool_name="user.create",
            params={
                "username": "x",
                "email": "x@y.z",
                "password": "abcdefgh",
                "tenant_id": str(uuid4()),
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        accounts.create.assert_not_called()

    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.User.objects")
    def test_user_create_superuser_can_create_in_foreign_tenant(
        self, mock_user_objects, mock_audit
    ):
        """Fix Round 1, I-2: a real Django superuser passing an explicit
        ``tenant_id`` they hold no ``TenantRole(admin)`` in must still
        succeed — this is the entire point of the superuser ``tenant_id``
        override (still documented in this tool's schema: "superuser
        callers only"). The gate used to be ``is_tenant_admin(...,
        tenant_id=<foreign tenant>)`` alone, which silently broke this: a
        real superuser is not necessarily a TenantRole(admin) of the
        FOREIGN tenant they are targeting, so that check evaluated False
        and wrongly denied. The gate must accept EITHER standing.
        """
        group, authz, accounts = _group()
        # The caller IS a genuine Django superuser...
        caller = MagicMock()
        caller.is_superuser = True
        mock_user_objects.filter.return_value.first.return_value = caller
        # ...but holds no TenantRole(admin) in the foreign target tenant.
        authz.is_tenant_admin.return_value = False

        foreign_tenant_id = uuid4()
        created = _mock_user(
            id_val=UUID("00000000-0000-0000-0000-0000000000d2"),
            username="cross-tenant-user",
            tenant_id=foreign_tenant_id,
        )
        accounts.create.return_value = created

        result = group.execute_tool(
            tool_name="user.create",
            params={
                "username": "cross-tenant-user",
                "email": "cross-tenant-user@test.local",
                "password": "abcdefgh",
                "tenant_id": str(foreign_tenant_id),
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True, result.message
        accounts.create.assert_called_once()
        # actor_is_tenant_admin must be True even though
        # authz.is_tenant_admin(...) returned False — the superuser status
        # alone must be sufficient to open the gate.
        assert accounts.create.call_args.kwargs["actor_is_tenant_admin"] is True
        assert accounts.create.call_args.kwargs["tenant_id"] == foreign_tenant_id


# ---------------------------------------------------------------------------
# user.assign_role
# ---------------------------------------------------------------------------


class TestUserAssignRole:
    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_user_assign_role_calls_authorization_service_and_audits(
        self, mock_set_tenant, mock_userrole_objects, mock_audit
    ):
        group, authz, _ = _group()
        authz.assign_role.return_value = _mock_user_role()
        # target is already a member
        mock_userrole_objects.filter.return_value.exists.return_value = True

        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "editor",
                "preset": "extended",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["assignment"]["role"] == "viewer"
        authz.assign_role.assert_called_once()
        call_kwargs = authz.assign_role.call_args.kwargs
        assert call_kwargs["target_user_id"] == TARGET_USER_ID
        assert call_kwargs["workspace_id"] == WORKSPACE_ID
        assert call_kwargs["role"] == "editor"
        assert call_kwargs["preset"] == "extended"
        assert call_kwargs["tenant_id"] == ADMIN_CTX.tenant_id
        assert call_kwargs["assigned_by_user_id"] == ADMIN_CTX.user_id
        assert call_kwargs["target_is_member"] is True
        # actor_is_tenant_admin is forwarded (resolved via authz.is_tenant_admin)
        assert "actor_is_tenant_admin" in call_kwargs
        # Tenant context was set so the userrole query worked
        mock_set_tenant.assert_called_once_with(ADMIN_CTX.tenant_id)
        # Audit was written
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "user.assign_role"
        assert audit_kwargs["entity_type"] == "UserRole"
        # Task 9 point 5: the (now-ignored) client-supplied preset must NOT
        # be written into the audit details anymore.
        assert "preset" not in audit_kwargs["details"]

    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_user_assign_role_non_member_target_reaches_service_with_false(
        self, mock_set_tenant, mock_userrole_objects
    ):
        group, authz, _ = _group()
        # AuthorizationService raises ValueError for non-member target
        authz.assign_role.side_effect = ValueError(
            "Target user is not a member of the workspace."
        )
        mock_userrole_objects.filter.return_value.exists.return_value = False

        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "editor",
                "preset": "extended",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        # Service was called with target_is_member=False
        call_kwargs = authz.assign_role.call_args.kwargs
        assert call_kwargs["target_is_member"] is False

    def test_user_assign_role_missing_user_id_returns_validation_error(self):
        group, authz, _ = _group()
        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
                "preset": "extended",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        authz.assign_role.assert_not_called()

    def test_user_assign_role_missing_preset_returns_validation_error(self):
        group, authz, _ = _group()
        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        authz.assign_role.assert_not_called()

    def test_user_assign_role_unknown_role_returns_validation_error(self):
        group, authz, _ = _group()
        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "wizard",
                "preset": "extended",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        authz.assign_role.assert_not_called()

    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_user_assign_role_service_raises_not_found(
        self, mock_set_tenant, mock_userrole_objects
    ):
        group, authz, _ = _group()
        authz.assign_role.side_effect = NotFoundError("user not found")
        mock_userrole_objects.filter.return_value.exists.return_value = True

        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "editor",
                "preset": "extended",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_user_assign_role_service_raises_permission_denied(
        self, mock_set_tenant, mock_userrole_objects
    ):
        group, authz, _ = _group()
        authz.assign_role.side_effect = PermissionDeniedError("admin required")
        mock_userrole_objects.filter.return_value.exists.return_value = True

        result = group.execute_tool(
            tool_name="user.assign_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "editor",
                "preset": "extended",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_user_assign_role_does_not_audit_on_failure(
        self, mock_set_tenant, mock_userrole_objects
    ):
        group, authz, _ = _group()
        authz.assign_role.side_effect = NotFoundError("user not found")
        mock_userrole_objects.filter.return_value.exists.return_value = True

        with patch("mcp_server.tools.users.write_mcp_audit") as mock_audit:
            result = group.execute_tool(
                tool_name="user.assign_role",
                params={
                    "user_id": str(TARGET_USER_ID),
                    "workspace_id": str(WORKSPACE_ID),
                    "role": "editor",
                    "preset": "extended",
                },
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        mock_audit.assert_not_called()


# ---------------------------------------------------------------------------
# user.list
# ---------------------------------------------------------------------------


class TestUserList:
    @patch("mcp_server.tools.users.User.objects")
    def test_user_list_returns_tenant_users(self, mock_user_objects):
        group, _, _ = _group()
        # Configure the mock so the caller is not a superuser — the
        # handler calls ``User.objects.filter(id=...).first()`` first,
        # then the actual tenant-scoped query.
        caller = MagicMock()
        caller.is_superuser = False
        mock_user_objects.filter.return_value.first.return_value = caller
        # The actual list query: filter by tenant, order, slice.
        list_qs = MagicMock()
        u1 = _mock_user(username="alice", email="a@t.local")
        u2 = _mock_user(username="bob", email="b@t.local")
        list_qs.order_by.return_value.__getitem__.return_value = [u1, u2]
        # ``User.objects.filter(tenant_id=...)`` is the second call, so we
        # set up ``filter.side_effect`` to return different querysets for
        # each call.
        mock_user_objects.filter.side_effect = [
            MagicMock(first=MagicMock(return_value=caller)),
            list_qs,
        ]

        result = group.execute_tool(
            tool_name="user.list",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["count"] == 2
        assert len(result.data["users"]) == 2
        assert result.data["tenant_id"] == str(ADMIN_CTX.tenant_id)
        # The second filter call was the tenant-scoped query.
        assert mock_user_objects.filter.call_args_list[1] == (
            (),
            {"tenant_id": ADMIN_CTX.tenant_id},
        )

    @patch("mcp_server.tools.users.User.objects")
    def test_user_list_with_is_active_filter(self, mock_user_objects):
        group, _, _ = _group()
        # First call: caller is_superuser check
        caller = MagicMock()
        caller.is_superuser = False
        # Second call: tenant-scoped filter, with chained is_active filter
        list_qs = MagicMock()
        list_qs.filter.return_value.order_by.return_value.__getitem__.return_value = []
        mock_user_objects.filter.side_effect = [
            MagicMock(first=MagicMock(return_value=caller)),
            list_qs,
        ]

        result = group.execute_tool(
            tool_name="user.list",
            params={"is_active": "true"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        # The chained is_active filter was applied
        list_qs.filter.assert_called_with(is_active=True)

    def test_user_list_invalid_is_active_returns_validation_error(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.list",
            params={"is_active": "maybe"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_list_invalid_limit_returns_validation_error(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.list",
            params={"limit": 0},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

        result = group.execute_tool(
            tool_name="user.list",
            params={"limit": "abc"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

        result = group.execute_tool(
            tool_name="user.list",
            params={"limit": 9999},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_list_does_not_write_audit(self):
        group, _, _ = _group()
        with patch("mcp_server.tools.users.User.objects") as mock_user_objects:
            caller = MagicMock()
            caller.is_superuser = False
            list_qs = MagicMock()
            list_qs.order_by.return_value.__getitem__.return_value = []
            mock_user_objects.filter.side_effect = [
                MagicMock(first=MagicMock(return_value=caller)),
                list_qs,
            ]
            with patch("mcp_server.tools.users.write_mcp_audit") as mock_audit:
                result = group.execute_tool(
                    tool_name="user.list",
                    params={},
                    auth_context=ADMIN_CTX,
                    api_key=VALID_API_KEY,
                )
        assert result.success is True
        mock_audit.assert_not_called()

    def test_user_list_tenant_id_other_than_self_returns_permission_denied(
        self,
    ):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.list",
            params={"tenant_id": str(uuid4())},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        # The caller is not a superuser, so a foreign tenant_id is rejected.
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @patch("mcp_server.tools.users.User.objects")
    def test_user_list_pure_tenant_admin_can_list(self, mock_user_objects):
        """Fix Round 1 (I-4): a pure tenant-admin (no workspace-level
        ``UserRole(admin)``, so ``_check_admin`` denies) must still be able
        to call ``user.list`` — every other tool in this group already
        accepts EITHER workspace-admin OR tenant-admin standing; ``user.list``
        was the sole tool left on the workspace-only gate.
        """
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True

        caller = MagicMock()
        caller.is_superuser = False
        list_qs = MagicMock()
        u1 = _mock_user(username="alice")
        list_qs.order_by.return_value.__getitem__.return_value = [u1]
        mock_user_objects.filter.side_effect = [
            MagicMock(first=MagicMock(return_value=caller)),
            list_qs,
        ]

        result = group.execute_tool(
            tool_name="user.list",
            params={},
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True, result.message
        assert result.data["count"] == 1


# ---------------------------------------------------------------------------
# user.deactivate
# ---------------------------------------------------------------------------


class TestUserDeactivate:
    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.User.objects")
    def test_user_deactivate_delegates_to_service_and_audits(
        self, mock_user_objects, mock_audit
    ):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = True
        u = _mock_user(is_active=True)
        mock_user_objects.filter.return_value.first.return_value = u

        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": str(u.id)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["deactivated"] is True
        accounts.deactivate.assert_called_once_with(
            actor_is_tenant_admin=True,
            actor_tenant_id=ADMIN_CTX.tenant_id,
            target_user_id=u.id,
        )
        # A fresh row is re-fetched after the mutation (not refresh_from_db
        # — the pre-mutation `pre_user` object is only used for its
        # `was_active` snapshot, see the handler's docstring).
        assert mock_user_objects.filter.call_count == 2
        # Audit written
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "user.deactivate"
        assert audit_kwargs["operation"] == "user.deactivate"
        assert audit_kwargs["entity_type"] == "User"
        assert audit_kwargs["details"]["was_active"] is True

    @patch("mcp_server.tools.users.User.objects")
    def test_user_deactivate_unknown_user_returns_not_found(
        self, mock_user_objects
    ):
        """The service raises User.DoesNotExist -> NOT_FOUND. It IS still
        called even though the handler's own pre-fetch also found nothing —
        the pre-fetch is informational only (was_active for the audit), not
        a gate (see the ordering-bug fix in the handler's docstring)."""
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = True
        mock_user_objects.filter.return_value.first.return_value = None
        accounts.deactivate.side_effect = User.DoesNotExist()

        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": str(uuid4())},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"
        accounts.deactivate.assert_called_once()

    @patch("mcp_server.tools.users.User.objects")
    def test_user_deactivate_permission_denied_takes_priority_over_not_found(
        self, mock_user_objects
    ):
        """Regression: a non-admin caller targeting a NON-EXISTENT user must
        still get PERMISSION_DENIED, not NOT_FOUND — the service's own
        permission check runs before its existence check, so this handler
        must never short-circuit to NOT_FOUND via its own pre-fetch before
        the service is even called (issue found via
        test_mcp_rbac_role_matrix.py's server-side admin-gate drift test)."""
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = False
        mock_user_objects.filter.return_value.first.return_value = None
        accounts.deactivate.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": str(uuid4())},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @patch("mcp_server.tools.users.User.objects")
    def test_user_deactivate_last_admin_error_maps_to_last_admin(
        self, mock_user_objects
    ):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = True
        u = _mock_user(is_active=True)
        mock_user_objects.filter.return_value.first.return_value = u
        accounts.deactivate.side_effect = LastAdminError(
            scope="tenant", identifier=str(ADMIN_CTX.tenant_id)
        )

        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": str(u.id)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "LAST_ADMIN"

    def test_user_deactivate_missing_user_id_returns_validation_error(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.deactivate",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_deactivate_invalid_uuid_returns_validation_error(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": "not-a-uuid"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    @patch("mcp_server.tools.users.User.objects")
    def test_user_deactivate_does_not_audit_on_failure(
        self, mock_user_objects
    ):
        group, _, _ = _group()
        mock_user_objects.filter.return_value.first.return_value = None

        with patch("mcp_server.tools.users.write_mcp_audit") as mock_audit:
            result = group.execute_tool(
                tool_name="user.deactivate",
                params={"user_id": str(uuid4())},
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        mock_audit.assert_not_called()


# ---------------------------------------------------------------------------
# user.activate
# ---------------------------------------------------------------------------


class TestUserActivate:
    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.User.objects")
    def test_user_activate_delegates_to_service_and_audits(
        self, mock_user_objects, mock_audit
    ):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = True
        u = _mock_user(is_active=True)
        mock_user_objects.filter.return_value.first.return_value = u

        result = group.execute_tool(
            tool_name="user.activate",
            params={"user_id": str(u.id)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["activated"] is True
        accounts.activate.assert_called_once_with(
            actor_is_tenant_admin=True,
            actor_tenant_id=ADMIN_CTX.tenant_id,
            target_user_id=u.id,
        )
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "user.activate"
        assert audit_kwargs["entity_type"] == "User"

    def test_user_activate_maps_service_permission_denied(self):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = False
        accounts.activate.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.activate",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_user_activate_service_does_not_exist_returns_not_found(self):
        group, authz, accounts = _group()
        authz.is_tenant_admin.return_value = True
        accounts.activate.side_effect = User.DoesNotExist()

        result = group.execute_tool(
            tool_name="user.activate",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_user_activate_missing_user_id_returns_validation_error(self):
        group, _, accounts = _group()
        result = group.execute_tool(
            tool_name="user.activate",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        accounts.activate.assert_not_called()


# ---------------------------------------------------------------------------
# user.suspend_role / user.reactivate_role
# ---------------------------------------------------------------------------


class TestUserSuspendRole:
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_user_suspend_role_calls_service_and_audits(self, mock_audit):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.suspend_role.return_value = None

        result = group.execute_tool(
            tool_name="user.suspend_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["suspended"] is True
        authz.suspend_role.assert_called_once_with(
            actor_roles=ADMIN_CTX.active_roles,
            actor_is_tenant_admin=True,
            target_user_id=TARGET_USER_ID,
            workspace_id=WORKSPACE_ID,
            role="viewer",
        )
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "user.suspend_role"
        assert audit_kwargs["entity_type"] == "UserRole"

    def test_user_suspend_role_maps_permission_denied(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = False
        authz.suspend_role.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.suspend_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
            },
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_user_suspend_role_maps_last_admin(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.suspend_role.side_effect = LastAdminError(
            scope="workspace", identifier=str(WORKSPACE_ID)
        )

        result = group.execute_tool(
            tool_name="user.suspend_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "admin",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "LAST_ADMIN"

    def test_user_suspend_role_maps_not_found(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.suspend_role.side_effect = NotFoundError("no such role")

        result = group.execute_tool(
            tool_name="user.suspend_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_user_suspend_role_unknown_role_returns_validation_error(self):
        group, authz, _ = _group()
        result = group.execute_tool(
            tool_name="user.suspend_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "wizard",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        authz.suspend_role.assert_not_called()

    def test_user_suspend_role_missing_workspace_id_returns_validation_error(self):
        group, authz, _ = _group()
        result = group.execute_tool(
            tool_name="user.suspend_role",
            params={"user_id": str(TARGET_USER_ID), "role": "viewer"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        authz.suspend_role.assert_not_called()


class TestUserReactivateRole:
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_user_reactivate_role_calls_service_and_audits(self, mock_audit):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.reactivate_role.return_value = None

        result = group.execute_tool(
            tool_name="user.reactivate_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["reactivated"] is True
        authz.reactivate_role.assert_called_once_with(
            actor_roles=ADMIN_CTX.active_roles,
            actor_is_tenant_admin=True,
            target_user_id=TARGET_USER_ID,
            workspace_id=WORKSPACE_ID,
            role="viewer",
        )
        mock_audit.assert_called_once()

    def test_user_reactivate_role_maps_permission_denied(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = False
        authz.reactivate_role.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.reactivate_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
            },
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_user_reactivate_role_maps_not_found(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.reactivate_role.side_effect = NotFoundError("no such role")

        result = group.execute_tool(
            tool_name="user.reactivate_role",
            params={
                "user_id": str(TARGET_USER_ID),
                "workspace_id": str(WORKSPACE_ID),
                "role": "viewer",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# user.assign_tenant_admin / user.revoke_tenant_admin
# ---------------------------------------------------------------------------


class TestUserAssignTenantAdmin:
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_user_assign_tenant_admin_calls_service_and_audits(self, mock_audit):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.assign_tenant_admin.return_value = MagicMock()

        result = group.execute_tool(
            tool_name="user.assign_tenant_admin",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["granted"] is True
        authz.assign_tenant_admin.assert_called_once_with(
            actor_is_tenant_admin=True,
            target_user_id=TARGET_USER_ID,
            tenant_id=ADMIN_CTX.tenant_id,
            assigned_by_user_id=ADMIN_CTX.user_id,
        )
        mock_audit.assert_called_once()

    def test_user_assign_tenant_admin_requires_tenant_admin(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = False
        authz.assign_tenant_admin.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.assign_tenant_admin",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_user_assign_tenant_admin_maps_not_found(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.assign_tenant_admin.side_effect = User.DoesNotExist()

        result = group.execute_tool(
            tool_name="user.assign_tenant_admin",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"


class TestUserRevokeTenantAdmin:
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_user_revoke_tenant_admin_calls_service_and_audits(self, mock_audit):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.revoke_tenant_admin.return_value = None

        result = group.execute_tool(
            tool_name="user.revoke_tenant_admin",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["revoked"] is True
        authz.revoke_tenant_admin.assert_called_once_with(
            actor_is_tenant_admin=True,
            target_user_id=TARGET_USER_ID,
            tenant_id=ADMIN_CTX.tenant_id,
        )
        mock_audit.assert_called_once()

    def test_user_revoke_tenant_admin_requires_tenant_admin(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = False
        authz.revoke_tenant_admin.side_effect = AuthTenancyPermissionDenied()

        result = group.execute_tool(
            tool_name="user.revoke_tenant_admin",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_user_revoke_tenant_admin_maps_last_admin(self):
        group, authz, _ = _group()
        authz.is_tenant_admin.return_value = True
        authz.revoke_tenant_admin.side_effect = LastAdminError(
            scope="tenant", identifier=str(ADMIN_CTX.tenant_id)
        )

        result = group.execute_tool(
            tool_name="user.revoke_tenant_admin",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "LAST_ADMIN"


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


class TestUnknownTool:
    def test_unknown_user_tool_returns_unknown_tool(self):
        group, _, _ = _group()
        result = group.execute_tool(
            tool_name="user.delete_permanently",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# Tool map / constructor wiring
# ---------------------------------------------------------------------------


class TestUsersToolGroupWiring:
    def test_default_constructor_uses_real_services(self):
        group = UsersToolGroup()
        assert isinstance(group._authz_service, AuthorizationService)
        from auth_tenancy.services.user_account import UserAccountService

        assert isinstance(group._accounts, UserAccountService)

    def test_tool_map_has_exactly_nine_entries(self):
        assert set(UsersToolGroup._TOOL_MAP.keys()) == {
            "user.create",
            "user.assign_role",
            "user.list",
            "user.deactivate",
            "user.activate",
            "user.suspend_role",
            "user.reactivate_role",
            "user.assign_tenant_admin",
            "user.revoke_tenant_admin",
        }


# ---------------------------------------------------------------------------
# ToolRegistry wiring
# ---------------------------------------------------------------------------


class TestToolRegistryWiring:
    """The ToolRegistry must register UsersToolGroup under the ``user`` prefix
    and list the eight write tools in ``_WRITE_TOOL_PREFIXES``."""

    def test_user_prefix_is_registered(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        assert "user" in registry._groups
        assert isinstance(registry._groups["user"], UsersToolGroup)

    def test_user_write_tools_are_registered(self):
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        for name in (
            "user.create",
            "user.assign_role",
            "user.deactivate",
            "user.activate",
            "user.suspend_role",
            "user.reactivate_role",
            "user.assign_tenant_admin",
            "user.revoke_tenant_admin",
        ):
            assert name in _WRITE_TOOL_PREFIXES
        # user.list is read-only
        assert "user.list" not in _WRITE_TOOL_PREFIXES

    def test_router_routes_user_prefix(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        router = registry._router
        assert router is not None
        for tool_name in (
            "user.create",
            "user.assign_role",
            "user.list",
            "user.deactivate",
            "user.activate",
            "user.suspend_role",
            "user.reactivate_role",
            "user.assign_tenant_admin",
            "user.revoke_tenant_admin",
        ):
            group, err = router.route(tool_name)
            assert err is None, f"{tool_name} did not route: {err}"
            assert group is registry._groups["user"]

    def test_tenant_admin_elevated_tools_cover_all_new_and_rewired_tools(self):
        """The registry-level write-RBAC bypass (Task 9 gap closure) must
        cover exactly the tools whose handler/service is tenant-admin
        aware — no more, no less."""
        from mcp_server.tool_registry import _TENANT_ADMIN_ELEVATED_USER_TOOLS

        assert _TENANT_ADMIN_ELEVATED_USER_TOOLS == {
            "user.create",
            "user.deactivate",
            "user.activate",
            "user.assign_role",
            "user.suspend_role",
            "user.reactivate_role",
            "user.assign_tenant_admin",
            "user.revoke_tenant_admin",
        }

    @pytest.mark.django_db
    def test_list_tools_advertises_elevated_tools_to_pure_tenant_admin(self):
        """Fix Round 1, I-1: a pure tenant-admin (zero workspace-level
        ``UserRole``, so ``can_write`` resolves False for the coarse
        ``tools/list`` gate) must still see every tool in
        ``_TENANT_ADMIN_ELEVATED_USER_TOOLS`` — they can actually execute
        all 8 of them via ``dispatch_request``'s own ``_is_tenant_admin_exempt``
        bypass, so hiding them from ``tools/list`` was a discoverability bug,
        not a security control.

        Note: ``authz`` here must be set on the registry-level service
        (the 3rd ``_build_registry`` return value), not the ``authz=``
        constructor kwarg — that kwarg only replaces the ``UsersToolGroup``
        handler's own ``_authz_service``, never the one ``list_tools``'s
        ``can_write``/``_is_tenant_admin_exempt`` consult.
        """
        registry, _, authz_svc = _build_registry(roles=())
        # roles=() alone would make _build_registry's default decide_access
        # mock resolve allow=True (its stub only flips to False for an
        # explicit "viewer" role) — override to the realistic case of a
        # caller with no roles/standing that is not permitted to write.
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        authz_svc.is_tenant_admin.return_value = True

        tools = registry.list_tools(api_key=VALID_API_KEY)
        names = {t["name"] for t in tools}

        for elevated_tool in (
            "user.create",
            "user.deactivate",
            "user.activate",
            "user.assign_role",
            "user.suspend_role",
            "user.reactivate_role",
            "user.assign_tenant_admin",
            "user.revoke_tenant_admin",
        ):
            assert elevated_tool in names, (
                f"{elevated_tool} missing from tools/list for a pure "
                f"tenant-admin caller: {sorted(names)}"
            )
        # user.list is read-only and always visible regardless of write RBAC.
        assert "user.list" in names

    @pytest.mark.django_db
    def test_list_tools_still_hides_elevated_tools_from_non_tenant_admin(self):
        """The bypass in the test above must be tenant-admin-specific: a
        caller with neither a workspace role nor tenant-admin standing must
        not see the elevated write tools either."""
        registry, _, authz_svc = _build_registry(roles=())
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        authz_svc.is_tenant_admin.return_value = False

        tools = registry.list_tools(api_key=VALID_API_KEY)
        names = {t["name"] for t in tools}

        for elevated_tool in (
            "user.create",
            "user.deactivate",
            "user.activate",
            "user.assign_role",
            "user.suspend_role",
            "user.reactivate_role",
            "user.assign_tenant_admin",
            "user.revoke_tenant_admin",
        ):
            assert elevated_tool not in names, (
                f"{elevated_tool} wrongly advertised to a caller with no "
                f"write standing at all: {sorted(names)}"
            )
        assert "user.list" in names


# ---------------------------------------------------------------------------
# E2E — JSON-RPC pipeline (mocked auth/authz services)
# ---------------------------------------------------------------------------


TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
API_KEY_ID = UUID("00000000-0000-0000-0000-000000000003")


def _claims(roles=("admin",)):
    return IdentityClaims(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=API_KEY_ID,
    )


def _build_registry(*, roles=("admin",), authz: MagicMock | None = None):
    """Build a ToolRegistry with mocked auth services and the real
    UsersToolGroup registered (with optionally mocked AuthorizationService)."""
    auth_svc = MagicMock()
    auth_svc.validate_api_key.return_value = _claims(roles=roles)

    authz_svc = MagicMock()
    authz_svc.active_roles_for.return_value = roles
    authz_svc.active_roles_across_workspaces.return_value = roles
    authz_svc.decide_access.return_value = MagicMock(allow=("viewer" not in roles))
    authz_svc.is_tenant_admin.return_value = False

    registry = ToolRegistry(
        auth_service=auth_svc,
        authz_service=authz_svc,
        workspace_exists=lambda workspace_id: True,
    )
    registry._ensure_groups()

    if authz is not None:
        registry._groups["user"]._authz_service = authz
    return registry, auth_svc, authz_svc


def _post(handler, method, params, *, request_id: int = 1, api_key: str = VALID_API_KEY):
    body = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
        "params": {"api_key": api_key, **params},
    }).encode()
    return handler.handle_http_request(body=body)


def _handler(registry: ToolRegistry) -> ProtocolHandler:
    return ProtocolHandler(tool_registry=registry)


# ``django_db``: these E2E classes drive the real
# ``ToolRegistry.dispatch_request``, which arms the PostgreSQL RLS session
# variable via ``persistence.middleware.set_request_tenant`` (``SET
# app.current_tenant``, COMP-PL-006 / fix #110) and resets it in the
# ``finally``. That is a real DB round-trip on the production path, so the
# tests need DB access even though every collaborator below is mocked.
@pytest.mark.django_db
class TestE2EUserList:
    @patch("mcp_server.tools.users.User.objects")
    def test_successful_list_returns_jsonrpc_result(self, mock_user_objects):
        # First filter call = caller lookup; second = tenant query.
        caller = MagicMock()
        caller.is_superuser = False
        list_qs = MagicMock()
        u1 = _mock_user(username="alice")
        u2 = _mock_user(username="bob")
        list_qs.order_by.return_value.__getitem__.return_value = [u1, u2]
        mock_user_objects.filter.side_effect = [
            MagicMock(first=MagicMock(return_value=caller)),
            list_qs,
        ]

        registry, _, _ = _build_registry()
        handler = _handler(registry)

        response = _post(
            handler,
            "user.list",
            {"workspace_id": str(WORKSPACE_ID)},
        )

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert response["result"]["count"] == 2
        assert len(response["result"]["users"]) == 2

    def test_list_with_viewer_role_returns_permission_denied(self):
        registry, _, authz_svc = _build_registry(roles=("viewer",))
        # The registry's _check_rbac must deny viewer writes, but user.list
        # is a read tool and so passes the registry gate; the admin gate
        # inside the handler denies it.
        authz_svc.decide_access.return_value = MagicMock(allow=True)
        handler = _handler(registry)

        response = _post(
            handler,
            "user.list",
            {"workspace_id": str(WORKSPACE_ID)},
        )

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]

    def test_list_with_invalid_api_key_returns_auth_failed(self):
        registry, auth_svc, _ = _build_registry()
        auth_svc.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")
        handler = _handler(registry)

        response = _post(
            handler,
            "user.list",
            {"workspace_id": str(WORKSPACE_ID)},
            api_key="reqlo_bad_key",
        )

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["AUTH_FAILED"]


@pytest.mark.django_db
class TestE2EUserCreate:
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_successful_create_returns_jsonrpc_result(self, mock_audit):
        authz = MagicMock()
        authz.is_tenant_admin.return_value = True
        registry, _, _ = _build_registry(authz=authz)
        registry._groups["user"]._accounts = MagicMock()
        created = _mock_user(
            id_val=UUID("00000000-0000-0000-0000-0000000000d1"),
            username="newbie",
        )
        registry._groups["user"]._accounts.create.return_value = created
        handler = _handler(registry)

        response = _post(
            handler,
            "user.create",
            {
                "username": "newbie",
                "email": "newbie@test.local",
                "password": "abcdefgh",
            },
        )

        assert "result" in response
        assert "error" not in response
        assert response["result"]["user"]["username"] == "newbie"
        mock_audit.assert_called_once()

    def test_create_with_editor_role_and_no_tenant_admin_returns_permission_denied(self):
        authz = MagicMock()
        authz.is_tenant_admin.return_value = False
        registry, _, _ = _build_registry(roles=("editor",), authz=authz)
        registry._groups["user"]._accounts = MagicMock()
        registry._groups["user"]._accounts.create.side_effect = (
            AuthTenancyPermissionDenied()
        )
        handler = _handler(registry)

        response = _post(
            handler,
            "user.create",
            {
                "username": "x",
                "email": "x@y.z",
                "password": "abcdefgh",
            },
        )

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]


@pytest.mark.django_db
class TestE2EUserAssignRole:
    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_successful_assign_role_returns_jsonrpc_result(
        self, mock_set_tenant, mock_userrole_objects, mock_audit
    ):
        authz = MagicMock()
        authz.assign_role.return_value = _mock_user_role(role="editor")
        mock_userrole_objects.filter.return_value.exists.return_value = True

        registry, _, _ = _build_registry(authz=authz)
        handler = _handler(registry)

        response = _post(
            handler,
            "user.assign_role",
            {
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(TARGET_USER_ID),
                "role": "editor",
                "preset": "extended",
            },
        )

        assert "result" in response
        assert "error" not in response
        assert response["result"]["assignment"]["role"] == "editor"
        authz.assign_role.assert_called_once()
        mock_audit.assert_called_once()


@pytest.mark.django_db
class TestE2EUserDeactivate:
    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.User.objects")
    def test_successful_deactivate_returns_jsonrpc_result(
        self, mock_user_objects, mock_audit
    ):
        authz = MagicMock()
        authz.is_tenant_admin.return_value = True
        u = _mock_user(is_active=True)
        mock_user_objects.filter.return_value.first.return_value = u

        registry, _, _ = _build_registry(authz=authz)
        registry._groups["user"]._accounts = MagicMock()
        handler = _handler(registry)

        response = _post(
            handler,
            "user.deactivate",
            {"user_id": str(u.id)},
        )

        assert "result" in response
        assert "error" not in response
        assert response["result"]["deactivated"] is True
        mock_audit.assert_called_once()


# ---------------------------------------------------------------------------
# E2E — REAL services, real DB fixtures (Task 9 gap closure proof).
#
# Everything above mocks AuthorizationService/UserAccountService, so it
# proves the MCP-layer WIRING is correct but can never prove the actual
# security-relevant claim: that a pure tenant-admin (only a TenantRole,
# zero workspace-level UserRole anywhere) can reach and succeed at these
# tools THROUGH the full pipeline — including the registry-level Step 3
# write-RBAC gate (mcp_server.tool_registry.ToolRegistry.dispatch_request),
# which is completely bypassed by every test above (they call
# ``group.execute_tool()`` directly or drive a registry with mocked
# ``authz_service``/``auth_service``). These tests use the REAL
# ``ToolRegistry()`` (default, unmocked collaborators) with real DB rows.
# ---------------------------------------------------------------------------


def _make_bare_user_and_key(tenant: Tenant, *, label: str) -> tuple[User, str]:
    """Create a user with NO roles at all (no UserRole, no TenantRole)."""
    suffix = uuid4().hex[:8]
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=f"e2e-{label}-{suffix}",
            email=f"e2e-{label}-{suffix}@e2e.test",
            tenant=tenant,
            is_active=True,
        )
    finally:
        clear_request_tenant()
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=f"e2e-{label}-key-{suffix}",
        key_hash=hash_api_key(plaintext),
        revoked_at=None,
    )
    return user, plaintext


def _make_pure_tenant_admin_and_key(tenant: Tenant, *, label: str = "pure-tenant-admin") -> tuple[User, str]:
    """Create a user holding ONLY a TenantRole(admin) — zero UserRole anywhere."""
    user, plaintext = _make_bare_user_and_key(tenant, label=label)
    TenantRole.unscoped.create(
        tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN, suspended_at=None
    )
    return user, plaintext


@pytest.mark.django_db
class TestE2ERealTenantAdminElevation:
    """Real AuthorizationService/UserAccountService, real ToolRegistry."""

    def test_pure_tenant_admin_can_assign_role(
        self, e2e_tenant, e2e_workspace, e2e_user_viewer
    ):
        _, api_key = _make_pure_tenant_admin_and_key(e2e_tenant)
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.assign_role",
            {
                "workspace_id": str(e2e_workspace.id),
                "user_id": str(e2e_user_viewer.id),
                "role": "editor",
                "preset": "extended",
            },
            api_key=api_key,
        )
        assert "result" in response, response
        assert response["result"]["assignment"]["role"] == "editor"

    def test_bare_caller_denied_assign_role(
        self, e2e_tenant, e2e_workspace, e2e_user_viewer
    ):
        """Neither workspace role, tenant-admin, nor bootstrap eligibility."""
        _, api_key = _make_bare_user_and_key(e2e_tenant, label="bare")
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.assign_role",
            {
                "workspace_id": str(e2e_workspace.id),
                "user_id": str(e2e_user_viewer.id),
                "role": "editor",
                "preset": "extended",
            },
            api_key=api_key,
        )
        assert "error" in response, response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]

    def test_pure_tenant_admin_can_suspend_and_reactivate_role(
        self, e2e_tenant, e2e_workspace, e2e_user_viewer, e2e_userrole_viewer
    ):
        _, api_key = _make_pure_tenant_admin_and_key(e2e_tenant)
        handler = _handler(ToolRegistry())

        suspend_resp = _post(
            handler,
            "user.suspend_role",
            {
                "workspace_id": str(e2e_workspace.id),
                "user_id": str(e2e_user_viewer.id),
                "role": "viewer",
            },
            api_key=api_key,
        )
        assert "result" in suspend_resp, suspend_resp
        assert suspend_resp["result"]["suspended"] is True

        reactivate_resp = _post(
            handler,
            "user.reactivate_role",
            {
                "workspace_id": str(e2e_workspace.id),
                "user_id": str(e2e_user_viewer.id),
                "role": "viewer",
            },
            api_key=api_key,
        )
        assert "result" in reactivate_resp, reactivate_resp
        assert reactivate_resp["result"]["reactivated"] is True

    def test_bare_caller_denied_suspend_role(
        self, e2e_tenant, e2e_workspace, e2e_user_viewer, e2e_userrole_viewer
    ):
        _, api_key = _make_bare_user_and_key(e2e_tenant, label="bare-suspend")
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.suspend_role",
            {
                "workspace_id": str(e2e_workspace.id),
                "user_id": str(e2e_user_viewer.id),
                "role": "viewer",
            },
            api_key=api_key,
        )
        assert "error" in response, response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]

    def test_bare_caller_denied_reactivate_role(
        self, e2e_tenant, e2e_workspace, e2e_user_viewer, e2e_userrole_viewer
    ):
        _, api_key = _make_bare_user_and_key(e2e_tenant, label="bare-reactivate")
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.reactivate_role",
            {
                "workspace_id": str(e2e_workspace.id),
                "user_id": str(e2e_user_viewer.id),
                "role": "viewer",
            },
            api_key=api_key,
        )
        assert "error" in response, response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]

    def test_pure_tenant_admin_can_create_and_deactivate_and_activate_user(
        self, e2e_tenant
    ):
        _, api_key = _make_pure_tenant_admin_and_key(e2e_tenant, label="pure-admin-crud")
        handler = _handler(ToolRegistry())

        create_resp = _post(
            handler,
            "user.create",
            {
                "username": f"e2e-created-{uuid4().hex[:8]}",
                "email": f"e2e-created-{uuid4().hex[:8]}@e2e.test",
                "password": "a-real-password-123",
            },
            api_key=api_key,
        )
        assert "result" in create_resp, create_resp
        new_user_id = create_resp["result"]["user"]["id"]

        deactivate_resp = _post(
            handler, "user.deactivate", {"user_id": new_user_id}, api_key=api_key
        )
        assert "result" in deactivate_resp, deactivate_resp
        assert deactivate_resp["result"]["user"]["is_active"] is False

        activate_resp = _post(
            handler, "user.activate", {"user_id": new_user_id}, api_key=api_key
        )
        assert "result" in activate_resp, activate_resp
        assert activate_resp["result"]["user"]["is_active"] is True

    def test_bare_caller_denied_create(self, e2e_tenant):
        _, api_key = _make_bare_user_and_key(e2e_tenant, label="bare-create")
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.create",
            {
                "username": f"e2e-denied-{uuid4().hex[:8]}",
                "email": f"e2e-denied-{uuid4().hex[:8]}@e2e.test",
                "password": "a-real-password-123",
            },
            api_key=api_key,
        )
        assert "error" in response, response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]

    def test_pure_tenant_admin_can_grant_and_revoke_tenant_admin(
        self, e2e_tenant, e2e_user_viewer
    ):
        _, api_key = _make_pure_tenant_admin_and_key(e2e_tenant, label="grantor")
        handler = _handler(ToolRegistry())

        grant_resp = _post(
            handler,
            "user.assign_tenant_admin",
            {"user_id": str(e2e_user_viewer.id)},
            api_key=api_key,
        )
        assert "result" in grant_resp, grant_resp
        assert grant_resp["result"]["granted"] is True

        revoke_resp = _post(
            handler,
            "user.revoke_tenant_admin",
            {"user_id": str(e2e_user_viewer.id)},
            api_key=api_key,
        )
        assert "result" in revoke_resp, revoke_resp
        assert revoke_resp["result"]["revoked"] is True

    def test_bare_caller_denied_assign_tenant_admin(self, e2e_tenant, e2e_user_viewer):
        _, api_key = _make_bare_user_and_key(e2e_tenant, label="bare-tenant-admin")
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.assign_tenant_admin",
            {"user_id": str(e2e_user_viewer.id)},
            api_key=api_key,
        )
        assert "error" in response, response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]


@pytest.mark.django_db
class TestE2ERealAuditPersistence:
    """Fix Round 1, C-1: prove a real ``AuditEntry`` row is written.

    Every other test in this file (including the "real service" E2E classes
    above) patches ``mcp_server.tools.users.write_mcp_audit`` and only
    asserts it was CALLED — which is exactly why C-1 shipped invisibly: the
    5 new tools' ``operation=`` literals were missing from
    ``AuditEntry.OP_CHOICES``, so ``write_mcp_audit`` silently swallowed the
    resulting ``ValidationError`` (logged, never raised) and wrote zero
    rows, while every mocked-call assertion still passed. These tests do
    NOT patch ``write_mcp_audit`` — they drive the real, unmocked
    ``ToolRegistry()`` end to end and query ``audit.models.AuditEntry``
    directly to prove a genuine row landed in the database.
    """

    def test_assign_tenant_admin_writes_a_real_audit_row(
        self, e2e_tenant, e2e_user_viewer
    ):
        from audit.models import AuditEntry

        _, api_key = _make_pure_tenant_admin_and_key(
            e2e_tenant, label="audit-grantor"
        )
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.assign_tenant_admin",
            {"user_id": str(e2e_user_viewer.id)},
            api_key=api_key,
        )
        assert "result" in response, response
        assert response["result"]["granted"] is True

        rows = list(
            AuditEntry.unscoped.filter(
                op="user.assign_tenant_admin",
                entity_id=e2e_user_viewer.id,
            )
        )
        assert len(rows) == 1, (
            "expected exactly one AuditEntry row for "
            f"user.assign_tenant_admin/{e2e_user_viewer.id}, found {len(rows)}"
        )
        assert rows[0].source == AuditEntry.SOURCE_MCP
        assert rows[0].entity_type == "TenantRole"

    def test_suspend_role_writes_a_real_audit_row(
        self, e2e_tenant, e2e_workspace, e2e_user_viewer, e2e_userrole_viewer
    ):
        from audit.models import AuditEntry

        _, api_key = _make_pure_tenant_admin_and_key(
            e2e_tenant, label="audit-suspender"
        )
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.suspend_role",
            {
                "workspace_id": str(e2e_workspace.id),
                "user_id": str(e2e_user_viewer.id),
                "role": "viewer",
            },
            api_key=api_key,
        )
        assert "result" in response, response
        assert response["result"]["suspended"] is True

        rows = list(
            AuditEntry.unscoped.filter(
                op="user.suspend_role",
                entity_id=e2e_user_viewer.id,
            )
        )
        assert len(rows) == 1, (
            "expected exactly one AuditEntry row for "
            f"user.suspend_role/{e2e_user_viewer.id}, found {len(rows)}"
        )
        assert rows[0].source == AuditEntry.SOURCE_MCP
        assert rows[0].entity_type == "UserRole"


@pytest.mark.django_db
class TestE2ERealLastAdminGuard:
    """Real service, real DB — the last-admin invariant end to end."""

    def test_deactivate_blocked_for_last_tenant_admin(self, e2e_tenant):
        admin_user, api_key = _make_pure_tenant_admin_and_key(
            e2e_tenant, label="lone-tenant-admin"
        )
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.deactivate",
            {"user_id": str(admin_user.id)},
            api_key=api_key,
        )
        assert "error" in response, response
        assert response["error"]["code"] == ERROR_CODE_MAP["LAST_ADMIN"]

        set_request_tenant(e2e_tenant.id)
        try:
            admin_user.refresh_from_db()
        finally:
            clear_request_tenant()
        assert admin_user.is_active is True

    def test_revoke_tenant_admin_blocked_for_last_tenant_admin(self, e2e_tenant):
        admin_user, api_key = _make_pure_tenant_admin_and_key(
            e2e_tenant, label="lone-revoke-admin"
        )
        handler = _handler(ToolRegistry())

        response = _post(
            handler,
            "user.revoke_tenant_admin",
            {"user_id": str(admin_user.id)},
            api_key=api_key,
        )
        assert "error" in response, response
        assert response["error"]["code"] == ERROR_CODE_MAP["LAST_ADMIN"]
