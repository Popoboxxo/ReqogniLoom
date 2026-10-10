"""REST-level coverage for ArchitectureElementViewSet (views.py).

leaf_id : COMP-RA-AE (ArchitectureElementViewSet)
req_id  : REQ-L2-RA-001, REQ-L3-RF004-004, REQ-L1-042, REQ-L1-044, REQ-171

The MBSE container endpoint behind the architecture editor. This module drives
the real middleware stack (JWT, RBAC, service layer, test database):

  - CRUD happy paths, including the deliberate soft-delete contract (DELETE ->
    204, ``retrieve`` stays 404 afterwards, ``include_deleted=true`` re-lists);
  - the ASIL / Make-or-Buy extension fields on create and the presence-checked
    field forwarding on PATCH (an omitted key must not NULL the column);
  - the client-``uid`` rejection (#932) — a system-owned identifier;
  - ``allocation-coverage`` for an element with no allocations;
  - the ``?search=`` filter and the cross-tenant read fence.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import ArchitectureElement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_BASE = "/api/v1/architecture/"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"ae-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ae-{suffix}", email=f"ae-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="AE WS", preset={"name": "extended"}
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


def _create_element(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "AE element",
        "description": "a subsystem",
        "element_type": "component",
        **overrides,
    }
    resp = client.post(_BASE, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _initialize_workflow(client: APIClient, workspace: Workspace) -> None:
    """Seed the ArchitectureElement workflow definition the soft-delete needs."""
    resp = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "ArchitectureElement"},
        format="json",
    )
    assert resp.status_code == 201, resp.content


# ---------------------------------------------------------------------------
# Auth + validation guards
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    assert APIClient().get(_BASE).status_code == 401


def test_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(_BASE + "?search=x")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_list_rejects_invalid_workspace_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(_BASE + "?workspace_id=nope")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


def test_create_without_title_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        _BASE, {"workspace_id": str(workspace.id)}, format="json"
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "title" in fields


def test_create_with_client_supplied_uid_returns_400() -> None:
    """#932: ``uid`` is system-generated — a client value is refused, not dropped."""
    _, user, workspace = _scenario()
    resp = _client(user).post(
        _BASE,
        {"workspace_id": str(workspace.id), "title": "AE element", "uid": "AE-1"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    details = {d["field"]: d["errors"] for d in resp.json()["error"]["details"]}
    assert "uid" in details
    assert not ArchitectureElement.unscoped.filter(uid="AE-1").exists()


def test_retrieve_malformed_uuid_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(_BASE + "not-a-uuid/")
    assert resp.status_code == 400, resp.content
    assert "well-formed UUID" in resp.json()["error"]["message"]


def test_retrieve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"{_BASE}{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# Happy path CRUD
# ---------------------------------------------------------------------------


def test_full_crud_roundtrip_with_soft_delete() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = _create_element(client, workspace, title="Roundtrip", asil_level="QM")
    element_id = created["id"]
    assert created["asil_level"] == "QM"
    assert created["uid"], "the service allocates a local uid"

    detail = client.get(f"{_BASE}{element_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["title"] == "Roundtrip"

    listed = client.get(f"{_BASE}?workspace_id={workspace.id}&search=Roundtrip")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [element_id]

    # An omitted asil_level must not clear the column (sentinel semantics).
    patched = client.patch(
        f"{_BASE}{element_id}/",
        {"description": "tightened", "change_reason": "review"},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["asil_level"] == "QM"

    _initialize_workflow(client, workspace)
    deleted = client.delete(f"{_BASE}{element_id}/")
    assert deleted.status_code == 204, deleted.content

    # ArchitectureElement deliberately keeps 404ing after the soft delete (no
    # status mirror), but the record re-appears behind include_deleted.
    hidden = client.get(f"{_BASE}{element_id}/")
    assert hidden.status_code == 404, hidden.content

    included = client.get(
        f"{_BASE}?workspace_id={workspace.id}&include_deleted=true&search=Roundtrip"
    )
    assert [row["id"] for row in included.json()["results"]] == [element_id]

    default_listing = client.get(f"{_BASE}?workspace_id={workspace.id}&search=Roundtrip")
    assert default_listing.json()["count"] == 0


def test_create_accepts_make_or_buy() -> None:
    _, user, workspace = _scenario()
    created = _create_element(
        _client(user), workspace, title="Buy or make", make_or_buy="Buy"
    )

    assert created["make_or_buy"] == "Buy"


def test_patch_unknown_element_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"{_BASE}{uuid.uuid4()}/", {"title": "x"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_delete_unknown_element_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).delete(f"{_BASE}{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_retrieve_of_foreign_tenant_element_is_404() -> None:
    _tenant, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    foreign = _create_element(_client(other_user), other_ws)

    resp = _client(user).get(f"{_BASE}{foreign['id']}/")
    assert resp.status_code == 404, resp.content

    own = _client(user).get(f"{_BASE}{created['id']}/")
    assert own.status_code == 200, own.content


def test_list_is_scoped_to_the_tenant() -> None:
    _, user, workspace = _scenario()
    _create_element(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    _create_element(_client(other_user), other_ws)

    resp = _client(user).get(f"{_BASE}?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# allocation-coverage (REQ-L1-042)
# ---------------------------------------------------------------------------


def test_allocation_coverage_of_an_unallocated_element() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    element_id = _create_element(client, workspace)["id"]

    resp = client.get(f"{_BASE}{element_id}/allocation-coverage/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["allocated_count"] == 0
    assert body["unallocated_requirements"] == []


def test_allocation_coverage_unknown_element_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"{_BASE}{uuid.uuid4()}/allocation-coverage/")
    assert resp.status_code == 404, resp.content
