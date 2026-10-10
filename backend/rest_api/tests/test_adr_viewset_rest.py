"""REST-level coverage for AdrViewSet (views.py).

leaf_id : COMP-RA-AD (AdrViewSet)
req_id  : REQ-L2-RA-001, REQ-L3-ADR-005, REQ-L1-090, REQ-L1-091

Architecture Decision Records at REST level. This module drives the real
middleware stack (JWT, RBAC, service layer, test database):

  - CRUD happy paths including the soft-delete contract (DELETE -> 204, the row
    survives behind ``?include_deleted=true``);
  - the ``diff``/``versions`` read actions and their 400/404 guards;
  - the ``supersede`` action (REQ-L3-ADR-005): the missing REST entry point for
    the successor-recording transition, including the payload guard;
  - the cross-tenant read fence.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Adr, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_BASE = "/api/v1/adrs/"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"ad-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ad-{suffix}", email=f"ad-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="AD WS", preset={"name": "extended"}
        )
        # The supersede action records its successor as a 'decides' trace
        # link — link validation is always-on, so the workspace needs its
        # link-type catalog (see rest_api/conftest).
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
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


def _create_adr(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "AD decision",
        "description": "we chose X",
        "context": "the context",
        "decision": "the decision",
        "consequences": "the consequences",
        **overrides,
    }
    resp = client.post(_BASE, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _initialize_workflow(client: APIClient, workspace: Workspace) -> None:
    """Seed the Adr workflow definition the soft-delete/transition needs."""
    resp = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "Adr"},
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


def test_create_without_title_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        _BASE, {"workspace_id": str(workspace.id)}, format="json"
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "title" in fields


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
# Happy path CRUD + soft delete
# ---------------------------------------------------------------------------


def test_full_crud_roundtrip_with_soft_delete() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = _create_adr(client, workspace, title="Roundtrip")
    adr_id = created["id"]

    detail = client.get(f"{_BASE}{adr_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["title"] == "Roundtrip"

    listed = client.get(f"{_BASE}?workspace_id={workspace.id}&search=Roundtrip")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [adr_id]

    patched = client.patch(
        f"{_BASE}{adr_id}/",
        {"decision": "the decision v2", "change_reason": "updated after review"},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["decision"] == "the decision v2"

    _initialize_workflow(client, workspace)
    deleted = client.delete(f"{_BASE}{adr_id}/")
    assert deleted.status_code == 204, deleted.content

    still_there = client.get(f"{_BASE}{adr_id}/")
    assert still_there.status_code == 200, still_there.content
    assert still_there.json()["status"] == "outdated"

    hidden = client.get(f"{_BASE}?workspace_id={workspace.id}&search=Roundtrip")
    assert hidden.json()["count"] == 0

    included = client.get(
        f"{_BASE}?workspace_id={workspace.id}&search=Roundtrip&include_deleted=true"
    )
    assert included.json()["count"] == 1


def test_patch_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"{_BASE}{uuid.uuid4()}/", {"title": "x"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_delete_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).delete(f"{_BASE}{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_retrieve_of_foreign_tenant_adr_is_404() -> None:
    _tenant, user, workspace = _scenario()
    created = _create_adr(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    foreign = _create_adr(_client(other_user), other_ws)

    resp = _client(user).get(f"{_BASE}{foreign['id']}/")
    assert resp.status_code == 404, resp.content

    own = _client(user).get(f"{_BASE}{created['id']}/")
    assert own.status_code == 200, own.content


def test_list_is_scoped_to_the_tenant() -> None:
    _, user, workspace = _scenario()
    _create_adr(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    _create_adr(_client(other_user), other_ws)

    resp = _client(user).get(f"{_BASE}?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# diff / versions
# ---------------------------------------------------------------------------


def test_versions_and_diff_of_a_new_adr() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    adr_id = _create_adr(client, workspace)["id"]

    versions = client.get(f"{_BASE}{adr_id}/versions/")
    assert versions.status_code == 200, versions.content

    diff = client.get(f"{_BASE}{adr_id}/diff/?from_version=0&to_version=1")
    assert diff.status_code == 200, diff.content


def test_diff_with_non_integer_version_returns_400() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    adr_id = _create_adr(client, workspace)["id"]

    resp = client.get(f"{_BASE}{adr_id}/diff/?from_version=abc")
    assert resp.status_code == 400, resp.content


def test_diff_of_unknown_adr_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"{_BASE}{uuid.uuid4()}/diff/?from_version=0")
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# supersede (REQ-L3-ADR-005)
# ---------------------------------------------------------------------------


def test_supersede_without_superseded_by_id_returns_400() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    adr_id = _create_adr(client, workspace)["id"]

    resp = client.post(f"{_BASE}{adr_id}/supersede/", {}, format="json")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "superseded_by_id is required"


def test_supersede_records_the_successor_link() -> None:
    """REQ-L3-ADR-005: walking the ADR to ``Approved`` and superseding it there
    records the successor as a ``decides`` link new -> old."""
    from persistence.models import TraceLink
    from traceability.types import LinkType

    tenant, user, workspace = _scenario()
    client = _client(user)
    # The workflow graph must exist before the items are created, so the
    # engine finds a WorkflowItemState to transition.
    _initialize_workflow(client, workspace)
    old = _create_adr(client, workspace, title="Old decision")
    new = _create_adr(client, workspace, title="New decision")

    for target_state in ("In Review", "Approved"):
        step = client.post(
            f"{_BASE}{old['id']}/transitions/",
            {"target_state": target_state, "change_reason": "reviewed"},
            format="json",
        )
        assert step.status_code == 200, f"{target_state}: {step.content}"

    resp = client.post(
        f"{_BASE}{old['id']}/supersede/",
        {"superseded_by_id": new["id"], "change_reason": "superseded by the new one"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["id"] == old["id"]
    assert body["status"] == "Superseded", resp.content

    # The successor is recorded as a 'decides' link, with both endpoints
    # resolved to their backing Artifact rows.
    set_request_tenant(tenant.id)
    try:
        old_artifact = Adr.objects.get(id=old["id"]).artifact_id
        new_artifact = Adr.objects.get(id=new["id"]).artifact_id
    finally:
        clear_request_tenant()

    assert TraceLink.unscoped.filter(
        source_id=new_artifact,
        target_id=old_artifact,
        link_type=LinkType.DECIDES.value,
    ).exists(), "the successor is recorded as a trace link"
