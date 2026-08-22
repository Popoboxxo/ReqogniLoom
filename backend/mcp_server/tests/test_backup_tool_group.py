"""
Tests for COMP-MC-009 BackupToolGroup (REQ-L1-046).

leaf_id : COMP-MC-009
req_id  : REQ-L1-046 (Disaster Recovery),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Covers:
- admin.backup_create: calls service, audits, error mapping (NOT_FOUND, PERMISSION_DENIED, VALIDATION_ERROR)
- admin.backup_list:   calls service, applies filters, error mapping
- admin.restore:       calls service, audits, captcha mismatch -> VALIDATION_ERROR
- Unknown admin.* tool returns UNKNOWN_TOOL
- Audit is written for every successful write tool, never on read tools
- ToolGroup is registered under the ``admin`` prefix in the registry
- admin.backup_create + admin.restore are registered as write tools
- Workspace-lifecycle AdminToolGroup (workspace.*) still works
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from auth_tenancy.context import AuthContext, AuthMethod, IdentityClaims
from auth_tenancy.errors import AuthenticationFailed

from admin_ops.models import BackupStatus, BackupType
from admin_ops.services import BackupNotFoundError
from application.base import (
    NotFoundError,
    PermissionDeniedError,
)

from mcp_server.protocol_handler import ERROR_CODE_MAP, ProtocolHandler
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.backup import BackupToolGroup


# ---------------------------------------------------------------------------
# Shared fixtures
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

VIEWER_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("viewer",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

VALID_API_KEY = "reqlo_admin_test_key"
BACKUP_UUID = UUID("00000000-0000-0000-0000-000000000099")


def _mock_backup(
    *,
    id_val: UUID = None,
    status_val: str = BackupStatus.COMPLETED,
    backup_type: str = BackupType.FULL,
    file_size_bytes: int = 10,
) -> MagicMock:
    """Build a MagicMock that mimics a BackupMetadata ORM instance."""
    row = MagicMock()
    row.id = id_val or BACKUP_UUID
    row.status = status_val
    row.backup_type = backup_type
    row.file_path = "backups/abc.json"
    row.file_size_bytes = file_size_bytes
    row.checksum_sha256 = "0" * 64
    row.error_message = ""
    row.metadata = {}
    row.completed_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    row.is_restorable = status_val == BackupStatus.COMPLETED
    row.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    row.created_by_id = UUID("00000000-0000-0000-0000-000000000001")
    return row


def _mock_restore_result(*, backup_id: UUID = None) -> MagicMock:
    """Build a MagicMock that mimics a RestoreResult."""
    r = MagicMock()
    r.backup_id = backup_id or BACKUP_UUID
    r.started_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    r.completed_at = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    r.restored_tables = []
    r.rows_per_table = {}
    return r


# ---------------------------------------------------------------------------
# BackupToolGroup tests
# ---------------------------------------------------------------------------


class TestBackupToolGroup:
    """Unit tests for BackupToolGroup DR tools."""

    def _group(self, backup=None, restore=None):
        """Build a BackupToolGroup with mocked services."""
        backup = backup or MagicMock()
        restore = restore or MagicMock()
        return (
            BackupToolGroup(backup_service=backup, restore_service=restore),
            backup,
            restore,
        )

    # ------------------------------------------------------------------
    # admin.backup_create
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.backup.write_mcp_audit")
    def test_backup_create_calls_service_and_audits(self, mock_audit):
        group, backup, _ = self._group()
        row = _mock_backup()
        backup.create_backup.return_value = row

        result = group.execute_tool(
            tool_name="admin.backup_create",
            params={"reason": "pre-upgrade", "backup_type": "full"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["backup"]["id"] == str(BACKUP_UUID)
        backup.create_backup.assert_called_once()
        call_kwargs = backup.create_backup.call_args.kwargs
        assert call_kwargs["backup_type"] == BackupType.FULL
        assert call_kwargs["metadata"] == {"reason": "pre-upgrade"}
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "admin.backup_create"
        assert audit_kwargs["operation"] == "admin.backup_create"
        assert audit_kwargs["entity_type"] == "BackupMetadata"
        assert audit_kwargs["entity_id"] == BACKUP_UUID

    @patch("mcp_server.tools.backup.write_mcp_audit")
    def test_backup_create_uses_full_as_default_type(self, mock_audit):
        group, backup, _ = self._group()
        row = _mock_backup()
        backup.create_backup.return_value = row

        result = group.execute_tool(
            tool_name="admin.backup_create",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        call_kwargs = backup.create_backup.call_args.kwargs
        assert call_kwargs["backup_type"] == BackupType.FULL
        assert call_kwargs["metadata"] == {}

    def test_backup_create_invalid_type_returns_validation_error(self):
        group, backup, _ = self._group()
        result = group.execute_tool(
            tool_name="admin.backup_create",
            params={"backup_type": "super-duper"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        backup.create_backup.assert_not_called()

    def test_backup_create_permission_denied(self):
        group, backup, _ = self._group()
        backup.create_backup.side_effect = PermissionDeniedError(
            "Permission denied: role 'admin' required"
        )

        result = group.execute_tool(
            tool_name="admin.backup_create",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_backup_create_value_error_from_service(self):
        group, backup, _ = self._group()
        backup.create_backup.side_effect = ValueError(
            "Unknown backup_type 'bogus'"
        )

        result = group.execute_tool(
            tool_name="admin.backup_create",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_backup_create_not_found(self):
        group, backup, _ = self._group()
        backup.create_backup.side_effect = NotFoundError("tenant missing")

        result = group.execute_tool(
            tool_name="admin.backup_create",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    # ------------------------------------------------------------------
    # admin.backup_list
    # ------------------------------------------------------------------

    def test_backup_list_returns_200_with_backups(self):
        group, backup, _ = self._group()
        b1 = _mock_backup(id_val=UUID("00000000-0000-0000-0000-000000000001"))
        b2 = _mock_backup(id_val=UUID("00000000-0000-0000-0000-000000000002"))
        backup.list_backups.return_value = [b1, b2]

        result = group.execute_tool(
            tool_name="admin.backup_list",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert "backups" in result.data
        assert len(result.data["backups"]) == 2

    def test_backup_list_with_filters_applied_in_process(self):
        group, backup, _ = self._group()
        b1 = _mock_backup(status_val=BackupStatus.COMPLETED, backup_type=BackupType.FULL)
        b2 = _mock_backup(
            id_val=UUID("00000000-0000-0000-0000-000000000002"),
            status_val=BackupStatus.FAILED,
            backup_type=BackupType.FULL,
        )
        b3 = _mock_backup(
            id_val=UUID("00000000-0000-0000-0000-000000000003"),
            status_val=BackupStatus.COMPLETED,
            backup_type=BackupType.PARTIAL,
        )
        backup.list_backups.return_value = [b1, b2, b3]

        result = group.execute_tool(
            tool_name="admin.backup_list",
            params={"status": "completed", "backup_type": "full"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        ids = [b["id"] for b in result.data["backups"]]
        # Only b1 matches (completed + full).
        assert ids == [str(b1.id)]

    def test_backup_list_with_invalid_status_returns_validation_error(self):
        group, backup, _ = self._group()
        result = group.execute_tool(
            tool_name="admin.backup_list",
            params={"status": "lol"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        backup.list_backups.assert_not_called()

    def test_backup_list_with_invalid_limit_returns_validation_error(self):
        group, backup, _ = self._group()
        result = group.execute_tool(
            tool_name="admin.backup_list",
            params={"limit": "notanumber"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        backup.list_backups.assert_not_called()

    def test_backup_list_with_negative_offset_returns_validation_error(self):
        group, backup, _ = self._group()
        result = group.execute_tool(
            tool_name="admin.backup_list",
            params={"offset": -1},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        backup.list_backups.assert_not_called()

    def test_backup_list_permission_denied(self):
        group, backup, _ = self._group()
        backup.list_backups.side_effect = PermissionDeniedError(
            "Permission denied: role 'admin' required"
        )

        result = group.execute_tool(
            tool_name="admin.backup_list",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    # ------------------------------------------------------------------
    # admin.restore
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.backup.write_mcp_audit")
    def test_restore_calls_service_and_audits(self, mock_audit):
        group, _, restore = self._group()
        restore.restore.return_value = _mock_restore_result()

        result = group.execute_tool(
            tool_name="admin.restore",
            params={
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "RESTORE",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["restore"]["backup_id"] == str(BACKUP_UUID)
        restore.restore.assert_called_once()
        call_kwargs = restore.restore.call_args.kwargs
        assert call_kwargs["backup_id"] == BACKUP_UUID
        assert call_kwargs["confirmation_text"] == "RESTORE"
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "admin.restore"
        assert audit_kwargs["operation"] == "admin.restore"
        assert audit_kwargs["entity_type"] == "BackupRestore"

    def test_restore_captcha_mismatch_returns_validation_error(self):
        """Captcha mismatch is a clean VALIDATION_ERROR — service must NOT be called."""
        group, _, restore = self._group()
        result = group.execute_tool(
            tool_name="admin.restore",
            params={
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "restore",  # lowercase
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "Captcha" in result.message
        restore.restore.assert_not_called()

    def test_restore_captcha_with_trailing_space_returns_validation_error(self):
        group, _, restore = self._group()
        result = group.execute_tool(
            tool_name="admin.restore",
            params={
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "RESTORE ",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        restore.restore.assert_not_called()

    def test_restore_missing_backup_id_returns_validation_error(self):
        group, _, restore = self._group()
        result = group.execute_tool(
            tool_name="admin.restore",
            params={"confirmation_text": "RESTORE"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        restore.restore.assert_not_called()

    def test_restore_invalid_backup_id_returns_validation_error(self):
        group, _, restore = self._group()
        result = group.execute_tool(
            tool_name="admin.restore",
            params={
                "backup_id": "not-a-uuid",
                "confirmation_text": "RESTORE",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        restore.restore.assert_not_called()

    def test_restore_missing_confirmation_text_returns_validation_error(self):
        group, _, restore = self._group()
        result = group.execute_tool(
            tool_name="admin.restore",
            params={"backup_id": str(BACKUP_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        restore.restore.assert_not_called()

    def test_restore_unknown_backup_id_returns_not_found(self):
        group, _, restore = self._group()
        restore.restore.side_effect = BackupNotFoundError(
            f"Backup {BACKUP_UUID} not found."
        )

        result = group.execute_tool(
            tool_name="admin.restore",
            params={
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "RESTORE",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_restore_permission_denied(self):
        group, _, restore = self._group()
        restore.restore.side_effect = PermissionDeniedError(
            "Permission denied: role 'admin' required"
        )

        result = group.execute_tool(
            tool_name="admin.restore",
            params={
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "RESTORE",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_restore_with_invalid_restore_type_returns_validation_error(self):
        group, _, restore = self._group()
        result = group.execute_tool(
            tool_name="admin.restore",
            params={
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "RESTORE",
                "restore_type": "incremental",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        restore.restore.assert_not_called()

    # ------------------------------------------------------------------
    # Unknown tool
    # ------------------------------------------------------------------

    def test_unknown_admin_tool_returns_unknown_tool(self):
        group, _, _ = self._group()
        result = group.execute_tool(
            tool_name="admin.does_not_exist",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# Constructor / wiring tests
# ---------------------------------------------------------------------------


class TestBackupToolGroupWiring:
    def test_default_constructor_uses_real_services(self):
        """Without args, the group instantiates real services."""
        group = BackupToolGroup()
        assert group._backup_service is not None
        assert group._restore_service is not None

    def test_tool_map_has_exactly_three_entries(self):
        """Guard against accidental additions or removals."""
        assert set(BackupToolGroup._TOOL_MAP.keys()) == {
            "admin.backup_create",
            "admin.backup_list",
            "admin.restore",
        }


# ---------------------------------------------------------------------------
# Registry wiring tests
# ---------------------------------------------------------------------------


class TestToolRegistryWiring:
    """The ToolRegistry must register BackupToolGroup under the ``admin`` prefix."""

    def test_admin_prefix_is_registered(self):
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._ensure_groups()
        assert "admin" in registry._groups
        assert isinstance(registry._groups["admin"], BackupToolGroup)

    def test_admin_tools_are_registered_as_write_tools(self):
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        assert "admin.backup_create" in _WRITE_TOOL_PREFIXES
        assert "admin.restore" in _WRITE_TOOL_PREFIXES
        # admin.backup_list is read-only and must NOT be in the write set.
        assert "admin.backup_list" not in _WRITE_TOOL_PREFIXES

    def test_router_routes_admin_prefix(self):
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._ensure_groups()
        router = registry._router
        assert router is not None
        for tool_name in ("admin.backup_create", "admin.backup_list", "admin.restore"):
            group, err = router.route(tool_name)
            assert err is None, f"{tool_name} did not route: {err}"
            assert group is registry._groups["admin"]


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


def _build_registry(*, roles=("admin",), backup=None, restore=None):
    """Build a ToolRegistry with mocked auth services and the real
    BackupToolGroup registered (with optionally mocked inner services).
    """
    auth_svc = MagicMock()
    auth_svc.validate_api_key.return_value = _claims(roles=roles)

    authz_svc = MagicMock()
    authz_svc.active_roles_for.return_value = roles
    authz_svc.decide_access.return_value = MagicMock(allow=("viewer" not in roles))

    registry = ToolRegistry(
        auth_service=auth_svc,
        authz_service=authz_svc,
        workspace_exists=lambda workspace_id: True,
    )
    registry._ensure_groups()

    if backup is not None or restore is not None:
        admin_group = registry._groups["admin"]
        if backup is not None:
            admin_group._backup_service = backup
        if restore is not None:
            admin_group._restore_service = restore
    return registry, auth_svc, authz_svc


def _post(handler: ProtocolHandler, method: str, params: dict, request_id: int = 1, *, api_key: str = VALID_API_KEY):
    """Build a JSON-RPC body and run it through ProtocolHandler.

    The key is supplied via the ``Authorization`` header, not the JSON-RPC
    body: the HTTP transport no longer honours ``params.api_key`` (D-1 /
    REQ-018 — see TestApiKeyTransportRestriction in test_protocol_handler.py).
    """
    body = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
        "params": params,
    }).encode()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {api_key}"}
    return handler.handle_http_request(body=body, headers=headers)


def _handler(registry: ToolRegistry) -> ProtocolHandler:
    return ProtocolHandler(tool_registry=registry)


# ``django_db``: these E2E classes drive the real
# ``ToolRegistry.dispatch_request``, which arms the PostgreSQL RLS session
# variable via ``persistence.middleware.set_request_tenant`` (``SET
# app.current_tenant``, COMP-PL-006 / fix #110) and resets it in the
# ``finally``. That is a real DB round-trip on the production path, so the
# tests need DB access even though every collaborator below is mocked.
@pytest.mark.django_db
class TestE2EAdminBackupCreate:
    @patch("mcp_server.tools.backup.write_mcp_audit")
    def test_successful_create_returns_jsonrpc_result_envelope(self, mock_audit):
        backup = MagicMock()
        backup.create_backup.return_value = _mock_backup()
        registry, _, _ = _build_registry(backup=backup)
        handler = _handler(registry)

        response = _post(
            handler,
            "admin.backup_create",
            {"reason": "pre-upgrade", "backup_type": "full"},
        )

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert "error" not in response
        assert response["result"]["backup"]["id"] == str(BACKUP_UUID)
        mock_audit.assert_called_once()

    def test_create_with_viewer_role_returns_permission_denied(self):
        backup = MagicMock()
        registry, _, authz_svc = _build_registry(roles=("viewer",), backup=backup)
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        handler = _handler(registry)

        response = _post(handler, "admin.backup_create", {})

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]
        backup.create_backup.assert_not_called()

    def test_create_with_invalid_api_key_returns_auth_failed(self):
        backup = MagicMock()
        registry, auth_svc, _ = _build_registry(backup=backup)
        auth_svc.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")
        handler = _handler(registry)

        response = _post(handler, "admin.backup_create", {}, api_key="reqlo_bad_key")

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["AUTH_FAILED"]
        backup.create_backup.assert_not_called()


@pytest.mark.django_db
class TestE2EAdminRestore:
    @patch("mcp_server.tools.backup.write_mcp_audit")
    def test_successful_restore_with_correct_captcha(self, mock_audit):
        restore = MagicMock()
        restore.restore.return_value = _mock_restore_result()
        registry, _, _ = _build_registry(restore=restore)
        handler = _handler(registry)

        response = _post(
            handler,
            "admin.restore",
            {
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "RESTORE",
            },
        )

        assert "result" in response
        assert response["result"]["restore"]["backup_id"] == str(BACKUP_UUID)
        mock_audit.assert_called_once()

    def test_restore_captcha_mismatch_returns_validation_error(self):
        restore = MagicMock()
        registry, _, _ = _build_registry(restore=restore)
        handler = _handler(registry)

        response = _post(
            handler,
            "admin.restore",
            {
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "WRONG",
            },
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["VALIDATION_ERROR"]
        assert "Captcha" in response["error"]["message"]
        restore.restore.assert_not_called()

    def test_restore_missing_confirmation_text_returns_validation_error(self):
        restore = MagicMock()
        registry, _, _ = _build_registry(restore=restore)
        handler = _handler(registry)

        response = _post(
            handler,
            "admin.restore",
            {"backup_id": str(BACKUP_UUID)},
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["VALIDATION_ERROR"]
        restore.restore.assert_not_called()

    def test_restore_with_viewer_role_is_blocked_by_rbac(self):
        restore = MagicMock()
        registry, _, authz_svc = _build_registry(roles=("viewer",), restore=restore)
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        handler = _handler(registry)

        response = _post(
            handler,
            "admin.restore",
            {
                "backup_id": str(BACKUP_UUID),
                "confirmation_text": "RESTORE",
            },
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]
        restore.restore.assert_not_called()
