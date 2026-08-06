"""Real-DB regression tests for GitHub issue #336.

``DELETE /api/v1/trace-links/{id}/`` was a silent no-op: the view called
``TraceLinkService.cascade_delete_trace_links(entity_id, ctx)`` and passed
the TraceLink's own ``id`` as if it were an *entity* id. ``cascade_delete_
trace_links`` only matches TraceLinks whose ``source_id``/``target_id``
equal the given id, so it never matched the link's own id, deleted zero
rows, and the view still answered 204 No Content while the link stayed in
the database.

The fix adds ``TraceLinkService.delete_trace_link(link_id, ctx)``, which
deletes the TraceLink identified by ``link_id`` itself via
``TraceLinkManager.delete`` (tenant-scoped), and wires it into
``TraceLinkViewSet.destroy``.

These tests drive the real HTTP + service + DB stack on purpose: the bug
lived exactly in the seam between the view and the service, so a mock
would hide it.
"""
from __future__ import annotations

from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TraceLink, User, Workspace

_SECRET = "test-secret-not-a-real-key-336"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def tl_env(db):
    """Tenant + admin + one workspace on the standard preset."""
    tenant = Tenant.objects.create(name="TL336 T", slug="tl336-t", is_active=True)
    admin = User.objects.create(
        username="tl336admin", email="tl336admin@t.test", tenant=tenant
    )
    admin.set_password("tl336pass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="TL336 WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace, "admin": admin}
    finally:
        clear_request_tenant()


def _client(tl_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "tl336admin", "password": "tl336pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(client: APIClient, path: str, payload: dict[str, Any]) -> dict:
    resp = client.post(path, payload, format="json")
    assert resp.status_code == 201, (path, resp.content)
    return resp.json()


def _create_trace_link(client: APIClient, ws_id: Any) -> dict:
    """Two requirements + a 'traces' TraceLink between them."""
    ws = str(ws_id)
    source = _create(
        client, "/api/v1/requirements/", {"workspace_id": ws, "title": "TL336 source"}
    )
    target = _create(
        client, "/api/v1/requirements/", {"workspace_id": ws, "title": "TL336 target"}
    )
    link = _create(
        client,
        "/api/v1/trace-links/",
        {"source_id": source["id"], "target_id": target["id"], "link_type": "traces"},
    )
    return link


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_delete_trace_link_removes_it_from_db(tl_env):
    """DELETE must actually remove the row, not just answer 204 (#336)."""
    client = _client(tl_env)
    link = _create_trace_link(client, tl_env["workspace"].id)

    resp = client.delete(f"/api/v1/trace-links/{link['id']}/")
    assert resp.status_code == 204, resp.content

    # Ground truth: the row must be gone from the database.
    assert not TraceLink.objects.filter(id=link["id"]).exists()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_delete_trace_link_then_reget_is_404(tl_env):
    """A subsequent GET on the deleted link's list must not surface it."""
    client = _client(tl_env)
    link = _create_trace_link(client, tl_env["workspace"].id)

    resp = client.delete(f"/api/v1/trace-links/{link['id']}/")
    assert resp.status_code == 204, resp.content

    listing = client.get(
        f"/api/v1/trace-links/?workspace_id={tl_env['workspace'].id}"
    )
    assert listing.status_code == 200, listing.content
    ids = [item["id"] for item in listing.json().get("results", listing.json())]
    assert link["id"] not in ids


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_delete_nonexistent_trace_link_returns_404(tl_env):
    """DELETE on an id that was never a TraceLink must be 404, not 204."""
    import uuid

    client = _client(tl_env)
    resp = client.delete(f"/api/v1/trace-links/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_delete_trace_link_twice_second_call_is_404(tl_env):
    """Deleting an already-deleted link must 404, proving it is gone for good."""
    client = _client(tl_env)
    link = _create_trace_link(client, tl_env["workspace"].id)

    first = client.delete(f"/api/v1/trace-links/{link['id']}/")
    assert first.status_code == 204, first.content

    second = client.delete(f"/api/v1/trace-links/{link['id']}/")
    assert second.status_code == 404, second.content
