"""REST surface for full workspace snapshot export/import (P5/P6)."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_snapshot_export_and_dry_run_import(admin_client, workspace_fixture) -> None:
    response = admin_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/export/snapshot/"
    )
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["format_version"] == "artifact-transfer/v1"
    assert snapshot["checksum"]

    dry = admin_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/import/snapshot/",
        {"snapshot": snapshot, "new_workspace_name": "Dry Run Copy", "dry_run": True},
        format="json",
    )
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True


@pytest.mark.django_db
def test_snapshot_import_into_new_workspace(admin_client, workspace_fixture) -> None:
    exported = admin_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/export/snapshot/"
    ).json()
    response = admin_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/import/snapshot/",
        {"snapshot": exported, "new_workspace_name": "Snapshot REST Copy"},
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["success"] is True
    assert body["workspace_id"] != str(workspace_fixture.id)


@pytest.mark.django_db
def test_non_admin_cannot_force_update_mode(editor_client, workspace_fixture) -> None:
    response = editor_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/import/snapshot/",
        {"snapshot": {}, "conflict_mode": "update"},
        format="json",
    )
    assert response.status_code == 403
