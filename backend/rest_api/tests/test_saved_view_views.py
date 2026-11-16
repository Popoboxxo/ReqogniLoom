"""REST surface for saved views and per-user table state (slice 3, Task 3.3).

The services behind it are covered in
``application/tests/test_saved_view_service.py``; this file pins the *transport*:

* route resolution (collection, detail, apply, table state),
* 201/200/204 roundtrips and the row/pagination shapes,
* 404 for another user's private view and for a foreign tenant's view,
* 403 for a non-owner patching a workspace-wide view,
* 400 for an unknown query parameter / an unknown body field,
* **no ``If-Match``**: the PATCH carries ``expected_version`` in the body and a
  GET publishes no ``ETag`` (the plan's conditional-request gate),
* ``apply`` answers 200 with ``warnings`` even when the stored view is stale,
* the per-user state GET answers the documented empty default without a row.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, SavedView, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/saved-views/"
STATE = "/api/v1/users/me/table-view-state/"
_PASSWORD = "hunter2pass"


def _second_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """A logged-in editor of the same tenant/workspace, different user."""
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"sv-other-{suffix}",
        email=f"sv-other-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


@pytest.fixture
def requirement(tenant: Tenant, workspace: Workspace) -> Requirement:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title="Alpha",
            uid="REQ-API-1",
            description="d",
        )
    finally:
        clear_request_tenant()


def _create(client: APIClient, workspace: Workspace, **overrides):
    body = {
        "workspace_id": str(workspace.id),
        "item_type": "Requirement",
        "name": "Offene Anforderungen",
        "columns": [{"field": "title", "order": 0}],
        "sort": [{"field": "title", "dir": "asc"}],
    }
    body.update(overrides)
    return client.post(COLLECTION, body, format="json")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_list_get_patch_delete_roundtrip(authed_client, workspace):
    created = _create(authed_client, workspace)
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["name"] == "Offene Anforderungen"
    assert body["visibility"] == "private"
    assert body["version"] == 1
    view_id = body["id"]

    listed = authed_client.get(COLLECTION, {"workspace_id": str(workspace.id)})
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [view_id]

    fetched = authed_client.get(f"{COLLECTION}{view_id}/")
    assert fetched.status_code == 200
    # No ETag on this resource: conditional requests are not part of its
    # contract (the plan's conditional-request gate lists the six ETag types).
    assert "ETag" not in fetched.headers

    patched = authed_client.patch(
        f"{COLLECTION}{view_id}/", {"name": "Neu"}, format="json"
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["name"] == "Neu"
    assert patched.json()["version"] == 2

    deleted = authed_client.delete(f"{COLLECTION}{view_id}/")
    assert deleted.status_code == 204
    assert authed_client.get(f"{COLLECTION}{view_id}/").status_code == 404


def test_patch_accepts_expected_version_in_body_not_if_match(
    authed_client, workspace
):
    view_id = _create(authed_client, workspace).json()["id"]

    stale = authed_client.patch(
        f"{COLLECTION}{view_id}/",
        {"name": "x", "expected_version": 99},
        format="json",
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"

    ok = authed_client.patch(
        f"{COLLECTION}{view_id}/",
        {"name": "x", "expected_version": 1},
        format="json",
    )
    assert ok.status_code == 200


def test_private_view_of_other_user_is_404(authed_client, tenant, workspace):
    view_id = _create(authed_client, workspace).json()["id"]
    other = _second_client(tenant, workspace)

    assert other.get(f"{COLLECTION}{view_id}/").status_code == 404
    assert other.get(f"{COLLECTION}{view_id}/apply/").status_code == 404
    assert other.get(COLLECTION, {"workspace_id": str(workspace.id)}).json() == []


def test_workspace_view_patch_by_non_owner_is_403(authed_client, tenant, workspace):
    view_id = _create(authed_client, workspace, visibility="workspace").json()["id"]
    other = _second_client(tenant, workspace)

    assert other.get(f"{COLLECTION}{view_id}/").status_code == 200
    denied = other.patch(f"{COLLECTION}{view_id}/", {"name": "x"}, format="json")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"


def test_foreign_tenant_404(authed_client, db):
    other = Tenant.objects.create(
        name="Other", slug=f"other-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(other.id)
    try:
        workspace = Workspace.objects.create(tenant=other, name="Other WS")
        owner = User.objects.create(
            tenant=other, username=f"foreign-{uuid.uuid4().hex[:8]}"
        )
        view = SavedView.objects.create(
            tenant=other,
            workspace=workspace,
            owner=owner,
            item_type="Requirement",
            name="foreign",
        )
        view_id = view.id
    finally:
        clear_request_tenant()

    assert authed_client.get(f"{COLLECTION}{view_id}/").status_code == 404


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_query_param_400(authed_client, workspace):
    response = authed_client.get(
        COLLECTION, {"workspace_id": str(workspace.id), "nope": "1"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_body_field_is_rejected(authed_client, workspace):
    view_id = _create(authed_client, workspace).json()["id"]

    response = authed_client.patch(
        f"{COLLECTION}{view_id}/", {"nope": 1}, format="json"
    )
    assert response.status_code == 400


def test_create_with_unknown_filter_field_is_400(authed_client, workspace):
    response = _create(
        authed_client,
        workspace,
        filters={"nope": {"op": "contains", "value": "x"}},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_missing_workspace_id_is_400(authed_client):
    assert authed_client.get(COLLECTION).status_code == 400


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def test_apply_paginates_and_returns_warnings(authed_client, workspace, requirement):
    view_id = _create(
        authed_client,
        workspace,
        filters={"title": {"op": "contains", "value": "Alp"}},
    ).json()["id"]

    response = authed_client.get(f"{COLLECTION}{view_id}/apply/")
    assert response.status_code == 200, response.content
    body = response.json()
    assert [row["values"]["title"] for row in body["results"]] == ["Alpha"]
    assert body["count"] == 1
    assert body["warnings"] == []
    assert body["results"][0]["item_type"] == "Requirement"
    assert body["results"][0]["artifact_id"] == str(requirement.artifact_id)
    assert body["results"][0]["locked"] is None
    assert set(body) >= {"count", "next", "previous", "page_size", "max_page_size"}


def test_apply_stale_view_is_200_empty_with_warning(
    authed_client, workspace, requirement
):
    view_id = _create(authed_client, workspace).json()["id"]
    set_request_tenant(workspace.tenant_id)
    try:
        SavedView.objects.filter(id=view_id).update(
            filters={"removed_attribute": {"op": "contains", "value": "x"}}
        )
    finally:
        clear_request_tenant()

    response = authed_client.get(f"{COLLECTION}{view_id}/apply/")
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert len(body["warnings"]) == 1
    assert "removed_attribute" in body["warnings"][0]


def test_apply_accepts_its_own_workspace_as_a_fence(authed_client, workspace):
    """The table sends the workspace with every read; applying its own view works."""
    view_id = _create(authed_client, workspace).json()["id"]

    ok = authed_client.get(
        f"{COLLECTION}{view_id}/apply/", {"workspace_id": str(workspace.id)}
    )
    assert ok.status_code == 200
    assert ok.json()["warnings"] == []


def test_apply_rejects_a_view_of_another_workspace(authed_client, workspace):
    """A workspace id that the view does not belong to is a 404, not a silent apply."""
    view_id = _create(authed_client, workspace).json()["id"]

    foreign = authed_client.get(
        f"{COLLECTION}{view_id}/apply/",
        {"workspace_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert foreign.status_code == 404


def test_apply_unknown_query_param_400(authed_client, workspace):
    view_id = _create(authed_client, workspace).json()["id"]

    assert (
        authed_client.get(f"{COLLECTION}{view_id}/apply/", {"nope": "1"}).status_code
        == 400
    )


# ---------------------------------------------------------------------------
# Per-user table state
# ---------------------------------------------------------------------------


def test_state_roundtrip_and_defaults(authed_client, workspace):
    default = authed_client.get(
        STATE, {"workspace_id": str(workspace.id), "item_type": "Requirement"}
    )
    assert default.status_code == 200
    body = default.json()
    assert body["columns"] == []
    assert body["filters"] == {}
    assert body["sort"] == []

    put = authed_client.put(
        STATE,
        {
            "columns": [{"field": "title", "order": 0}],
            "filters": {"title": {"op": "contains", "value": "a"}},
            "sort": [{"field": "title", "dir": "desc"}],
        },
        format="json",
        QUERY_STRING=f"workspace_id={workspace.id}&item_type=Requirement",
    )
    assert put.status_code == 200, put.content
    assert put.json()["columns"] == [{"field": "title", "order": 0}]

    reread = authed_client.get(
        STATE, {"workspace_id": str(workspace.id), "item_type": "Requirement"}
    )
    assert reread.json()["sort"] == [{"field": "title", "dir": "desc"}]


def test_state_requires_item_type(authed_client, workspace):
    response = authed_client.get(STATE, {"workspace_id": str(workspace.id)})

    assert response.status_code == 400


def test_state_rejects_oversized_payload(authed_client, workspace):
    response = authed_client.put(
        STATE,
        {"columns": [{"field": "x" * (33 * 1024)}]},
        format="json",
        QUERY_STRING=f"workspace_id={workspace.id}&item_type=Requirement",
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_routes_resolve_to_their_views():
    from django.urls import resolve

    from rest_api.saved_view_views import (
        SavedViewApplyView,
        SavedViewCollectionView,
        SavedViewDetailView,
        UserTableViewStateView,
    )

    assert resolve(COLLECTION).func.cls is SavedViewCollectionView
    assert (
        resolve(f"{COLLECTION}{uuid.uuid4()}/").func.cls is SavedViewDetailView
    )
    assert (
        resolve(f"{COLLECTION}{uuid.uuid4()}/apply/").func.cls
        is SavedViewApplyView
    )
    assert resolve(STATE).func.cls is UserTableViewStateView
