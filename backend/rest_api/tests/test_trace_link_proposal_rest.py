"""REST surface for agent-proposed trace links (security review M2).

``TraceLinkService.confirm_proposed_link``/``discard_proposed_link`` existed
with no caller outside their own unit tests: a proposal could be created but
never accepted or rejected through any interface. These tests drive the real
HTTP + service + DB stack, because the gap was precisely the missing seam
between the view layer and an otherwise working service.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ApiKey, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TraceLink, User, Workspace

_SECRET = "test-secret-not-a-real-key-m2"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def tl_env(db):
    """Tenant + admin + one provisioned workspace on the standard preset."""
    tenant = Tenant.objects.create(name="M2 T", slug="m2-t", is_active=True)
    admin = User.objects.create(username="m2admin", email="m2admin@t.test", tenant=tenant)
    admin.set_password("m2pass123456")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="M2 WS", preset={"name": "standard"}
        )
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        key = ApiKey.objects.create(
            tenant=tenant,
            user=admin,
            name="m2-bot",
            key_hash="sha256p1:m2",
            principal_type="agent",
            agent_label="Claude Code",
        )
        yield {"tenant": tenant, "workspace": workspace, "admin": admin, "key": key}
    finally:
        clear_request_tenant()


def _client(tl_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "m2admin", "password": "m2pass123456"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(client: APIClient, path: str, payload: dict[str, Any]) -> dict:
    resp = client.post(path, payload, format="json")
    assert resp.status_code == 201, (path, resp.content)
    return resp.json()


def _proposed_link(client: APIClient, tl_env: dict) -> dict:
    """A trace link marked as an agent proposal, as create_trace_link would."""
    ws = str(tl_env["workspace"].id)
    source = _create(client, "/api/v1/requirements/", {"workspace_id": ws, "title": "M2 src"})
    target = _create(client, "/api/v1/requirements/", {"workspace_id": ws, "title": "M2 tgt"})
    link = _create(
        client,
        "/api/v1/trace-links/",
        {
            "source_id": source["id"],
            "target_id": target["id"],
            "link_type": "derives-from",
        },
    )
    set_request_tenant(tl_env["tenant"].id)
    try:
        TraceLink.objects.filter(id=link["id"]).update(
            proposed_by=tl_env["key"], proposed_at=timezone.now()
        )
    finally:
        clear_request_tenant()
    return link


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_list_surfaces_the_proposal_fields(tl_env):
    """The fields were declared on the serializer but never reached the wire."""
    client = _client(tl_env)
    link = _proposed_link(client, tl_env)

    resp = client.get(f"/api/v1/trace-links/?workspace_id={tl_env['workspace'].id}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    row = next(
        item for item in body.get("results", body) if item["id"] == link["id"]
    )
    assert row["proposed_by"] is not None
    assert row["proposed_at"] is not None
    assert row["proposed_by_label"] == "Claude Code"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_confirm_clears_the_proposal(tl_env):
    client = _client(tl_env)
    link = _proposed_link(client, tl_env)

    resp = client.post(f"/api/v1/trace-links/{link['id']}/confirm/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["proposed_by"] is None
    assert resp.json()["proposed_at"] is None

    set_request_tenant(tl_env["tenant"].id)
    try:
        row = TraceLink.objects.get(id=link["id"])
    finally:
        clear_request_tenant()
    assert row.is_proposal is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_discard_deletes_the_proposal(tl_env):
    client = _client(tl_env)
    link = _proposed_link(client, tl_env)

    resp = client.post(f"/api/v1/trace-links/{link['id']}/discard/")
    assert resp.status_code == 204, resp.content
    assert not TraceLink.unscoped.filter(id=link["id"]).exists()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_discard_refuses_a_confirmed_link(tl_env):
    """Only proposals go through discard; a normal link uses DELETE."""
    client = _client(tl_env)
    ws = str(tl_env["workspace"].id)
    source = _create(client, "/api/v1/requirements/", {"workspace_id": ws, "title": "M2 s2"})
    target = _create(client, "/api/v1/requirements/", {"workspace_id": ws, "title": "M2 t2"})
    link = _create(
        client,
        "/api/v1/trace-links/",
        {
            "source_id": source["id"],
            "target_id": target["id"],
            "link_type": "derives-from",
        },
    )

    resp = client.post(f"/api/v1/trace-links/{link['id']}/discard/")
    assert resp.status_code == 400, resp.content
    assert TraceLink.unscoped.filter(id=link["id"]).exists()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_confirm_unknown_link_is_404(tl_env):
    client = _client(tl_env)
    resp = client.post(f"/api/v1/trace-links/{uuid.uuid4()}/confirm/")
    assert resp.status_code == 404, resp.content
