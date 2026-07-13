"""
Tests for admin_ops REST endpoints (REQ-L1-046).

Covers the Welle D REST adapter:

* GET  /api/v1/admin/backups/   — list
* POST /api/v1/admin/backups/   — create
* POST /api/v1/admin/restore/   — restore (captcha "RESTORE")
* Error mapping: 400 / 403 / 404

Tests follow the same pattern as ``auth_tenancy/tests/test_item_permission_rest.py``:
the views are constructed directly with a mocked auth context, the services
are patched where useful, and the responses are asserted without spinning up
the full DRF stack. A couple of DB-backed integration tests exercise the
full ``request -> view -> service -> DB`` path.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
import rest_framework
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from admin_ops.models import BackupMetadata, BackupStatus, BackupType
from auth_tenancy.context import AuthContext, AuthMethod
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

from .conftest import active_tenant


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_MOCK_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_MOCK_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
_MOCK_API_KEY_ID = UUID("00000000-0000-0000-0000-000000000003")

VALID_BACKUP_ID = UUID("00000000-0000-0000-0000-000000000099")


def _admin_ctx() -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        api_key_id=_MOCK_API_KEY_ID,
    )


def _editor_ctx() -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        api_key_id=_MOCK_API_KEY_ID,
    )


def _viewer_ctx() -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=("viewer",),
        auth_method=AuthMethod.BEARER_TOKEN,
        api_key_id=_MOCK_API_KEY_ID,
    )


# ---------------------------------------------------------------------------
# Request factory
# ---------------------------------------------------------------------------


def _make_request(method: str, url: str, *, body=None, auth: AuthContext | None = None):
    """Build a DRF Request with auth_context attached."""
    factory = APIRequestFactory()
    if method == "GET":
        raw = factory.get(url)
    elif method == "POST":
        raw = factory.post(url, data=body or {}, format="json")
    else:  # pragma: no cover - only GET/POST needed here
        raise ValueError(method)

    request = Request(raw, parsers=[JSONParser()])
    request.auth_context = auth
    request.parser_context = {"kwargs": {}, "args": (), "view": None}
    return request


def _mock_backup(
    *,
    id_val: UUID = None,
    status_val: str = BackupStatus.COMPLETED,
    backup_type: str = BackupType.FULL,
    file_size_bytes: int = 10,
    is_restorable: bool = True,
) -> MagicMock:
    """Build a MagicMock that mimics a BackupMetadata ORM instance."""
    row = MagicMock()
    row.id = id_val or VALID_BACKUP_ID
    row.status = status_val
    row.backup_type = backup_type
    row.file_path = "backups/abc.json"
    row.file_size_bytes = file_size_bytes
    row.checksum_sha256 = "0" * 64
    row.error_message = ""
    row.metadata = {}
    row.completed_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    row.is_restorable = is_restorable
    row.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    row.created_by_id = _MOCK_USER_ID
    return row


def _mock_restore_result(*, backup_id: UUID = None) -> MagicMock:
    """Build a MagicMock that mimics a RestoreResult."""
    r = MagicMock()
    r.backup_id = backup_id or VALID_BACKUP_ID
    r.started_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    r.completed_at = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    r.restored_tables = []
    r.rows_per_table = {}
    return r


# ---------------------------------------------------------------------------
# Tests — GET /api/v1/admin/backups/
# ---------------------------------------------------------------------------


class TestListBackups:
    """GET /api/v1/admin/backups/"""

    @patch("admin_ops.rest.BackupService")
    def test_list_returns_200_with_backups(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        mock_svc = mock_cls.return_value
        b1 = _mock_backup(id_val=UUID("00000000-0000-0000-0000-000000000001"))
        b2 = _mock_backup(id_val=UUID("00000000-0000-0000-0000-000000000002"))
        mock_svc.list_backups.return_value = [b1, b2]

        view = BackupListCreateView()
        view._service = mock_svc
        request = _make_request(
            "GET", "/api/v1/admin/backups/", auth=_admin_ctx()
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_200_OK
        assert "backups" in response.data
        assert len(response.data["backups"]) == 2
        assert response.data["backups"][0]["id"] == str(b1.id)
        assert response.data["backups"][0]["is_restorable"] is True
        mock_svc.list_backups.assert_called_once()

    @patch("admin_ops.rest.BackupService")
    def test_list_with_status_filter(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        mock_svc = mock_cls.return_value
        b1 = _mock_backup(status_val=BackupStatus.COMPLETED)
        mock_svc.list_backups.return_value = [b1]

        view = BackupListCreateView()
        view._service = mock_svc
        request = _make_request(
            "GET",
            "/api/v1/admin/backups/?status=completed",
            auth=_admin_ctx(),
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["backups"]) == 1

    @patch("admin_ops.rest.BackupService")
    def test_list_with_invalid_status_returns_400(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        view = BackupListCreateView()
        view._service = mock_cls.return_value
        request = _make_request(
            "GET",
            "/api/v1/admin/backups/?status=lol",
            auth=_admin_ctx(),
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("admin_ops.rest.BackupService")
    def test_list_with_invalid_limit_returns_400(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        view = BackupListCreateView()
        view._service = mock_cls.return_value
        request = _make_request(
            "GET",
            "/api/v1/admin/backups/?limit=notanumber",
            auth=_admin_ctx(),
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("admin_ops.rest.BackupService")
    def test_list_non_admin_returns_403(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        mock_svc = mock_cls.return_value
        mock_svc.list_backups.side_effect = PermissionDeniedError(
            "Permission denied: role 'admin' required"
        )

        view = BackupListCreateView()
        view._service = mock_svc
        request = _make_request(
            "GET", "/api/v1/admin/backups/", auth=_editor_ctx()
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Tests — POST /api/v1/admin/backups/
# ---------------------------------------------------------------------------


class TestCreateBackup:
    """POST /api/v1/admin/backups/"""

    @patch("admin_ops.rest.BackupService")
    def test_create_returns_201_with_backup(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        mock_svc = mock_cls.return_value
        row = _mock_backup()
        mock_svc.create_backup.return_value = row

        view = BackupListCreateView()
        view._service = mock_svc
        request = _make_request(
            "POST",
            "/api/v1/admin/backups/",
            body={"reason": "pre-upgrade snapshot"},
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert "backup" in response.data
        assert response.data["backup"]["id"] == str(row.id)
        # Service was called with default backup_type="full" + metadata={"reason": ...}
        call_kwargs = mock_svc.create_backup.call_args.kwargs
        assert call_kwargs["backup_type"] == BackupType.FULL
        assert call_kwargs["metadata"] == {"reason": "pre-upgrade snapshot"}

    @patch("admin_ops.rest.BackupService")
    def test_create_with_explicit_backup_type(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        mock_svc = mock_cls.return_value
        row = _mock_backup(backup_type=BackupType.PARTIAL)
        mock_svc.create_backup.return_value = row

        view = BackupListCreateView()
        view._service = mock_svc
        request = _make_request(
            "POST",
            "/api/v1/admin/backups/",
            body={"backup_type": "partial"},
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_201_CREATED
        call_kwargs = mock_svc.create_backup.call_args.kwargs
        assert call_kwargs["backup_type"] == BackupType.PARTIAL

    @patch("admin_ops.rest.BackupService")
    def test_create_with_invalid_backup_type_returns_400(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        view = BackupListCreateView()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            "/api/v1/admin/backups/",
            body={"backup_type": "super-duper"},
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("admin_ops.rest.BackupService")
    def test_create_with_non_object_body_returns_400(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        view = BackupListCreateView()
        view._service = mock_cls.return_value
        # Use a list as the body — DRF's JSONParser yields a list, not a dict
        factory = APIRequestFactory()
        raw = factory.post("/api/v1/admin/backups/", data=[], format="json")
        request = Request(raw, parsers=[JSONParser()])
        request.auth_context = _admin_ctx()
        request.parser_context = {"kwargs": {}, "args": (), "view": None}

        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("admin_ops.rest.BackupService")
    def test_create_non_admin_returns_403(self, mock_cls):
        from admin_ops.rest import BackupListCreateView

        mock_svc = mock_cls.return_value
        mock_svc.create_backup.side_effect = PermissionDeniedError(
            "Permission denied: role 'admin' required"
        )

        view = BackupListCreateView()
        view._service = mock_svc
        request = _make_request(
            "POST", "/api/v1/admin/backups/", body={}, auth=_editor_ctx()
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Tests — POST /api/v1/admin/restore/
# ---------------------------------------------------------------------------


class TestRestore:
    """POST /api/v1/admin/restore/"""

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_with_correct_captcha_returns_200(self, mock_cls):
        from admin_ops.rest import AdminRestoreView

        mock_svc = mock_cls.return_value
        result = _mock_restore_result()
        mock_svc.restore.return_value = result

        view = AdminRestoreView()
        view._service = mock_svc
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": str(VALID_BACKUP_ID),
                "confirmation_text": "RESTORE",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_200_OK
        assert "restore" in response.data
        assert response.data["restore"]["backup_id"] == str(VALID_BACKUP_ID)
        mock_svc.restore.assert_called_once()
        call_kwargs = mock_svc.restore.call_args.kwargs
        assert call_kwargs["backup_id"] == VALID_BACKUP_ID
        assert call_kwargs["confirmation_text"] == "RESTORE"

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_captcha_mismatch_returns_400(self, mock_cls):
        """Captcha mismatch is a clean 400 — service must NOT be called."""
        from admin_ops.rest import AdminRestoreView

        mock_svc = mock_cls.return_value
        view = AdminRestoreView()
        view._service = mock_svc
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": str(VALID_BACKUP_ID),
                "confirmation_text": "restore",  # lowercase
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"
        assert "Captcha" in response.data["message"]
        mock_svc.restore.assert_not_called()

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_with_trailing_space_captcha_returns_400(self, mock_cls):
        from admin_ops.rest import AdminRestoreView

        mock_svc = mock_cls.return_value
        view = AdminRestoreView()
        view._service = mock_svc
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": str(VALID_BACKUP_ID),
                "confirmation_text": "RESTORE ",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"
        mock_svc.restore.assert_not_called()

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_missing_backup_id_returns_400(self, mock_cls):
        from admin_ops.rest import AdminRestoreView

        view = AdminRestoreView()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={"confirmation_text": "RESTORE"},
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_invalid_backup_id_returns_400(self, mock_cls):
        from admin_ops.rest import AdminRestoreView

        view = AdminRestoreView()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": "not-a-uuid",
                "confirmation_text": "RESTORE",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_missing_confirmation_text_returns_400(self, mock_cls):
        from admin_ops.rest import AdminRestoreView

        view = AdminRestoreView()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={"backup_id": str(VALID_BACKUP_ID)},
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_unknown_backup_id_returns_404(self, mock_cls):
        from admin_ops.rest import AdminRestoreView
        from admin_ops.services import BackupNotFoundError

        mock_svc = mock_cls.return_value
        mock_svc.restore.side_effect = BackupNotFoundError(
            f"Backup {VALID_BACKUP_ID} not found."
        )

        view = AdminRestoreView()
        view._service = mock_svc
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": str(VALID_BACKUP_ID),
                "confirmation_text": "RESTORE",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"] == "NOT_FOUND"

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_non_admin_returns_403(self, mock_cls):
        from admin_ops.rest import AdminRestoreView

        mock_svc = mock_cls.return_value
        mock_svc.restore.side_effect = PermissionDeniedError(
            "Permission denied: role 'admin' required"
        )

        view = AdminRestoreView()
        view._service = mock_svc
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": str(VALID_BACKUP_ID),
                "confirmation_text": "RESTORE",
            },
            auth=_editor_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"] == "PERMISSION_DENIED"

    @patch("admin_ops.rest.AdminRestoreService")
    def test_restore_with_invalid_restore_type_returns_400(self, mock_cls):
        from admin_ops.rest import AdminRestoreView

        view = AdminRestoreView()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": str(VALID_BACKUP_ID),
                "confirmation_text": "RESTORE",
                "restore_type": "incremental",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Tests — required_operation wiring
# ---------------------------------------------------------------------------


class TestRBACWiring:
    """Sanity checks on the DRF permission class wiring."""

    def test_backup_view_declares_workspace_config_operation(self):
        from admin_ops.rest import BackupListCreateView
        from auth_tenancy.services import Operation

        assert BackupListCreateView.required_operation == Operation.WORKSPACE_CONFIG

    def test_restore_view_declares_workspace_config_operation(self):
        from admin_ops.rest import AdminRestoreView
        from auth_tenancy.services import Operation

        assert AdminRestoreView.required_operation == Operation.WORKSPACE_CONFIG

    def test_workspace_config_is_admin_only(self):
        """WORKSPACE_CONFIG is admin-only in the RBAC matrix."""
        from auth_tenancy.services import Operation, AuthorizationService

        authz = AuthorizationService()
        # Editor denied
        editor = authz.decide_access(("editor",), Operation.WORKSPACE_CONFIG)
        assert not editor.allow
        # Viewer denied
        viewer = authz.decide_access(("viewer",), Operation.WORKSPACE_CONFIG)
        assert not viewer.allow
        # Approver denied
        approver = authz.decide_access(("approver",), Operation.WORKSPACE_CONFIG)
        assert not approver.allow
        # Admin allowed
        admin = authz.decide_access(("admin",), Operation.WORKSPACE_CONFIG)
        assert admin.allow


# ---------------------------------------------------------------------------
# Integration tests — DB-backed, exercise the full service surface
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end test: request -> view -> service -> DB."""

    @pytest.fixture
    def fake_dumpdata(self, monkeypatch):
        """Stub ``dumpdata`` for the create-backup integration test."""
        payload = b"[]\n"
        digest = hashlib.sha256(payload).hexdigest()

        def fake_call(*args, **kwargs):
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write(payload.decode("utf-8"))

        monkeypatch.setattr(
            "admin_ops.services.backup_service.call_command", fake_call
        )
        return digest

    @pytest.mark.django_db
    def test_create_then_list_integration(
        self, admin_user, admin_ctx, tenant_a, tmp_backups_dir, fake_dumpdata
    ):
        """POST then GET against the real service."""
        from admin_ops.rest import BackupListCreateView

        with active_tenant(tenant_a):
            view = BackupListCreateView()
            create_req = _make_request(
                "POST",
                "/api/v1/admin/backups/",
                body={"reason": "integration"},
                auth=admin_ctx,
            )
            create_resp = view.post(create_req)
            assert create_resp.status_code == status.HTTP_201_CREATED
            created_id = create_resp.data["backup"]["id"]

            list_req = _make_request(
                "GET", "/api/v1/admin/backups/", auth=admin_ctx
            )
            list_resp = view.get(list_req)
            assert list_resp.status_code == status.HTTP_200_OK
            ids = [b["id"] for b in list_resp.data["backups"]]
            assert created_id in ids

    @pytest.mark.django_db
    def test_restore_integration_captcha_mismatch_does_not_touch_service(
        self, admin_user, admin_ctx, tenant_a, tmp_backups_dir
    ):
        """Captcha mismatch at the REST layer short-circuits the service call."""
        from admin_ops.rest import AdminRestoreView

        view = AdminRestoreView()
        req = _make_request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": str(VALID_BACKUP_ID),
                "confirmation_text": "WRONG",
            },
            auth=admin_ctx,
        )
        resp = view.post(req)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["error"] == "VALIDATION_ERROR"
        # No row was created, no audit row was written.
        with active_tenant(tenant_a):
            from audit.models import AuditEntry
            assert (
                AuditEntry.objects.filter(entity_type="BackupRestore").count()
                == 0
            )
