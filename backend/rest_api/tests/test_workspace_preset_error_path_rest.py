"""REST-level regression coverage for the preset-switch error path.

leaf_id : COMP-RA-WS (WorkspaceViewSet.set_preset)
req_id  : REQ-L2-RF-007, REQ-L2-RF-012

``PATCH /api/v1/workspaces/{pk}/preset/`` used to answer 500 for a workspace id
with no row: the tier switch resolves that id through the preset gate's
unscoped managers, which raise ``Workspace.DoesNotExist`` before
``WorkspaceService`` can translate it into the ``NotFoundError`` its handler
already maps to 404. The generic ``except Exception`` fallback then masked the
routing miss as a server fault.

Pinned here through the real middleware stack (JWT, RBAC, service layer, test
database): an unknown id must answer 404 ``NOT_FOUND`` exactly like
``retrieve`` does, and a known workspace must still switch its tier.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant with one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"ws-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ws-{suffix}", email=f"ws-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS Preset Error", preset={"name": "extended"}
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


def test_set_preset_of_unknown_workspace_returns_404() -> None:
    """An id with no row is a routing miss (404), never a masked 500."""
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{uuid.uuid4()}/preset/", {"preset": "minimal"}, format="json"
    )

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_set_preset_of_known_workspace_switches_the_tier() -> None:
    """Positive counterpart: the happy path stays 2xx and reports the new tier."""
    _, user, workspace = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{workspace.id}/preset/", {"preset": "standard"}, format="json"
    )

    assert resp.status_code == 200, resp.content
    assert resp.json() == {"id": str(workspace.id), "preset": "standard"}
