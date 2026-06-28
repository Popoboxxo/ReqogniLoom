"""
admin_ops — AdminRestoreService tests (REQ-L1-046).

Covers the full restore safety contract:

* admin gate — non-admin callers are rejected.
* captcha gate — ``confirmation_text`` must be the exact ``"RESTORE"``.
* backup-state gate — only ``status='completed'`` rows are restorable.
* integration (DB-backed) — happy path with stubbed loaddata, missing
  file path, and failure path that records a ``restore.fail`` audit row.

The ``loaddata`` call inside :class:`AdminRestoreService.restore` is
monkeypatched for the integration tests so we never touch the real
database.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from application.base import PermissionDeniedError, ValidationError
from admin_ops.models import BackupMetadata, BackupStatus, BackupType
from admin_ops.services import AdminRestoreService, BackupService
from admin_ops.services.admin_restore_service import RESTORE_CAPTCHA
from admin_ops.services.exceptions import BackupNotFoundError

from .conftest import active_tenant


# ---------------------------------------------------------------------------
# Fixtures local to this file
# ---------------------------------------------------------------------------


@pytest.fixture
def restore_svc() -> AdminRestoreService:
    """A fresh, stateless :class:`AdminRestoreService` for every test."""
    return AdminRestoreService()


@pytest.fixture
def fake_loaddata(monkeypatch):
    """Stub ``loaddata`` so the integration tests do not touch the DB.

    Records the path the service passed so the test can assert on it.
    """

    called: list[list[str]] = []

    def fake_call(*args, **kwargs):
        called.append(list(args))

    monkeypatch.setattr(
        "admin_ops.services.admin_restore_service.call_command", fake_call
    )
    return called


@pytest.fixture
def completed_backup(
    admin_user, tenant_a, tmp_backups_dir
) -> BackupMetadata:
    """A pre-existing 'completed' backup row with a real file on disk.

    The on-disk file is a tiny JSON blob (the same shape dumpdata
    produces), and the row's ``checksum_sha256`` / ``file_size_bytes``
    match it exactly. Tests use this fixture to skip the dumpdata step
    and focus on the restore behaviour.

    The ``file_path`` matches what :class:`BackupService.create_backup`
    would store — relative to ``backup_root()``, i.e. just the
    filename. The actual file is created inside the per-test
    MEDIA_ROOT, at ``<MEDIA_ROOT>/backups/<file>``.
    """
    from admin_ops.services.paths import backup_root

    payload = b"[]\n"
    rel_path = f"{uuid4()}.json"
    abs_path = os.path.join(backup_root(), rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as fh:
        fh.write(payload)

    import hashlib

    digest = hashlib.sha256(payload).hexdigest()

    return BackupMetadata.objects.create(
        status=BackupStatus.COMPLETED,
        backup_type=BackupType.FULL,
        file_path=rel_path,
        file_size_bytes=len(payload),
        checksum_sha256=digest,
        completed_at=datetime.now(timezone.utc),
        created_by=admin_user,
    )


# ---------------------------------------------------------------------------
# Unit tests — gates (no DB)
# ---------------------------------------------------------------------------


def test_restore_rejects_editor(restore_svc, regular_ctx, uuid4_call=None):
    """An editor caller is denied at the gate before any DB read."""
    with pytest.raises(PermissionDeniedError):
        restore_svc.restore(
            regular_ctx,
            backup_id=uuid4(),
            confirmation_text=RESTORE_CAPTCHA,
        )


def test_restore_rejects_viewer(restore_svc, viewer_ctx):
    """A viewer caller is denied at the gate."""
    with pytest.raises(PermissionDeniedError):
        restore_svc.restore(
            viewer_ctx,
            backup_id=uuid4(),
            confirmation_text=RESTORE_CAPTCHA,
        )


def test_restore_rejects_empty_roles(restore_svc, empty_roles_ctx):
    """An empty-roles caller is denied at the gate."""
    with pytest.raises(PermissionDeniedError):
        restore_svc.restore(
            empty_roles_ctx,
            backup_id=uuid4(),
            confirmation_text=RESTORE_CAPTCHA,
        )


def test_restore_captcha_mismatch_lowercase(restore_svc, admin_ctx):
    """Lowercase 'restore' fails the captcha (case-sensitive)."""
    with pytest.raises(ValidationError) as exc:
        restore_svc.restore(
            admin_ctx, backup_id=uuid4(), confirmation_text="restore"
        )
    assert "Captcha mismatch" in str(exc.value)


def test_restore_captcha_mismatch_with_trailing_space(restore_svc, admin_ctx):
    """Trailing whitespace fails the captcha (exact match)."""
    with pytest.raises(ValidationError) as exc:
        restore_svc.restore(
            admin_ctx, backup_id=uuid4(), confirmation_text="RESTORE "
        )
    assert "Captcha mismatch" in str(exc.value)


def test_restore_captcha_mismatch_with_extra_punct(restore_svc, admin_ctx):
    """Extra punctuation fails the captcha (exact match)."""
    with pytest.raises(ValidationError) as exc:
        restore_svc.restore(
            admin_ctx, backup_id=uuid4(), confirmation_text="RESTORE!"
        )
    assert "Captcha mismatch" in str(exc.value)


def test_restore_captcha_empty_string(restore_svc, admin_ctx):
    """An empty string fails the captcha."""
    with pytest.raises(ValidationError) as exc:
        restore_svc.restore(
            admin_ctx, backup_id=uuid4(), confirmation_text=""
        )
    assert "Captcha mismatch" in str(exc.value)


def test_restore_captcha_mismatch_does_not_audit(
    restore_svc, admin_ctx, admin_user, tenant_a
):
    """A captcha-mismatch rejection writes no audit row."""
    from audit.models import AuditEntry

    with active_tenant(tenant_a):
        with pytest.raises(ValidationError):
            restore_svc.restore(
                admin_ctx, backup_id=uuid4(), confirmation_text="WRONG"
            )
        # The audit query is still inside the active_tenant block so
        # the tenant-isolating manager can resolve the tenant.
        assert (
            AuditEntry.objects.filter(entity_type="BackupRestore").count()
            == 0
        )


# ---------------------------------------------------------------------------
# Integration tests — DB-backed, exercise the full service surface
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_restore_raises_not_found_for_unknown_id(
    restore_svc, admin_ctx, admin_user, tenant_a
):
    """An unknown id raises BackupNotFoundError (after captcha passes)."""
    with active_tenant(tenant_a):
        with pytest.raises(BackupNotFoundError):
            restore_svc.restore(
                admin_ctx,
                backup_id=uuid4(),
                confirmation_text=RESTORE_CAPTCHA,
            )


@pytest.mark.django_db
def test_restore_refuses_pending_backup(
    restore_svc, admin_ctx, admin_user, tenant_a
):
    """A 'pending' backup is not restorable."""
    pending = BackupMetadata.objects.create(
        status=BackupStatus.PENDING,
        backup_type=BackupType.FULL,
    )
    with active_tenant(tenant_a):
        with pytest.raises(BackupNotFoundError) as exc:
            restore_svc.restore(
                admin_ctx,
                backup_id=pending.id,
                confirmation_text=RESTORE_CAPTCHA,
            )
    assert "not restorable" in str(exc.value)


@pytest.mark.django_db
def test_restore_refuses_failed_backup(
    restore_svc, admin_ctx, admin_user, tenant_a
):
    """A 'failed' backup is not restorable even though a file may exist."""
    failed = BackupMetadata.objects.create(
        status=BackupStatus.FAILED,
        backup_type=BackupType.FULL,
    )
    with active_tenant(tenant_a):
        with pytest.raises(BackupNotFoundError):
            restore_svc.restore(
                admin_ctx,
                backup_id=failed.id,
                confirmation_text=RESTORE_CAPTCHA,
            )


@pytest.mark.django_db
def test_restore_refuses_completed_backup_with_missing_file(
    restore_svc, admin_ctx, admin_user, tenant_a, tmp_backups_dir
):
    """A 'completed' row whose file has been deleted is rejected."""
    rel_path = f"backups/{uuid4()}.json"
    backup = BackupMetadata.objects.create(
        status=BackupStatus.COMPLETED,
        backup_type=BackupType.FULL,
        file_path=rel_path,
        file_size_bytes=0,
        checksum_sha256="0" * 64,
    )
    with active_tenant(tenant_a):
        with pytest.raises(FileNotFoundError):
            restore_svc.restore(
                admin_ctx,
                backup_id=backup.id,
                confirmation_text=RESTORE_CAPTCHA,
            )


@pytest.mark.django_db
def test_restore_happy_path_writes_start_and_complete_audit(
    restore_svc,
    admin_ctx,
    admin_user,
    tenant_a,
    tmp_backups_dir,
    fake_loaddata,
    completed_backup,
):
    """A successful restore emits 'start' and 'complete' audit rows under the same id."""
    from audit.models import AuditEntry

    with active_tenant(tenant_a):
        result = restore_svc.restore(
            admin_ctx,
            backup_id=completed_backup.id,
            confirmation_text=RESTORE_CAPTCHA,
        )
    assert result.backup_id == completed_backup.id
    assert result.started_at <= result.completed_at
    # loaddata was called once with the absolute path of the file.
    assert len(fake_loaddata) == 1
    called_args = fake_loaddata[0]
    assert called_args[0] == "loaddata"
    assert called_args[1].endswith(completed_backup.file_path)

    # The audit log has a 'start' and a 'complete' row under the
    # same BackupRestore entity id. The v1 audit writer ignores
    # ``details``; operation_kind lives in ``change_reason``.
    with active_tenant(tenant_a):
        rows = list(
            AuditEntry.objects.filter(
                entity_type="BackupRestore"
            ).order_by("timestamp")
        )
    assert len(rows) == 2
    assert rows[0].op == "create"
    assert rows[0].change_reason.startswith("restore.start ")
    assert rows[1].op == "update"
    assert rows[1].change_reason.startswith("restore.complete ")
    # Both rows share the same entity_id so they form a coherent trail.
    assert rows[0].entity_id == rows[1].entity_id
    # The first row's entity_id is the audit-only restore_event_id; the
    # backup_id appears in the change_reason of both rows.
    assert str(completed_backup.id) in rows[0].change_reason
    assert str(completed_backup.id) in rows[1].change_reason


@pytest.mark.django_db
def test_restore_failure_writes_fail_audit(
    restore_svc,
    admin_ctx,
    admin_user,
    tenant_a,
    tmp_backups_dir,
    completed_backup,
    monkeypatch,
):
    """A mid-restore failure rolls back the transaction AND writes a 'fail' audit row."""
    from audit.models import AuditEntry

    def boom(*args, **kwargs):
        raise RuntimeError("simulated loaddata failure")

    monkeypatch.setattr(
        "admin_ops.services.admin_restore_service.call_command", boom
    )

    with active_tenant(tenant_a):
        with pytest.raises(RuntimeError):
            restore_svc.restore(
                admin_ctx,
                backup_id=completed_backup.id,
                confirmation_text=RESTORE_CAPTCHA,
            )

    # A 'fail' audit row was written; no 'start' / 'complete' rows
    # leaked through because the main transaction rolled back.
    with active_tenant(tenant_a):
        fail_rows = list(
            AuditEntry.objects.filter(
                entity_type="BackupRestore"
            ).filter(entity_id__isnull=False)
        )
    fail_rows = [
        r
        for r in fail_rows
        if r.change_reason.startswith("restore.fail")
    ]
    assert len(fail_rows) == 1
    assert fail_rows[0].op == "update"
    # The error message lives in change_reason (v1 audit writer
    # ignores ``details``).
    assert "simulated loaddata failure" in fail_rows[0].change_reason

    # No 'start' row survived (the start audit was inside the
    # rolled-back transaction).
    with active_tenant(tenant_a):
        start_rows = list(
            AuditEntry.objects.filter(
                entity_type="BackupRestore"
            )
        )
    start_rows = [
        r
        for r in start_rows
        if r.change_reason.startswith("restore.start")
    ]
    assert len(start_rows) == 0


@pytest.mark.django_db
def test_restore_captcha_constant_is_restored(
    restore_svc, admin_ctx, admin_user, tenant_a
):
    """The captcha constant is the literal ``"RESTORE"`` string."""
    assert RESTORE_CAPTCHA == "RESTORE"
    # And the gate uses it: a literal "RESTORE" passes the captcha and
    # only then hits the backup-not-found path.
    with active_tenant(tenant_a):
        with pytest.raises(BackupNotFoundError):
            restore_svc.restore(
                admin_ctx,
                backup_id=uuid4(),
                confirmation_text=RESTORE_CAPTCHA,
            )
