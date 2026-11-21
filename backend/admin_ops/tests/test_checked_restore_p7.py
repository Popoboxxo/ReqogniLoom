"""P7 / D17 — checked target-instance restore tests.

Covers the four guarantees added to ``AdminRestoreService``:

* SHA-256 verification of the on-disk bytes **before** ``loaddata``;
* ``format_version`` validation (with legacy default);
* ``dry_run`` — exact plan, no load, no audit row, no data change;
* ``target_tenant`` / ``target_workspace`` with an explicitly armed and
  always-restored RLS context.

The last test is a real round-trip: a minimal dumpdata fixture (one Artifact
+ one Requirement) is restored with the real ``loaddata`` against the test DB.
Run the whole file in Docker via ``backend-test`` (needs PostgreSQL for the
RLS context switches).
"""
from __future__ import annotations

import gzip
import hashlib
import os
import uuid
from datetime import UTC, datetime

import pytest
from django.core import serializers

from admin_ops.models import BackupMetadata, BackupStatus, BackupType
from admin_ops.services import AdminRestoreService, BackupService
from admin_ops.services.admin_restore_service import (
    DEFAULT_BACKUP_FORMAT_VERSION,
    RESTORE_CAPTCHA,
    BackupChecksumMismatch,
    UnsupportedBackupFormat,
)
from admin_ops.services.paths import backup_root
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

from .conftest import active_tenant

pytestmark = pytest.mark.django_db


def _write_backup(payload: bytes, *, metadata: dict | None = None) -> BackupMetadata:
    """Write *payload* to a per-test backup file and create its metadata row."""
    digest = hashlib.sha256(payload).hexdigest()
    rel_path = f"p7-{uuid.uuid4().hex}.json.gz"
    abs_path = os.path.join(backup_root(), rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as fh:
        fh.write(payload)
    return BackupMetadata.objects.create(
        status=BackupStatus.COMPLETED,
        backup_type=BackupType.FULL,
        file_path=rel_path,
        file_size_bytes=len(payload),
        checksum_sha256=digest,
        metadata=metadata or {},
        completed_at=datetime.now(UTC),
    )


def _stub_loaddata(monkeypatch):
    calls: list[str] = []

    def fake_call(*args, **kwargs):
        calls.append(str(args[0]) if args else "")

    monkeypatch.setattr(
        "admin_ops.services.admin_restore_service.call_command", fake_call
    )
    return calls


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------


def test_checksum_mismatch_blocks_loaddata(admin_ctx, monkeypatch):
    calls = _stub_loaddata(monkeypatch)
    backup = _write_backup(gzip.compress(b"[]", mtime=0))
    # Simulate corruption after the backup row was written.
    backup.checksum_sha256 = "0" * 64
    backup.save(update_fields=["checksum_sha256"])

    with pytest.raises(BackupChecksumMismatch, match="checksum mismatch"):
        AdminRestoreService().restore(
            admin_ctx,
            backup_id=backup.id,
            confirmation_text=RESTORE_CAPTCHA,
        )

    assert calls == [], "loaddata must not run on a checksum mismatch"


def test_checksum_verified_flag_is_reported(admin_ctx, monkeypatch):
    _stub_loaddata(monkeypatch)
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    result = AdminRestoreService().restore(
        admin_ctx, backup_id=backup.id, confirmation_text=RESTORE_CAPTCHA
    )

    assert result.checksum_verified is True
    assert result.format_version == DEFAULT_BACKUP_FORMAT_VERSION


# ---------------------------------------------------------------------------
# format_version
# ---------------------------------------------------------------------------


def test_unsupported_format_version_is_refused(admin_ctx, monkeypatch):
    _stub_loaddata(monkeypatch)
    backup = _write_backup(
        gzip.compress(b"[]", mtime=0), metadata={"format_version": "99"}
    )

    with pytest.raises(UnsupportedBackupFormat, match="format_version"):
        AdminRestoreService().restore(
            admin_ctx, backup_id=backup.id, confirmation_text=RESTORE_CAPTCHA
        )


def test_backup_stamps_format_version(admin_user, monkeypatch, tenant_a):
    """Backups created by BackupService always carry a known format_version."""
    from admin_ops.services.paths import backup_root as root

    def fake_dumpdata(*args, **kwargs):
        kwargs["stdout"].write("[]")

    monkeypatch.setattr(
        "admin_ops.services.backup_service.call_command", fake_dumpdata
    )
    with active_tenant(tenant_a):
        row = BackupService().create_backup(_admin_ctx(admin_user, tenant_a))

    assert row.metadata["format_version"] == DEFAULT_BACKUP_FORMAT_VERSION
    assert os.path.isfile(os.path.join(root(), row.file_path))


def _admin_ctx(user, tenant: Tenant) -> AuthContext:
    from auth_tenancy.context import AuthMethod
    from auth_tenancy.models import ROLE_ADMIN

    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------


def test_dry_run_returns_plan_without_loading_or_auditing(
    admin_ctx, monkeypatch
):
    calls = _stub_loaddata(monkeypatch)
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    result = AdminRestoreService().restore(
        admin_ctx,
        backup_id=backup.id,
        confirmation_text=RESTORE_CAPTCHA,
        dry_run=True,
    )

    assert calls == []
    assert result.dry_run is True
    assert result.plan is not None
    assert result.plan["loaddata"] is False
    assert result.plan["checksum_verified"] is True
    assert result.checksum_verified is True
    assert result.restored_tables == []


# ---------------------------------------------------------------------------
# target tenant / RLS
# ---------------------------------------------------------------------------


def test_target_tenant_arms_and_restores_rls_context(
    admin_ctx, tenant_a, monkeypatch
):
    _stub_loaddata(monkeypatch)
    other = Tenant.objects.create(
        name="P7-TARGET", slug=f"p7-target-{uuid.uuid4().hex[:8]}", is_active=True
    )
    from auth_tenancy.models import ROLE_ADMIN, UserRole

    with active_tenant(other):
        target_ws = Workspace.objects.create(
            tenant=other, name="P7 target WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=other,
            user_id=admin_ctx.user_id,
            workspace=target_ws,
            role=ROLE_ADMIN,
        )
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    # Arm the caller's tenant first — the restore must put it back.
    with active_tenant(tenant_a):
        assert TenantContext.get_tenant() == tenant_a.id
        # D16b: a cross-tenant restore needs an audited dry-run preview first.
        AdminRestoreService().restore(
            admin_ctx,
            backup_id=backup.id,
            confirmation_text=RESTORE_CAPTCHA,
            dry_run=True,
            target_tenant=other.id,
        )
        result = AdminRestoreService().restore(
            admin_ctx,
            backup_id=backup.id,
            confirmation_text=RESTORE_CAPTCHA,
            target_tenant=other.id,
        )
        assert TenantContext.get_tenant() == tenant_a.id

    assert result.target_tenant == other.id


def test_unknown_target_tenant_is_refused(admin_ctx, tenant_a, monkeypatch):
    _stub_loaddata(monkeypatch)
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    with active_tenant(tenant_a):
        from admin_ops.services.exceptions import BackupNotFoundError

        with pytest.raises(BackupNotFoundError, match="Target tenant"):
            AdminRestoreService().restore(
                admin_ctx,
                backup_id=backup.id,
                confirmation_text=RESTORE_CAPTCHA,
                target_tenant=uuid.uuid4(),
            )


# ---------------------------------------------------------------------------
# Real round-trip (one entity, real loaddata)
# ---------------------------------------------------------------------------


def test_checked_restore_roundtrip_minimal_fixture(admin_ctx, tenant_a, tmp_backups_dir):
    """Serialize one live entity, delete it, then restore it with real loaddata."""
    with active_tenant(tenant_a):
        workspace = Workspace.objects.create(
            tenant=tenant_a, name="P7 Roundtrip WS", preset={"name": "standard"}
        )
        artifact = Artifact.objects.create(
            tenant=tenant_a, workspace=workspace, artifact_type="Requirement"
        )
        requirement = Requirement.objects.create(
            tenant=tenant_a,
            artifact=artifact,
            title="P7 Roundtrip Requirement",
            description="round trip",
            category="functional",
            type="SyReq",
            level=1,
            uid="REQ-P7-RT-1",
        )
        raw_json = serializers.serialize("json", [artifact, requirement])
        requirement_id = requirement.id

    payload = gzip.compress(raw_json.encode("utf-8"), mtime=0)
    backup = _write_backup(
        payload, metadata={"format_version": DEFAULT_BACKUP_FORMAT_VERSION}
    )

    with active_tenant(tenant_a):
        Requirement.objects.filter(pk=requirement_id).delete()
        Artifact.objects.filter(pk=artifact.id).delete()
        assert not Requirement.objects.filter(uid="REQ-P7-RT-1").exists()

    result = AdminRestoreService().restore(
        admin_ctx, backup_id=backup.id, confirmation_text=RESTORE_CAPTCHA
    )

    assert result.checksum_verified is True
    assert "persistence.requirement" in result.restored_tables

    with active_tenant(tenant_a):
        restored = Requirement.objects.get(uid="REQ-P7-RT-1")
        assert restored.title == "P7 Roundtrip Requirement"


# ---------------------------------------------------------------------------
# D16b — cross-tenant gates (admin in both tenants, dry-run preview, audit)
# ---------------------------------------------------------------------------


def _cross_tenant_setup(admin_ctx, *, grant_target_admin: bool = True):
    """Create a second tenant with an admin workspace for the same user."""
    from auth_tenancy.models import ROLE_ADMIN, UserRole
    from persistence.middleware import clear_request_tenant, set_request_tenant

    set_request_tenant(admin_ctx.tenant_id)
    try:
        target = Tenant.objects.create(
            name="P7-target", slug=f"p7-target-{uuid.uuid4().hex[:8]}"
        )
        ws = Workspace.objects.create(
            tenant=target, name="P7 target WS", preset={"name": "standard"}
        )
        if grant_target_admin:
            UserRole.objects.create(
                tenant=target,
                user_id=admin_ctx.user_id,
                workspace=ws,
                role=ROLE_ADMIN,
            )
        return target
    finally:
        clear_request_tenant()


def test_cross_tenant_dry_run_writes_preview_audit(admin_ctx, monkeypatch):
    from audit.models import AuditEntry
    from persistence.middleware import clear_request_tenant, set_request_tenant

    calls = _stub_loaddata(monkeypatch)
    target = _cross_tenant_setup(admin_ctx)
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    result = AdminRestoreService().restore(
        admin_ctx,
        backup_id=backup.id,
        confirmation_text=RESTORE_CAPTCHA,
        dry_run=True,
        target_tenant=target.id,
    )

    assert result.dry_run is True
    assert calls == []
    # The audit writer injects the ACTIVE RLS tenant, so the preview receipt
    # lives in the target tenant — which is exactly where the real restore
    # looks for it.
    set_request_tenant(target.id)
    try:
        assert AuditEntry.objects.filter(
            details__operation_kind="restore.preview",
            details__backup_id=str(backup.id),
            details__target_tenant=str(target.id),
        ).exists()
    finally:
        clear_request_tenant()


def test_cross_tenant_real_restore_requires_preview(admin_ctx, monkeypatch):
    from application.base import ValidationError as ServiceValidationError

    _stub_loaddata(monkeypatch)
    target = _cross_tenant_setup(admin_ctx)
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    with pytest.raises(ServiceValidationError, match="dry_run=True preview"):
        AdminRestoreService().restore(
            admin_ctx,
            backup_id=backup.id,
            confirmation_text=RESTORE_CAPTCHA,
            target_tenant=target.id,
        )


def test_cross_tenant_requires_admin_in_target(admin_ctx, monkeypatch):
    from application.base import PermissionDeniedError

    _stub_loaddata(monkeypatch)
    target = _cross_tenant_setup(admin_ctx, grant_target_admin=False)
    backup = _write_backup(gzip.compress(b"[]", mtime=0))

    with pytest.raises(PermissionDeniedError, match="target tenant"):
        AdminRestoreService().restore(
            admin_ctx,
            backup_id=backup.id,
            confirmation_text=RESTORE_CAPTCHA,
            dry_run=True,
            target_tenant=target.id,
        )
