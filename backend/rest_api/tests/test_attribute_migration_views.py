"""REST views of the AWMS surface (WS7 #940, spec §7).

Drives the real HTTP stack (APIClient + JWT -> auth enforcer -> view ->
AttributeMigrationService) for the admin-only migration resource: preview,
apply, run history, detail and rollback, plus the permission/invalid-plan
error envelopes.
"""
from __future__ import annotations

import pytest

from attribute_definitions.migration_plan import load_plan_file
from attribute_definitions.plans import plan_path
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement

pytestmark = pytest.mark.django_db


def _plan() -> dict:
    return load_plan_file(plan_path("rationale_from_description.yaml"))


@pytest.fixture
def requirement(tenant_fixture, workspace_fixture):
    set_request_tenant(tenant_fixture.id)
    try:
        artifact = Artifact.objects.create(
            tenant_id=tenant_fixture.id,
            workspace=workspace_fixture,
            artifact_type="Requirement",
        )
        Requirement.objects.create(
            tenant_id=tenant_fixture.id,
            artifact=artifact,
            title="REST Req",
            description="Begründung: die REST-API muss sie liefern.",
        )
        return artifact
    finally:
        clear_request_tenant()


def _custom_fields(tenant_fixture, artifact) -> dict:
    """Read the artifact under an armed request tenant.

    The auth middleware clears the request tenant after every HTTP request, so a
    test-side ORM read has to re-arm it.
    """
    set_request_tenant(tenant_fixture.id)
    try:
        return dict(Artifact.objects.get(id=artifact.id).custom_fields or {})
    finally:
        clear_request_tenant()


def test_preview_then_apply_then_history_and_rollback(
    admin_client, tenant_fixture, requirement
) -> None:
    preview = admin_client.post(
        "/api/v1/attribute-migration/plan/", _plan(), format="json"
    )
    assert preview.status_code == 200, preview.content
    assert preview.json()["status"] == "planned"
    assert "rationale" not in _custom_fields(tenant_fixture, requirement)

    applied = admin_client.post(
        "/api/v1/attribute-migration/apply/", _plan(), format="json"
    )
    assert applied.status_code == 200, applied.content
    body = applied.json()
    assert body["status"] == "applied"
    run_id = body["run_id"]
    assert (
        _custom_fields(tenant_fixture, requirement)["rationale"]
        == "die REST-API muss sie liefern."
    )

    runs = admin_client.get("/api/v1/attribute-migration/runs/")
    assert runs.status_code == 200
    assert runs.json()["count"] >= 1

    detail = admin_client.get(f"/api/v1/attribute-migration/runs/{run_id}/")
    assert detail.status_code == 200
    assert detail.json()["id"] == run_id

    rollback = admin_client.post(
        f"/api/v1/attribute-migration/runs/{run_id}/rollback/"
    )
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "rolled_back"
    assert "rationale" not in _custom_fields(tenant_fixture, requirement)


def test_apply_alias_route_is_the_same_view(admin_client, requirement) -> None:
    response = admin_client.post("/api/v1/attribute-migration/", _plan(), format="json")
    assert response.status_code == 200, response.content
    assert response.json()["mode"] == "apply"


def test_editor_gets_permission_denied(editor_client, requirement) -> None:
    response = editor_client.post(
        "/api/v1/attribute-migration/plan/", _plan(), format="json"
    )
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_invalid_plan_is_a_400(admin_client) -> None:
    response = admin_client.post(
        "/api/v1/attribute-migration/plan/",
        {"id": "x", "steps": []},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_run_is_a_404(admin_client) -> None:
    import uuid

    response = admin_client.get(
        f"/api/v1/attribute-migration/runs/{uuid.uuid4()}/"
    )
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "NOT_FOUND"
