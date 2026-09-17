"""REST surface for the link-type catalog."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_VIEWER, UserRole
from link_types.builtin import builtin_definition
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def api(db, authed_client, workspace):
    return authed_client, workspace


@pytest.fixture
def viewer_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """An APIClient authenticated as a viewer (read-only role) of *tenant*/*workspace*.

    No shared viewer-role fixture exists in this repo (checked
    ``rest_api/tests/conftest.py``); mirrors the local-setup pattern used in
    ``test_rbac_role_auth_matrix.py`` / ``test_api_key_views_rbac.py``.
    """
    user = User.objects.create(
        username="viewerlt", email="viewerlt@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "viewerlt", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.mark.django_db
def test_global_list_returns_the_seeded_types(api):
    client, _ws = api
    response = client.get("/api/v1/link-type-defaults/")
    assert response.status_code == 200
    assert {row["key"] for row in response.json()} >= {"verifies", "derives-from"}


@pytest.mark.django_db
def test_global_create_adds_a_tenant_type(api):
    client, _ws = api
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    response = client.post(
        "/api/v1/link-type-defaults/",
        data={"key": "conflicts-with", "definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["key"] == "conflicts-with"


@pytest.mark.django_db
def test_global_create_rejects_an_invalid_suspect_rule(api):
    client, _ws = api
    definition = builtin_definition("mitigates")
    definition["suspect_rule"] = "nope"
    response = client.post(
        "/api/v1/link-type-defaults/",
        data={"key": "conflicts-with", "definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "suspect_rule" in response.json()["detail"]


@pytest.mark.django_db
def test_global_update_reports_propagation(api):
    client, _ws = api
    definition = builtin_definition("mitigates")
    definition["impact_weight"] = 0.9
    response = client.put(
        "/api/v1/link-type-defaults/mitigates/",
        data={"definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["propagated_to"] >= 1


@pytest.mark.django_db
def test_global_delete_rejects_a_system_owned_type(api):
    client, _ws = api
    response = client.delete("/api/v1/link-type-defaults/diagram-ref/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_workspace_list_returns_resolved_rows(api):
    client, ws = api
    response = client.get(f"/api/v1/workspaces/{ws.id}/link-type-definitions/")
    assert response.status_code == 200
    body = response.json()
    assert all("is_customized" in row for row in body)
    assert all("definition" in row for row in body)


@pytest.mark.django_db
def test_workspace_update_then_reset(api):
    client, ws = api
    definition = builtin_definition("mitigates")
    definition["impact_weight"] = 0.7

    updated = client.put(
        f"/api/v1/workspaces/{ws.id}/link-type-definitions/mitigates/",
        data={"definition": definition},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["is_customized"] is True

    reset = client.post(
        f"/api/v1/workspaces/{ws.id}/link-type-definitions/mitigates/reset/"
    )
    assert reset.status_code == 200
    assert reset.json()["is_customized"] is False
    assert reset.json()["definition"]["impact_weight"] == 0.5


@pytest.mark.django_db
def test_a_non_uuid_workspace_404s_instead_of_500ing(api):
    client, _ws = api
    response = client.get("/api/v1/workspaces/not-a-uuid/link-type-definitions/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_an_unknown_key_returns_400(api):
    client, ws = api
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/link-type-definitions/nope/reset/"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_viewer_cannot_write(viewer_client, workspace):
    definition = builtin_definition("mitigates")
    response = viewer_client.put(
        f"/api/v1/workspaces/{workspace.id}/link-type-definitions/mitigates/",
        data={"definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_viewer_can_read(viewer_client, workspace):
    response = viewer_client.get(
        f"/api/v1/workspaces/{workspace.id}/link-type-definitions/"
    )
    assert response.status_code == 200
