"""
admin_ops — BackupService tests (REQ-L1-046).

Covers:

* admin-gate: every public method rejects editor / viewer / empty-roles.
* input validation: unknown ``backup_type`` raises ``ValueError``.
* integration (DB-backed): create / list / get / delete round-trips,
  AuditLog writes, and the failure-recording path.

The ``dumpdata`` call inside :class:`BackupService.create_backup` is
monkeypatched to a deterministic stub for the integration tests — the
real command would dump the entire test database, which makes
assertions on the file content fragile across schema changes.
"""
from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest
from auth_tenancy.context import AuthContext, AuthMethod

from application.base import PermissionDeniedError
from admin_ops.models import BackupMetadata, BackupStatus, BackupType
from admin_ops.services import BackupService
from admin_ops.services.exceptions import BackupNotFoundError
from admin_ops.services.paths import absolute_backup_path

from .conftest import active_tenant


# ---------------------------------------------------------------------------
# Fixtures local to this file
# ---------------------------------------------------------------------------


@pytest.fixture
def svc() -> BackupService:
    """A fresh, stateless :class:`BackupService` for every test."""
    return BackupService()


@pytest.fixture
def fake_dumpdata(monkeypatch):
    """Stub ``dumpdata`` to write a known, tiny JSON payload.

    Replaces the real Django management command with a closure that
    writes the empty-array JSON ``[]`` to the ``stdout=`` buffer the
    service supplies. Returns the SHA-256 of the stub payload so tests
    can compare it against the row's ``checksum_sha256`` field.
    """

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


# ---------------------------------------------------------------------------
# Unit tests — admin gate (no DB)
# ---------------------------------------------------------------------------


def test_create_backup_rejects_editor(svc, regular_ctx):
    """An editor caller is denied at the gate before any DB write."""
    with pytest.raises(PermissionDeniedError):
        svc.create_backup(regular_ctx)


def test_create_backup_rejects_viewer(svc, viewer_ctx):
    """A viewer caller is denied at the gate before any DB write."""
    with pytest.raises(PermissionDeniedError):
        svc.create_backup(viewer_ctx)


def test_create_backup_rejects_empty_roles(svc, empty_roles_ctx):
    """An empty-roles caller is denied at the gate."""
    with pytest.raises(PermissionDeniedError):
        svc.create_backup(empty_roles_ctx)


def test_list_backups_rejects_editor(svc, regular_ctx):
    """list_backups is admin-only."""
    with pytest.raises(PermissionDeniedError):
        svc.list_backups(regular_ctx)


def test_get_backup_rejects_viewer(svc, viewer_ctx):
    """get_backup is admin-only."""
    with pytest.raises(PermissionDeniedError):
        svc.get_backup(viewer_ctx, uuid4())


def test_delete_backup_rejects_editor(svc, regular_ctx):
    """delete_backup is admin-only."""
    with pytest.raises(PermissionDeniedError):
        svc.delete_backup(regular_ctx, uuid4())


# ---------------------------------------------------------------------------
# Unit tests — read paths (DB-backed, with no rows)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_backup_rejects_unknown_type(svc, admin_ctx, admin_user, tenant_a):
    """An invalid ``backup_type`` raises ValueError before any DB write."""
    with active_tenant(tenant_a), pytest.raises(ValueError):
        svc.create_backup(admin_ctx, backup_type="bogus")
    assert BackupMetadata.objects.count() == 0


@pytest.mark.django_db
def test_list_backups_returns_empty_when_no_rows(svc, admin_ctx, admin_user, tenant_a):
    """With no backups in the table, list_backups returns []."""
    with active_tenant(tenant_a):
        assert svc.list_backups(admin_ctx) == []


@pytest.mark.django_db
def test_get_backup_raises_not_found(svc, admin_ctx, admin_user, tenant_a):
    """An unknown id raises BackupNotFoundError."""
    with active_tenant(tenant_a):
        with pytest.raises(BackupNotFoundError):
            svc.get_backup(admin_ctx, uuid4())


@pytest.mark.django_db
def test_delete_backup_returns_false_for_unknown_id(svc, admin_ctx, admin_user, tenant_a):
    """Deleting a non-existent id returns False (idempotent)."""
    with active_tenant(tenant_a):
        assert svc.delete_backup(admin_ctx, uuid4()) is False


# ---------------------------------------------------------------------------
# Integration tests — DB-backed, exercise the full service surface
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_backup_persists_row_and_file(
    svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir, fake_dumpdata
):
    """create_backup writes the row, the file, the checksum, and an audit entry."""
    with active_tenant(tenant_a):
        row = svc.create_backup(admin_ctx, backup_type=BackupType.FULL)
        # Row-level expectations.
        assert isinstance(row, BackupMetadata)
        assert row.status == BackupStatus.COMPLETED
        assert row.backup_type == BackupType.FULL
        assert row.file_path is not None
        assert row.file_size_bytes is not None and row.file_size_bytes > 0
        assert row.checksum_sha256 == fake_dumpdata
        assert row.completed_at is not None
        assert row.created_by_id == admin_user.id
        # File-level expectations.
        abs_path = absolute_backup_path(row.file_path)
        assert os.path.isfile(abs_path)
        with open(abs_path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == row.checksum_sha256


@pytest.mark.django_db
def test_create_backup_writes_audit_entry(
    svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir, fake_dumpdata
):
    """create_backup produces an AuditEntry with operation_kind='backup.create'."""
    from audit.models import AuditEntry

    with active_tenant(tenant_a):
        row = svc.create_backup(admin_ctx)
        entries = list(
            AuditEntry.objects.filter(
                entity_id=row.id, entity_type="BackupMetadata"
            )
        )
    assert len(entries) == 1
    entry = entries[0]
    assert entry.op == "create"
    assert entry.actor == str(admin_user.id)
    assert entry.actor_type == "user"
    # v1 audit writer ignores ``details``; the operation_kind lives in
    # ``change_reason`` for grep-ability.
    assert entry.change_reason.startswith("backup.create ")
    assert f"backup_type={BackupType.FULL}" in entry.change_reason


@pytest.mark.django_db
def test_create_backup_rejects_invalid_type_audits_nothing(
    svc, admin_ctx, admin_user, tenant_a
):
    """A ValueError on bad type does NOT write an audit row."""
    from audit.models import AuditEntry

    with active_tenant(tenant_a):
        with pytest.raises(ValueError):
            svc.create_backup(admin_ctx, backup_type="bogus")
        # The audit query is inside the active_tenant block so the
        # tenant-isolating manager can resolve the tenant.
        assert (
            AuditEntry.objects.filter(entity_type="BackupMetadata").count()
            == 0
        )


@pytest.mark.django_db
def test_list_backups_returns_rows_newest_first(
    svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir, fake_dumpdata
):
    """list_backups orders by -created_at and respects the limit."""
    with active_tenant(tenant_a):
        first = svc.create_backup(admin_ctx)
        second = svc.create_backup(admin_ctx)
        third = svc.create_backup(admin_ctx)
        rows = svc.list_backups(admin_ctx, limit=10)
    assert [r.id for r in rows] == [third.id, second.id, first.id]


@pytest.mark.django_db
def test_get_backup_returns_row(
    svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir, fake_dumpdata
):
    """get_backup returns the row that was created."""
    with active_tenant(tenant_a):
        created = svc.create_backup(admin_ctx)
        got = svc.get_backup(admin_ctx, created.id)
    assert got.id == created.id
    assert got.status == BackupStatus.COMPLETED


@pytest.mark.django_db
def test_delete_backup_removes_row_file_and_audits(
    svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir, fake_dumpdata
):
    """delete_backup removes the row, the file, and writes a delete audit entry."""
    from audit.models import AuditEntry

    with active_tenant(tenant_a):
        row = svc.create_backup(admin_ctx)
        file_abs = absolute_backup_path(row.file_path)
        assert os.path.isfile(file_abs)

        deleted = svc.delete_backup(admin_ctx, row.id)
        assert deleted is True
        assert not os.path.isfile(file_abs)
        assert not BackupMetadata.objects.filter(pk=row.id).exists()

        delete_entries = list(
            AuditEntry.objects.filter(
                entity_id=row.id,
                entity_type="BackupMetadata",
                op="delete",
            )
        )
    assert len(delete_entries) == 1
    assert delete_entries[0].change_reason.startswith("backup.delete ")


@pytest.mark.django_db
def test_delete_backup_unknown_id_does_not_audit(
    svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir
):
    """A no-op delete does NOT produce an audit row (idempotent)."""
    from audit.models import AuditEntry

    with active_tenant(tenant_a):
        assert svc.delete_backup(admin_ctx, uuid4()) is False
        assert (
            AuditEntry.objects.filter(
                entity_type="BackupMetadata", op="delete"
            ).count()
            == 0
        )


@pytest.mark.django_db
def test_create_backup_records_failure_row_when_dumpdata_raises(
    svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir, monkeypatch
):
    """When dumpdata raises, a 'failed' row is recorded (best-effort)."""

    def boom(*args, **kwargs):
        raise RuntimeError("simulated dumpdata failure")

    monkeypatch.setattr(
        "admin_ops.services.backup_service.call_command", boom
    )

    with active_tenant(tenant_a):
        with pytest.raises(RuntimeError):
            svc.create_backup(admin_ctx)

    # The failure-recording path inserted a row with status='failed'.
    failed = BackupMetadata.objects.filter(status=BackupStatus.FAILED)
    assert failed.count() == 1
    assert "simulated dumpdata failure" in failed.first().error_message
