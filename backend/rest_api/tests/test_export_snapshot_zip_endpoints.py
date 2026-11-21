"""REST surface for the async ZIP full-snapshot export (R1/P5, D14c)."""
from __future__ import annotations

import io
import uuid
import zipfile

import pytest

from admin_ops.models import ExportSnapshotMetadata, ExportStatus
from admin_ops.services.paths import absolute_export_path
from application.zip_snapshot_export_service import ZipSnapshotExportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace


def _start_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/export/snapshot/zip/"


@pytest.fixture(autouse=True)
def _isolated_export_dir(tmp_path, monkeypatch):
    """Never write ZIPs into the container's read-only /app/exports."""
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))


@pytest.mark.django_db
def test_start_status_and_download_zip(admin_client, workspace_fixture) -> None:
    start = admin_client.post(_start_url(workspace_fixture.id), {}, format="json")
    assert start.status_code == 202, start.content
    body = start.json()
    export_id = body["export_id"]
    assert body["status"] == ExportStatus.COMPLETED  # eager worker in tests
    assert body["checksum_sha256"]
    assert body["download_url"].endswith(f"{export_id}/download/")

    status = admin_client.get(f"{_start_url(workspace_fixture.id)}{export_id}/status/")
    assert status.status_code == 200, status.content
    payload = status.json()
    assert payload["status"] == ExportStatus.COMPLETED
    assert payload["format_version"] == "artifact-transfer/v1"
    assert payload["download_url"]

    download = admin_client.get(
        f"{_start_url(workspace_fixture.id)}{export_id}/download/"
    )
    assert download.status_code == 200, download.content
    assert download["Content-Type"] == "application/zip"
    assert download["X-Checksum-SHA256"] == payload["checksum_sha256"]
    zip_bytes = b"".join(download.streaming_content)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        assert "manifest.json" in archive.namelist()
        assert len(
            [n for n in archive.namelist() if n.startswith("entities/")]
        ) == 24

    set_request_tenant(workspace_fixture.tenant_id)
    try:
        row = ExportSnapshotMetadata.objects.get(id=export_id)
    finally:
        clear_request_tenant()
    assert ZipSnapshotExportService().verify_zip_checksum(
        absolute_export_path(row.file_path), row.checksum_sha256
    )


@pytest.mark.django_db
def test_dry_run_preview_does_not_queue_or_persist(
    admin_client, workspace_fixture
) -> None:
    response = admin_client.post(
        _start_url(workspace_fixture.id), {"dry_run": True}, format="json"
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["dry_run"] is True
    assert "requirement" in body["preview"]
    assert "export_id" not in body
    set_request_tenant(workspace_fixture.tenant_id)
    try:
        assert not ExportSnapshotMetadata.objects.exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_cross_tenant_export_is_refused(editor_client, workspace_fixture) -> None:
    foreign = Tenant.objects.create(
        name="Foreign Tenant", slug=f"foreign-{uuid.uuid4().hex[:8]}"
    )
    set_request_tenant(foreign.id)
    try:
        foreign_ws = Workspace.objects.create(
            tenant=foreign, name="foreign-ws", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()

    # D16: a foreign workspace needs an explicit source READ grant; an
    # editor of another tenant has none.
    response = editor_client.post(_start_url(foreign_ws.id), {}, format="json")
    assert response.status_code == 403
