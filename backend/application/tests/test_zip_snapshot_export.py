"""R1/P5: versioned ZIP snapshot export — buckets, checksum, TTL, cross-tenant gates."""
from __future__ import annotations

import json
import os
import zipfile
from datetime import timedelta
from uuid import UUID

import pytest
from django.utils import timezone

from admin_ops.models import ExportSnapshotMetadata, ExportStatus
from admin_ops.services.paths import absolute_export_path
from application.artifact_transfer_contract import TRANSFER_SPECS
from application.base import ValidationError
from application.zip_snapshot_export_service import (
    SNAPSHOT_FORMAT_VERSION,
    ZipSnapshotExportService,
    purge_expired_exports,
)
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    editor_ctx,
    make_requirement,
    make_user,
    make_workspace,
)
from presets.exceptions import CrossTenantWorkspaceError


@pytest.fixture(autouse=True)
def _isolated_export_dir(tmp_path, monkeypatch):
    """Never write ZIPs into the container's read-only /app/exports."""
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))


@pytest.mark.django_db
def test_zip_has_all_24_entity_buckets_manifest_media_and_checksum() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        make_requirement(source, title="ZIP Requirement")
        ctx = editor_ctx(tenant, source)

        result = ZipSnapshotExportService().start_export(
            ctx=ctx, workspace_id=source.id
        )
        export_id = UUID(result["export_id"])
        row = ExportSnapshotMetadata.unscoped.get(id=export_id)
        assert row.status == ExportStatus.COMPLETED
        assert row.checksum_sha256 and row.content_checksum_sha256
        assert row.size_bytes and row.size_bytes > 0
        assert row.metadata["format_version"] == SNAPSHOT_FORMAT_VERSION

        path = absolute_export_path(row.file_path)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            buckets = [
                name
                for name in names
                if name.startswith("entities/") and name.endswith(".jsonl")
            ]
            assert len(buckets) == len(TRANSFER_SPECS) == 24
            assert "manifest.json" in names
            assert "relations.jsonl" in names
            assert "media/README.md" in names
            assert "checksum.sha256" in names

            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["format_version"] == SNAPSHOT_FORMAT_VERSION
            assert manifest["source_workspace_id"] == str(source.id)
            assert manifest["entities"]["requirement"]["count"] >= 1
            assert (
                archive.read("checksum.sha256").decode("ascii").strip()
                == row.content_checksum_sha256
            )
            requirement_lines = [
                json.loads(line)
                for line in archive.read("entities/requirement.jsonl").splitlines()
            ]
            assert any(r["title"] == "ZIP Requirement" for r in requirement_lines)

        service = ZipSnapshotExportService()
        assert service.verify_zip_checksum(path, row.checksum_sha256) is True


@pytest.mark.django_db
def test_checksum_mismatch_is_refused() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        ctx = editor_ctx(tenant, source)
        result = ZipSnapshotExportService().start_export(
            ctx=ctx, workspace_id=source.id
        )
        row = ExportSnapshotMetadata.unscoped.get(id=UUID(result["export_id"]))
        path = absolute_export_path(row.file_path)
        service = ZipSnapshotExportService()

        with pytest.raises(ValidationError, match="checksum"):
            service.verify_zip_checksum(path, "0" * 64)

        # Tamper with a member (not just the outer hash) — the internal content
        # digest must catch it too.
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("entities/requirement.jsonl", b'{"injected": true}\n')
        with pytest.raises(ValidationError, match="checksum"):
            service.verify_zip_checksum(path)


@pytest.mark.django_db
def test_cross_tenant_source_export_is_refused_without_grant() -> None:
    with active_tenant() as tenant_a:
        source = make_workspace(tenant_a)
    with active_tenant() as tenant_b:
        # An editor of tenant B has no read grant on tenant A's workspace.
        ctx_b = editor_ctx(tenant_b)
        with pytest.raises(CrossTenantWorkspaceError):
            ZipSnapshotExportService().start_export(
                ctx=ctx_b, workspace_id=source.id
            )


@pytest.mark.django_db
def test_cross_tenant_transfer_needs_admin_and_dry_run_preview() -> None:
    with active_tenant() as tenant_a:
        source = make_workspace(tenant_a)
    with active_tenant() as tenant_b:
        target = make_workspace(tenant_b)
        admin_b = make_user(tenant_b)
        ctx_b = ctx_for_user(tenant_b, admin_b, roles=("admin",))
        service = ZipSnapshotExportService()

        preview = service.start_export(
            ctx=ctx_b,
            workspace_id=source.id,
            target_workspace_id=target.id,
            dry_run=True,
        )
        assert preview["dry_run"] is True
        assert preview["cross_tenant"] is True
        assert "requirement" in preview["preview"]
        assert not ExportSnapshotMetadata.unscoped.filter(
            source_workspace_id=source.id
        ).exists()

        with pytest.raises(ValidationError, match="dry_run"):
            service.start_export(
                ctx=ctx_b,
                workspace_id=source.id,
                target_workspace_id=target.id,
            )


@pytest.mark.django_db
def test_metadata_stamped_and_ttl_cleanup_removes_row_and_file() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        ctx = editor_ctx(tenant, source)
        result = ZipSnapshotExportService().start_export(
            ctx=ctx, workspace_id=source.id
        )
        row = ExportSnapshotMetadata.unscoped.get(id=UUID(result["export_id"]))
        assert row.owner_id == ctx.user_id
        assert row.tenant_id == tenant.id
        assert row.expires_at is not None
        path = absolute_export_path(row.file_path)
        assert os.path.isfile(path)

        status = ZipSnapshotExportService().get_status(
            ctx=ctx, workspace_id=source.id, export_id=row.id
        )
        assert status.status == ExportStatus.COMPLETED
        assert status.checksum_sha256 == row.checksum_sha256
        assert status.download_url is not None

        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["expires_at"])
        assert purge_expired_exports() >= 1
        assert not ExportSnapshotMetadata.unscoped.filter(id=row.id).exists()
        assert not os.path.exists(path)
