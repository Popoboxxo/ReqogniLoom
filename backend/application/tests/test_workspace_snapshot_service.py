"""P5/P6: snapshot export and import into a new workspace with remapped ids."""
from __future__ import annotations

import pytest

from application.base import ValidationError
from application.workspace_snapshot_service import WorkspaceSnapshotService
from persistence.models import Requirement, Workspace
from persistence.tests.factories import active_tenant, editor_ctx, make_requirement, make_workspace


@pytest.mark.django_db
def test_snapshot_round_trip_into_new_workspace() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        original = make_requirement(source, title="Snapshot Requirement")
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()

        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)
        assert snapshot["format_version"] == "artifact-transfer/v1"
        assert snapshot["checksum"]
        assert any(row["title"] == "Snapshot Requirement" for row in snapshot["entities"]["requirement"])

        dry = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, new_workspace_name="Would-Be Copy", dry_run=True
        )
        assert dry.dry_run is True
        assert dry.created.get("Requirement") == 1
        assert not Workspace.objects.filter(name="Would-Be Copy").exists()

        result = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, new_workspace_name="Snapshot Copy"
        )
        assert result.workspace_id != source.id
        assert result.created.get("Requirement") == 1

        copied = Requirement.objects.filter(artifact__workspace_id=result.workspace_id).first()
        assert copied is not None
        assert copied.title == "Snapshot Requirement"
        assert copied.id != original.id
        assert copied.artifact_id != original.artifact_id


@pytest.mark.django_db
def test_snapshot_rejects_checksum_mismatch() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)
        snapshot["checksum"] = "tampered"
        with pytest.raises(ValidationError, match="checksum"):
            service.import_snapshot(
                ctx=ctx, snapshot=snapshot, new_workspace_name="Bad Snapshot"
            )
