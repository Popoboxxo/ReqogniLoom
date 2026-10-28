"""T-A2-8 / PR-A21b: the ``similar`` endpoint derives its own authority.

``GET /api/v1/tracelinks/similar/`` now scopes the vector query to the workspace
of the query link's **source artifact** -- resolved server-side from the row,
never from a client parameter. The tests pin both halves of that rule:

* a link whose source lives in a workspace the caller cannot read is
  indistinguishable from a missing link (404), instead of answering with a
  tenant-wide neighbour list;
* a client-supplied ``workspace_id`` is ignored, so it cannot widen (or
  address) the result set.

req_id: REQ-L2-VS-004
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, TraceLink, User, Workspace
from traceability.types import LinkType

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_LINK = LinkType.REFERENCES.value
_DIM = EMBEDDING_VECTOR_DIMENSIONS


def _scenario() -> tuple[Tenant, User, Workspace, Workspace]:
    """Tenant with two workspaces; the user is admin only in the first one."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"A21B-{suffix}", slug=f"a21b-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"a21b-{suffix}", email=f"a21b-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(
            tenant=tenant, name="WS A", preset={"name": "extended"}
        )
        ws_b = Workspace.objects.create(
            tenant=tenant, name="WS B", preset={"name": "extended"}
        )
        for workspace in (ws_a, ws_b):
            provision_workspace_link_types(
                workspace_id=workspace.id, tenant_id=tenant.id
            )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=ws_a, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, ws_a, ws_b


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


def _artifact(tenant: Tenant, workspace: Workspace, name: str) -> Artifact:
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            custom_fields={"name": name},
        )
    finally:
        clear_request_tenant()


def _link(tenant: Tenant, workspace: Workspace, name: str) -> TraceLink:
    """An embedded link whose two endpoints live in *workspace*."""
    source = _artifact(tenant, workspace, f"{name} src")
    target = _artifact(tenant, workspace, f"{name} tgt")
    set_request_tenant(tenant.id)
    try:
        return TraceLink.objects.create(
            tenant=tenant,
            source=source,
            target=target,
            link_type=_LINK,
            proposed_at=None,
            embedding=[1.0] * _DIM,
        )
    finally:
        clear_request_tenant()


def test_similar_of_a_link_in_a_foreign_workspace_is_not_found() -> None:
    """No READ in the link's workspace -> 404, never a tenant-wide answer."""
    tenant, user, _ws_a, ws_b = _scenario()
    foreign = _link(tenant, ws_b, "foreign")
    # A neighbour in the same foreign workspace would be reachable via the old
    # unscoped (pgvector) path, so it is the concrete widening this prevents.
    _link(tenant, ws_b, "foreign neighbour")

    resp = _client(user).get(f"/api/v1/tracelinks/similar/?tracelink_id={foreign.id}")

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_a_client_workspace_id_is_not_an_authority() -> None:
    """Only a workspace the caller may read is accepted, and it cannot re-scope.

    The endpoint never reads ``workspace_id``; the request pipeline already
    rejects a workspace the caller has no role in, so the parameter can neither
    widen nor redirect the result set.
    """
    tenant, user, ws_a, ws_b = _scenario()
    query = _link(tenant, ws_a, "query")
    _link(tenant, ws_a, "neighbour")
    client = _client(user)

    plain = client.get(f"/api/v1/tracelinks/similar/?tracelink_id={query.id}")
    own = client.get(
        f"/api/v1/tracelinks/similar/?tracelink_id={query.id}&workspace_id={ws_a.id}"
    )
    foreign = client.get(
        f"/api/v1/tracelinks/similar/?tracelink_id={query.id}&workspace_id={ws_b.id}"
    )

    assert plain.status_code == 200, plain.content
    assert own.status_code == 200, own.content
    assert own.json() == plain.json()
    assert foreign.status_code == 403, foreign.content


def test_similar_of_an_embeddable_link_returns_its_neighbour() -> None:
    """Sanity: the derived workspace scope keeps the happy path working."""
    tenant, user, ws_a, _ws_b = _scenario()
    query = _link(tenant, ws_a, "query")
    neighbour = _link(tenant, ws_a, "neighbour")

    resp = _client(user).get(f"/api/v1/tracelinks/similar/?tracelink_id={query.id}")

    assert resp.status_code == 200, resp.content
    assert [row["id"] for row in resp.json()] == [str(neighbour.id)]
