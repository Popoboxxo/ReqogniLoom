"""
Tests for COMP-MC-008 PermissionsToolGroup (REQ-L1-039).

Covers the four MCP tools exposed under the ``permissions.*`` namespace:

* permissions.set_rule  — write, admin-gated, audited, error mapping
* permissions.list      — read,  admin-gated, error mapping
* permissions.revoke    — write, admin-gated, audited, error mapping
* permissions.check     — read,  any-authenticated, no audit

Plus wiring tests: tool map, write-prefix registration, namespace routing
via the real ``ToolRegistry`` and ``ProtocolHandler`` E2E pipeline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID


from auth_tenancy.context import AuthContext, AuthMethod

from application.base import (
    PermissionDeniedError,
)

from auth_tenancy.models import (
    ITEM_PERMISSION_READ,
    ITEM_PERMISSION_WRITE,
)
from auth_tenancy.services import ItemPermissionService
from auth_tenancy.services.item_permission import PermissionDecision

from mcp_server.tools.permissions import PermissionsToolGroup


# ---------------------------------------------------------------------------
# Shared fixtures / data
# ---------------------------------------------------------------------------


ADMIN_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("admin",),
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

VALID_API_KEY = "rf_test_admin_key"

WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000020")
ARTIFACT_ID = UUID("00000000-0000-0000-0000-000000000030")
PERMISSION_ID = UUID("00000000-0000-0000-0000-000000000040")


def _mock_permission(
    *,
    id_val: UUID = None,
    level: str = ITEM_PERMISSION_READ,
    artifact_id_val = None,
) -> MagicMock:
    p = MagicMock()
    p.id = id_val or PERMISSION_ID
    p.user_id = USER_ID
    p.workspace_id = WORKSPACE_ID
    p.artifact_id = artifact_id_val
    p.permission_level = level
    p.granted_by_id = ADMIN_CTX.user_id
    return p


def _group(service: MagicMock | None = None) -> tuple:
    """Build a PermissionsToolGroup with a mocked service."""
    svc = service or MagicMock()
    return PermissionsToolGroup(service=svc), svc


# ---------------------------------------------------------------------------
# permissions.set_rule
# ---------------------------------------------------------------------------


class TestPermissionsSetRule:
    @patch("mcp_server.tools.permissions.write_mcp_audit")
    def test_set_rule_calls_service_and_audits(self, mock_audit):
        group, svc = _group()
        perm = _mock_permission(level=ITEM_PERMISSION_WRITE)
        svc.grant_permission.return_value = perm

        result = group.execute_tool(
            tool_name="permissions.set_rule",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
                "permission_level": "write",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["permission"]["permission_level"] == ITEM_PERMISSION_WRITE
        svc.grant_permission.assert_called_once()
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "permissions.set_rule"
        assert audit_kwargs["operation"] == "permissions.set_rule"
        assert audit_kwargs["entity_type"] == "ItemPermission"
        assert audit_kwargs["entity_id"] == PERMISSION_ID

    @patch("mcp_server.tools.permissions.write_mcp_audit")
    def test_set_rule_with_artifact_id(self, mock_audit):
        group, svc = _group()
        perm = _mock_permission(level=ITEM_PERMISSION_READ, artifact_id_val=ARTIFACT_ID)
        svc.grant_permission.return_value = perm

        result = group.execute_tool(
            tool_name="permissions.set_rule",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
                "artifact_id": str(ARTIFACT_ID),
                "permission_level": "read",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        # Confirm the service received the artifact_id positional/kwarg.
        kwargs = svc.grant_permission.call_args.kwargs
        assert kwargs["artifact_id"] == ARTIFACT_ID

    def test_set_rule_missing_workspace_id_returns_validation_error(self):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="permissions.set_rule",
            params={"user_id": str(USER_ID), "permission_level": "read"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.grant_permission.assert_not_called()

    def test_set_rule_invalid_uuid_returns_validation_error(self):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="permissions.set_rule",
            params={
                "workspace_id": "not-a-uuid",
                "user_id": str(USER_ID),
                "permission_level": "read",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_set_rule_missing_level_returns_validation_error(self):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="permissions.set_rule",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_set_rule_permission_denied(self):
        group, svc = _group()
        svc.grant_permission.side_effect = PermissionDeniedError("admin required")

        result = group.execute_tool(
            tool_name="permissions.set_rule",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
                "permission_level": "read",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_set_rule_invalid_level_returns_validation_error(self):
        group, svc = _group()
        svc.grant_permission.side_effect = ValueError("Invalid permission level")

        result = group.execute_tool(
            tool_name="permissions.set_rule",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
                "permission_level": "superuser",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# permissions.list
# ---------------------------------------------------------------------------


class TestPermissionsList:
    def test_list_returns_rules(self):
        group, svc = _group()
        p1 = _mock_permission(level=ITEM_PERMISSION_READ)
        p2 = _mock_permission(
            level=ITEM_PERMISSION_WRITE, artifact_id_val=ARTIFACT_ID
        )
        svc.list_permissions.return_value = [p1, p2]

        result = group.execute_tool(
            tool_name="permissions.list",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert len(result.data["permissions"]) == 2
        svc.list_permissions.assert_called_once()

    def test_list_with_artifact_filter_narrows_results(self):
        group, svc = _group()
        p1 = _mock_permission(level=ITEM_PERMISSION_READ)
        p2 = _mock_permission(
            level=ITEM_PERMISSION_WRITE, artifact_id_val=ARTIFACT_ID
        )
        svc.list_permissions.return_value = [p1, p2]

        result = group.execute_tool(
            tool_name="permissions.list",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
                "artifact_id": str(ARTIFACT_ID),
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert len(result.data["permissions"]) == 1
        assert result.data["permissions"][0]["artifact_id"] == str(ARTIFACT_ID)

    def test_list_missing_user_id_returns_validation_error(self):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="permissions.list",
            params={"workspace_id": str(WORKSPACE_ID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.list_permissions.assert_not_called()

    def test_list_permission_denied(self):
        group, svc = _group()
        svc.list_permissions.side_effect = PermissionDeniedError("admin required")
        result = group.execute_tool(
            tool_name="permissions.list",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# permissions.revoke
# ---------------------------------------------------------------------------


class TestPermissionsRevoke:
    @patch("mcp_server.tools.permissions.write_mcp_audit")
    def test_revoke_calls_service_and_audits(self, mock_audit):
        perm = _mock_permission(level=ITEM_PERMISSION_READ)
        with patch(
            "mcp_server.tools.permissions.ItemPermission.unscoped"
        ) as mock_unscoped:
            mock_qs = MagicMock()
            mock_unscoped.filter.return_value = mock_qs
            mock_qs.first.return_value = perm

            group, svc = _group()
            svc.revoke_permission.return_value = True

            result = group.execute_tool(
                tool_name="permissions.revoke",
                params={"permission_id": str(PERMISSION_ID)},
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )

        assert result.success is True
        assert result.data["revoked"] is True
        assert result.data["permission_id"] == str(PERMISSION_ID)
        svc.revoke_permission.assert_called_once()
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "permissions.revoke"
        assert audit_kwargs["entity_id"] == PERMISSION_ID

    def test_revoke_unknown_id_returns_not_found(self):
        with patch(
            "mcp_server.tools.permissions.ItemPermission.unscoped"
        ) as mock_unscoped:
            mock_qs = MagicMock()
            mock_unscoped.filter.return_value = mock_qs
            mock_qs.first.return_value = None

            group, svc = _group()
            result = group.execute_tool(
                tool_name="permissions.revoke",
                params={"permission_id": str(PERMISSION_ID)},
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"
        svc.revoke_permission.assert_not_called()

    def test_revoke_missing_id_returns_validation_error(self):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="permissions.revoke",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.revoke_permission.assert_not_called()

    def test_revoke_permission_denied(self):
        perm = _mock_permission(level=ITEM_PERMISSION_READ)
        with patch(
            "mcp_server.tools.permissions.ItemPermission.unscoped"
        ) as mock_unscoped:
            mock_qs = MagicMock()
            mock_unscoped.filter.return_value = mock_qs
            mock_qs.first.return_value = perm

            group, svc = _group()
            svc.revoke_permission.side_effect = PermissionDeniedError(
                "admin required"
            )
            result = group.execute_tool(
                tool_name="permissions.revoke",
                params={"permission_id": str(PERMISSION_ID)},
                auth_context=EDITOR_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_revoke_service_returns_false_returns_not_found(self):
        perm = _mock_permission(level=ITEM_PERMISSION_READ)
        with patch(
            "mcp_server.tools.permissions.ItemPermission.unscoped"
        ) as mock_unscoped:
            mock_qs = MagicMock()
            mock_unscoped.filter.return_value = mock_qs
            mock_qs.first.return_value = perm

            group, svc = _group()
            svc.revoke_permission.return_value = False
            result = group.execute_tool(
                tool_name="permissions.revoke",
                params={"permission_id": str(PERMISSION_ID)},
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# permissions.check
# ---------------------------------------------------------------------------


class TestPermissionsCheck:
    def test_check_read_at_write_returns_allowed(self):
        group, svc = _group()
        svc.check_permission.return_value = PermissionDecision(
            level=ITEM_PERMISSION_WRITE, reason="artifact-scoped rule grants 'write'"
        )

        result = group.execute_tool(
            tool_name="permissions.check",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "permission_level": "read",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["decision"]["level"] == ITEM_PERMISSION_WRITE
        # write >= read -> allowed
        assert result.data["decision"]["is_allowed"] is True

    def test_check_write_at_read_returns_denied(self):
        group, svc = _group()
        svc.check_permission.return_value = PermissionDecision(
            level=ITEM_PERMISSION_READ, reason="workspace-wide rule grants 'read'"
        )

        result = group.execute_tool(
            tool_name="permissions.check",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "permission_level": "write",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        # read is not >= write -> denied
        assert result.data["decision"]["is_allowed"] is False

    def test_check_deny_returns_denied(self):
        group, svc = _group()
        svc.check_permission.return_value = PermissionDecision(
            level="deny", reason="no rule applies (default deny)"
        )

        result = group.execute_tool(
            tool_name="permissions.check",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "permission_level": "read",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["decision"]["is_allowed"] is False
        assert result.data["decision"]["level"] == "deny"

    def test_check_missing_level_returns_validation_error(self):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="permissions.check",
            params={"workspace_id": str(WORKSPACE_ID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.check_permission.assert_not_called()

    def test_check_invalid_level_returns_validation_error(self):
        group, svc = _group()
        result = group.execute_tool(
            tool_name="permissions.check",
            params={
                "workspace_id": str(WORKSPACE_ID),
                "permission_level": "superuser",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.check_permission.assert_not_called()


# ---------------------------------------------------------------------------
# Wiring / construction
# ---------------------------------------------------------------------------


class TestPermissionsToolGroupWiring:
    def test_default_constructor_uses_real_service(self):
        group = PermissionsToolGroup()
        assert group._service is not None
        assert isinstance(group._service, ItemPermissionService)

    def test_tool_map_has_exactly_four_entries(self):
        assert set(PermissionsToolGroup._TOOL_MAP.keys()) == {
            "permissions.set_rule",
            "permissions.list",
            "permissions.revoke",
            "permissions.check",
        }

    def test_unknown_tool_returns_unknown_tool_error(self):
        group, _ = _group()
        result = group.execute_tool(
            tool_name="permissions.does_not_exist",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_set_rule_and_revoke_are_registered_as_write_prefixes(self):
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        assert "permissions.set_rule" in _WRITE_TOOL_PREFIXES
        assert "permissions.revoke" in _WRITE_TOOL_PREFIXES
        # list and check must NOT be write tools
        assert "permissions.list" not in _WRITE_TOOL_PREFIXES
        assert "permissions.check" not in _WRITE_TOOL_PREFIXES


# ---------------------------------------------------------------------------
# E2E — pipeline: ProtocolHandler -> ToolRegistry -> PermissionsToolGroup
# ---------------------------------------------------------------------------


def _build_registry(*, roles=("admin",), service: MagicMock | None = None):
    """Build a ToolRegistry with mocked auth + the real PermissionsToolGroup."""
    from auth_tenancy.context import IdentityClaims
    from mcp_server.tool_registry import ToolRegistry

    auth_svc = MagicMock()
    auth_svc.validate_api_key.return_value = IdentityClaims(
        user_id=ADMIN_CTX.user_id,
        tenant_id=ADMIN_CTX.tenant_id,
        roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=ADMIN_CTX.api_key_id,
    )

    authz_svc = MagicMock()
    authz_svc.active_roles_for.return_value = roles
    authz_svc.decide_access.return_value = MagicMock(allow=("viewer" not in roles))

    registry = ToolRegistry(auth_service=auth_svc, authz_service=authz_svc)
    registry._ensure_groups()

    if service is not None:
        registry._groups["permissions"]._service = service

    return registry


def _post(handler, method, params, *, request_id: int = 1, api_key: str = VALID_API_KEY):
    import json

    body = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
        "params": {"api_key": api_key, **params},
    }).encode()
    return handler.handle_http_request(body=body)


class TestE2EPermissions:
    @patch("mcp_server.tools.permissions.write_mcp_audit")
    def test_set_rule_e2e_returns_jsonrpc_result(self, mock_audit):
        from mcp_server.protocol_handler import ProtocolHandler

        svc = MagicMock()
        svc.grant_permission.return_value = _mock_permission(
            level=ITEM_PERMISSION_WRITE
        )
        registry = _build_registry(roles=("admin",), service=svc)
        handler = ProtocolHandler(tool_registry=registry)

        response = _post(
            handler,
            "permissions.set_rule",
            {
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
                "permission_level": "write",
            },
        )

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert response["result"]["permission"]["permission_level"] == "write"
        svc.grant_permission.assert_called_once()
        mock_audit.assert_called_once()

    def test_set_rule_e2e_viewer_is_blocked_by_rbac(self):
        from mcp_server.protocol_handler import ProtocolHandler

        svc = MagicMock()
        registry = _build_registry(roles=("viewer",), service=svc)
        # viewer must be denied for write tools
        registry._authz_service.decide_access.return_value = MagicMock(allow=False)
        handler = ProtocolHandler(tool_registry=registry)

        response = _post(
            handler,
            "permissions.set_rule",
            {
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
                "permission_level": "read",
            },
        )

        assert "error" in response
        assert response["error"]["error_code"] == "PERMISSION_DENIED"
        svc.grant_permission.assert_not_called()

    def test_list_e2e_returns_jsonrpc_result(self):
        from mcp_server.protocol_handler import ProtocolHandler

        svc = MagicMock()
        p1 = _mock_permission(level=ITEM_PERMISSION_READ)
        svc.list_permissions.return_value = [p1]
        registry = _build_registry(roles=("admin",), service=svc)
        handler = ProtocolHandler(tool_registry=registry)

        response = _post(
            handler,
            "permissions.list",
            {
                "workspace_id": str(WORKSPACE_ID),
                "user_id": str(USER_ID),
            },
        )

        assert "result" in response
        assert len(response["result"]["permissions"]) == 1

    def test_registry_routes_permissions_prefix_to_permissions_group(self):
        from mcp_server.tools.permissions import PermissionsToolGroup

        registry = _build_registry(roles=("admin",))
        assert isinstance(registry._groups["permissions"], PermissionsToolGroup)
        # Router-level check.
        group, err = registry._router.route("permissions.set_rule")
        assert err is None
        assert group is registry._groups["permissions"]
