"""API test for workspace-default theme persistence (multi-palette theming, #568 phase 1).

Verifies the PATCH/GET /api/v1/workspaces/{pk}/ round-trip for the new
``theme`` field, which mirrors how ``language`` is already stored in the
``Workspace.preset`` JSON blob (see WorkspaceService.update_metadata,
task 1 of #568 phase 1).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _tenant_user_workspace(name: str) -> tuple[Tenant, User, Workspace]:
    slug = f"wstheme-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"tier": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert ACCESS_COOKIE_NAME in client.cookies
    return client


def test_patch_theme_persists_and_is_returned() -> None:
    _, user, workspace = _tenant_user_workspace("Theme API WS")
    client = _client(user)

    resp = client.patch(
        f"/api/v1/workspaces/{workspace.id}/", {"theme": "light"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.data["theme"] == "light"

    resp = client.get(f"/api/v1/workspaces/{workspace.id}/")
    assert resp.status_code == 200, resp.content
    assert resp.data["theme"] == "light"


def test_default_theme_is_dark_when_unset() -> None:
    _, user, workspace = _tenant_user_workspace("Theme Default WS")
    client = _client(user)

    resp = client.get(f"/api/v1/workspaces/{workspace.id}/")
    assert resp.status_code == 200, resp.content
    assert resp.data["theme"] == "dark"
