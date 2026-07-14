"""
Tests for COMP-MC-011 UsersToolGroup (REQ-L1-046 admin user-management).

Covers the four MCP tools exposed under the ``user.*`` namespace:

* user.create       — write, admin-gated, audited, error mapping
* user.assign_role  — write, admin-gated, audited, error mapping,
                      reuses AuthorizationService.assign_role
* user.list         — read,  admin-gated, error mapping
* user.deactivate   — write, admin-gated, audited, error mapping

Plus wiring tests: tool map, write-prefix registration, namespace routing
via the real ``ToolRegistry`` and ``ProtocolHandler`` E2E pipeline.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4


from auth_tenancy.context import AuthContext, AuthMethod, IdentityClaims
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import ROLE_ADMIN, ROLE_VIEWER
from auth_tenancy.services import AuthorizationService

from application.base import (
    NotFoundError,
    PermissionDeniedError,
)

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

VALID_API_KEY = "rf_test_admin_key"
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
    suspended_at = None,
) -> MagicMock:
    """Build a MagicMock that mimics an auth_tenancy.UserRole ORM instance."""
    ur = MagicMock()
    ur.id = id_val or USER_ROLE_ID
    ur.user_id = user_id or TARGET_USER_ID
    ur.workspace_id = workspace_id or WORKSPACE_ID
    ur.role = role
    ur.suspended_at = suspended_at
    return ur


def _group(authz: MagicMock | None = None) -> tuple:
    """Build a UsersToolGroup with a mocked AuthorizationService."""
    svc = authz or MagicMock()
    return UsersToolGroup(authz_service=svc), svc


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
# Common admin gate (all four handlers)
# ---------------------------------------------------------------------------


class TestAdminGate:
    """The admin gate fires for every handler in the group, before any
    service is invoked."""

    def test_user_create_with_editor_role_returns_permission_denied(self):
        group, authz = _group()
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
        authz.assign_role.assert_not_called()

    def test_user_list_with_viewer_role_returns_permission_denied(self):
        group, _ = _group()
        result = group.execute_tool(
            tool_name="user.list",
            params={},
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_user_deactivate_with_editor_role_returns_permission_denied(self):
        group, _ = _group()
        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": str(TARGET_USER_ID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_user_assign_role_with_viewer_role_returns_permission_denied(self):
        group, authz = _group()
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
        authz.assign_role.assert_not_called()


# ---------------------------------------------------------------------------
# user.create
# ---------------------------------------------------------------------------


class TestUserCreate:
    @patch("mcp_server.tools.users.User.objects")
    @patch("mcp_server.tools.users.Tenant.objects")
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_user_create_hashes_password_and_audits(
        self, mock_audit, mock_tenant_objects, mock_user_objects
    ):
        group, _ = _group()
        # Tenant lookup returns a Tenant
        tenant = MagicMock()
        tenant.id = ADMIN_CTX.tenant_id
        mock_tenant_objects.filter.return_value.first.return_value = tenant
        # Uniqueness pre-checks pass
        mock_user_objects.filter.return_value.exists.return_value = False
        # Create returns a new user
        created = _mock_user(
            id_val=UUID("00000000-0000-0000-0000-0000000000d1"),
            username="newbie",
            email="newbie@test.local",
        )
        mock_user_objects.create.return_value = created

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
        # set_password was called with the plaintext
        created.set_password.assert_called_once_with("abcdefgh")
        created.save.assert_called_once()
        # Audit was written
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "user.create"
        assert audit_kwargs["operation"] == "user.create"
        assert audit_kwargs["entity_type"] == "User"
        assert audit_kwargs["details"]["tenant_id"] == str(ADMIN_CTX.tenant_id)

    def test_user_create_missing_username_returns_validation_error(self):
        group, _ = _group()
        result = group.execute_tool(
            tool_name="user.create",
            params={"email": "x@y.z", "password": "abcdefgh"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_create_missing_email_returns_validation_error(self):
        group, _ = _group()
        result = group.execute_tool(
            tool_name="user.create",
            params={"username": "x", "password": "abcdefgh"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_create_short_password_returns_validation_error(self):
        group, _ = _group()
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
        group, _ = _group()
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

    @patch("mcp_server.tools.users.User.objects")
    @patch("mcp_server.tools.users.Tenant.objects")
    def test_user_create_duplicate_username_returns_validation_error(
        self, mock_tenant_objects, mock_user_objects
    ):
        group, _ = _group()
        tenant = MagicMock()
        tenant.id = ADMIN_CTX.tenant_id
        mock_tenant_objects.filter.return_value.first.return_value = tenant

        # First filter (username) returns exists=True; second (email) False
        exists_results = [True, False]
        def exists_side_effect(*args, **kwargs):
            return exists_results.pop(0) if exists_results else False
        mock_user_objects.filter.return_value.exists.side_effect = (
            exists_side_effect
        )

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
        assert "username" in result.message.lower()

    @patch("mcp_server.tools.users.User.objects")
    @patch("mcp_server.tools.users.Tenant.objects")
    def test_user_create_tenant_not_found_returns_not_found(
        self, mock_tenant_objects, mock_user_objects
    ):
        group, _ = _group()
        mock_tenant_objects.filter.return_value.first.return_value = None
        mock_user_objects.filter.return_value.exists.return_value = False

        result = group.execute_tool(
            tool_name="user.create",
            params={
                "username": "x",
                "email": "x@y.z",
                "password": "abcdefgh",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    @patch("mcp_server.tools.users.User.objects")
    @patch("mcp_server.tools.users.Tenant.objects")
    def test_user_create_tenant_id_as_non_superuser_returns_permission_denied(
        self, mock_tenant_objects, mock_user_objects
    ):
        """Non-superuser caller passing tenant_id must be rejected."""
        group, _ = _group()
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
        group, authz = _group()
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
        # Tenant context was set so the userrole query worked
        mock_set_tenant.assert_called_once_with(ADMIN_CTX.tenant_id)
        # Audit was written
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "user.assign_role"
        assert audit_kwargs["entity_type"] == "UserRole"

    @patch("mcp_server.tools.users.UserRole.objects")
    @patch("mcp_server.tools.users.TenantContext.set_tenant")
    def test_user_assign_role_non_member_target_reaches_service_with_false(
        self, mock_set_tenant, mock_userrole_objects
    ):
        group, authz = _group()
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
        group, authz = _group()
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
        group, authz = _group()
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
        group, authz = _group()
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
        group, authz = _group()
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
        group, authz = _group()
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
        group, authz = _group()
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
        group, _ = _group()
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
        group, _ = _group()
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
        group, _ = _group()
        result = group.execute_tool(
            tool_name="user.list",
            params={"is_active": "maybe"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_list_invalid_limit_returns_validation_error(self):
        group, _ = _group()
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
        group, _ = _group()
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
        group, _ = _group()
        result = group.execute_tool(
            tool_name="user.list",
            params={"tenant_id": str(uuid4())},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        # The caller is not a superuser, so a foreign tenant_id is rejected.
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# user.deactivate
# ---------------------------------------------------------------------------


class TestUserDeactivate:
    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.User.objects")
    def test_user_deactivate_sets_is_active_false_and_audits(
        self, mock_user_objects, mock_audit
    ):
        group, _ = _group()
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
        assert result.data["user"]["is_active"] is False
        # The mock's attribute is set to False (mock allows assignment)
        assert u.is_active is False
        u.save.assert_called_once()
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
        group, _ = _group()
        mock_user_objects.filter.return_value.first.return_value = None

        result = group.execute_tool(
            tool_name="user.deactivate",
            params={"user_id": str(uuid4())},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_user_deactivate_missing_user_id_returns_validation_error(self):
        group, _ = _group()
        result = group.execute_tool(
            tool_name="user.deactivate",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_user_deactivate_invalid_uuid_returns_validation_error(self):
        group, _ = _group()
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
        group, _ = _group()
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
# Unknown tool
# ---------------------------------------------------------------------------


class TestUnknownTool:
    def test_unknown_user_tool_returns_unknown_tool(self):
        group, _ = _group()
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
    def test_default_constructor_uses_real_authorization_service(self):
        group = UsersToolGroup()
        assert isinstance(group._authz_service, AuthorizationService)

    def test_tool_map_has_exactly_four_entries(self):
        assert set(UsersToolGroup._TOOL_MAP.keys()) == {
            "user.create",
            "user.assign_role",
            "user.list",
            "user.deactivate",
        }


# ---------------------------------------------------------------------------
# ToolRegistry wiring
# ---------------------------------------------------------------------------


class TestToolRegistryWiring:
    """The ToolRegistry must register UsersToolGroup under the ``user`` prefix
    and list the three write tools in ``_WRITE_TOOL_PREFIXES``."""

    def test_user_prefix_is_registered(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        assert "user" in registry._groups
        assert isinstance(registry._groups["user"], UsersToolGroup)

    def test_user_write_tools_are_registered(self):
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        assert "user.create" in _WRITE_TOOL_PREFIXES
        assert "user.assign_role" in _WRITE_TOOL_PREFIXES
        assert "user.deactivate" in _WRITE_TOOL_PREFIXES
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
        ):
            group, err = router.route(tool_name)
            assert err is None, f"{tool_name} did not route: {err}"
            assert group is registry._groups["user"]


# ---------------------------------------------------------------------------
# E2E — JSON-RPC pipeline
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
    authz_svc.decide_access.return_value = MagicMock(allow=("viewer" not in roles))

    registry = ToolRegistry(auth_service=auth_svc, authz_service=authz_svc)
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
            api_key="rf_bad_key",
        )

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["AUTH_FAILED"]


class TestE2EUserCreate:
    @patch("mcp_server.tools.users.User.objects")
    @patch("mcp_server.tools.users.Tenant.objects")
    @patch("mcp_server.tools.users.write_mcp_audit")
    def test_successful_create_returns_jsonrpc_result(
        self, mock_audit, mock_tenant_objects, mock_user_objects
    ):
        tenant = MagicMock()
        tenant.id = ADMIN_CTX.tenant_id
        mock_tenant_objects.filter.return_value.first.return_value = tenant
        # Configure caller lookup to return a non-superuser
        caller = MagicMock()
        caller.is_superuser = False
        mock_user_objects.filter.return_value.first.return_value = caller
        mock_user_objects.filter.return_value.exists.return_value = False
        created = _mock_user(
            id_val=UUID("00000000-0000-0000-0000-0000000000d1"),
            username="newbie",
        )
        mock_user_objects.create.return_value = created

        registry, _, _ = _build_registry()
        handler = _handler(registry)

        response = _post(
            handler,
            "user.create",
            {
                "workspace_id": str(WORKSPACE_ID),
                "username": "newbie",
                "email": "newbie@test.local",
                "password": "abcdefgh",
            },
        )

        assert "result" in response
        assert "error" not in response
        assert response["result"]["user"]["username"] == "newbie"
        mock_audit.assert_called_once()

    def test_create_with_editor_role_returns_permission_denied(self):
        registry, _, _ = _build_registry(roles=("editor",))
        handler = _handler(registry)

        response = _post(
            handler,
            "user.create",
            {
                "workspace_id": str(WORKSPACE_ID),
                "username": "x",
                "email": "x@y.z",
                "password": "abcdefgh",
            },
        )

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]


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


class TestE2EUserDeactivate:
    @patch("mcp_server.tools.users.write_mcp_audit")
    @patch("mcp_server.tools.users.User.objects")
    def test_successful_deactivate_returns_jsonrpc_result(
        self, mock_user_objects, mock_audit
    ):
        # Configure caller lookup (first filter call) to return a non-superuser
        caller = MagicMock()
        caller.is_superuser = False
        u = _mock_user(is_active=True)
        mock_user_objects.filter.return_value.first.side_effect = [caller, u]

        registry, _, _ = _build_registry()
        handler = _handler(registry)

        response = _post(
            handler,
            "user.deactivate",
            {"workspace_id": str(WORKSPACE_ID), "user_id": str(u.id)},
        )

        assert "result" in response
        assert "error" not in response
        assert response["result"]["deactivated"] is True
        assert response["result"]["user"]["is_active"] is False
        mock_audit.assert_called_once()
