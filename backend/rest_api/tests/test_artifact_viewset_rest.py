"""REST-level coverage for ArtifactViewSet (views.py).

leaf_id : COMP-RA-AR (ArtifactViewSet)
req_id  : REQ-L2-RA-001, REQ-034, REQ-066

The Artifact ViewSet is the generic container endpoint behind every entity
editor. ``test_views.py`` drives it with a mocked service; this module uses the
real middleware stack (JWT, RBAC, service layer, test database) so the
handler-level mapping is exercised:

  - ``list`` workspace scoping (missing/invalid ``workspace_id`` -> 400);
  - CRUD happy paths including the soft-delete 204;
  - the ``baseline-membership`` read action (#399) with its empty-list contract
    and its 404 for an artifact outside the tenant.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"ar-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ar-{suffix}", email=f"ar-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="AR WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _artifact(tenant: Tenant, workspace: Workspace, **fields) -> Artifact:
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="generic", **fields
        )
    finally:
        clear_request_tenant()


def _create_artifact(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "artifact_type": "generic",
        **overrides,
    }
    resp = client.post("/api/v1/artifacts/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# Auth + validation guards
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/artifacts/").status_code == 401


def test_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/artifacts/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_list_rejects_invalid_workspace_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/artifacts/?workspace_id=nope")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


def test_list_of_unknown_workspace_is_an_empty_page() -> None:
    """``list_child_summaries`` is a filtered read: an unknown workspace lists
    nothing (200) rather than inventing a 404 the service never raises."""
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/artifacts/?workspace_id={uuid.uuid4()}")
    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 0


def test_create_without_workspace_id_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        "/api/v1/artifacts/", {"artifact_type": "generic"}, format="json"
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "workspace_id" in fields


def test_retrieve_malformed_uuid_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/artifacts/not-a-uuid/")
    assert resp.status_code == 400, resp.content
    assert "well-formed UUID" in resp.json()["error"]["message"]


def test_retrieve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/artifacts/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# Happy path CRUD
# ---------------------------------------------------------------------------


def test_full_crud_roundtrip() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = _create_artifact(
        client, workspace, artifact_type="Document", custom_fields={"name": "Doc"}
    )
    artifact_id = created["id"]
    assert created["artifact_type"] == "Document"

    detail = client.get(f"/api/v1/artifacts/{artifact_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["id"] == artifact_id

    listed = client.get(f"/api/v1/artifacts/?workspace_id={workspace.id}")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [artifact_id]

    child = _create_artifact(
        client,
        workspace,
        artifact_type="Section",
        parent_id=artifact_id,
        custom_fields={"name": "Section 1"},
    )
    assert child["parent_id"] == artifact_id

    patched = client.patch(
        f"/api/v1/artifacts/{artifact_id}/",
        {"artifact_type": "Document", "custom_fields": {"name": "Doc v2"}},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["artifact_type"] == "Document"

    deleted = client.delete(f"/api/v1/artifacts/{artifact_id}/")
    assert deleted.status_code == 204, deleted.content

    missing = client.get(f"/api/v1/artifacts/{artifact_id}/")
    assert missing.status_code == 404, missing.content


def test_patch_unknown_artifact_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"/api/v1/artifacts/{uuid.uuid4()}/", {"artifact_type": "generic"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_delete_unknown_artifact_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).delete(f"/api/v1/artifacts/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_list_is_scoped_to_the_tenant() -> None:
    _tenant, user, workspace = _scenario()
    created = _create_artifact(_client(user), workspace)

    other_tenant, _, other_ws = _scenario()
    _artifact(other_tenant, other_ws)

    resp = _client(user).get(f"/api/v1/artifacts/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert [row["id"] for row in resp.json()["results"]] == [created["id"]]


# ---------------------------------------------------------------------------
# baseline-membership (#399)
# ---------------------------------------------------------------------------


def test_baseline_membership_of_an_artifact_in_no_baseline() -> None:
    tenant, user, workspace = _scenario()
    artifact = _artifact(tenant, workspace)

    resp = _client(user).get(f"/api/v1/artifacts/{artifact.id}/baseline-membership/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["artifact_id"] == str(artifact.id)
    assert body["drifted"] is False
    assert body["memberships"] == []


def test_baseline_membership_unknown_artifact_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(
        f"/api/v1/artifacts/{uuid.uuid4()}/baseline-membership/"
    )
    assert resp.status_code == 404, resp.content


def test_baseline_membership_of_foreign_tenant_artifact_is_404() -> None:
    """Cross-tenant isolation: another tenant's artifact is not addressable."""
    _tenant, user, _workspace = _scenario()
    foreign_tenant, _, foreign_ws = _scenario()
    foreign = _artifact(foreign_tenant, foreign_ws)

    resp = _client(user).get(f"/api/v1/artifacts/{foreign.id}/baseline-membership/")

    assert resp.status_code == 404, resp.content
