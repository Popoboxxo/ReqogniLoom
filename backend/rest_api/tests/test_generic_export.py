"""REST surface for the generic artifact export (P2)."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_generic_export_endpoint_csv(admin_client, workspace_fixture) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/export/entity/",
        {"entity": "requirement", "export_format": "csv"},
    )
    assert response.status_code == 200, response.content
    assert response["Content-Type"].startswith("text/csv")
    assert 'filename="export_requirement.csv"' in response["Content-Disposition"]


@pytest.mark.django_db
def test_generic_export_endpoint_json(admin_client, workspace_fixture) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/export/entity/",
        {"entity": "work_item"},
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert b'"entity": "work_item"' in response.content


@pytest.mark.django_db
def test_generic_export_rejects_unknown_entity(admin_client, workspace_fixture) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/export/entity/",
        {"entity": "does_not_exist"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
