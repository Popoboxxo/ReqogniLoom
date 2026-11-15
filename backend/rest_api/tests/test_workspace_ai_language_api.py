"""API test for the workspace AI-language setting (S7, spec §7.6/E10).

``Workspace.ai_language`` is a dedicated column (not part of the UI preset
blob): the UI/content language and the language of every AI answer are
deliberately independent. These tests pin the REST round-trip and the default.
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
    slug = f"wsai-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"tier": "standard", "language": "de"}
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


def test_default_ai_language_is_auto() -> None:
    _, user, workspace = _tenant_user_workspace("AI Language Default WS")
    client = _client(user)

    resp = client.get(f"/api/v1/workspaces/{workspace.id}/")

    assert resp.status_code == 200, resp.content
    assert resp.data["ai_language"] == "auto"
    # The UI/content language lives on the preset blob and is independent.
    assert resp.data["language"] == "de"


def test_patch_ai_language_persists_and_is_returned() -> None:
    _, user, workspace = _tenant_user_workspace("AI Language Patch WS")
    client = _client(user)

    resp = client.patch(
        f"/api/v1/workspaces/{workspace.id}/", {"ai_language": "en"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.data["ai_language"] == "en"

    resp = client.get(f"/api/v1/workspaces/{workspace.id}/")
    assert resp.status_code == 200, resp.content
    assert resp.data["ai_language"] == "en"


def test_invalid_ai_language_is_rejected() -> None:
    _, user, workspace = _tenant_user_workspace("AI Language Invalid WS")
    client = _client(user)

    resp = client.patch(
        f"/api/v1/workspaces/{workspace.id}/", {"ai_language": "fr"}, format="json"
    )

    assert resp.status_code == 400, resp.content
