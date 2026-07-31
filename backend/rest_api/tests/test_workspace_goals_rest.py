"""REST coverage for Workspace ``goals_enabled``/``goals_ai_enabled`` fields.

Verifies the PATCH /api/v1/workspaces/{pk}/ write path persists and
round-trips the two boolean toggles surfaced by the WorkspaceSettings UI
(REQ-L2-RF-012).
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext

_JWT = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _admin_ctx(tenant, user):
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def admin_client(db):
    tenant = Tenant.objects.create(name="GoalsRestTenant")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        tenant=tenant, username="goalsadmin", email="a@x.io", is_active=True
    )
    user.set_password("goalspass123")
    user.save()
    ctx = _admin_ctx(tenant, user)
    # create_workspace() already grants the creator an 'admin' UserRole (#232).
    ws = WorkspaceService().create_workspace(ctx, name="WS", preset="extended")

    client = APIClient()
    with override_settings(**_JWT):
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": "goalsadmin", "password": "goalspass123"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    TenantContext.clear_tenant()
    return client, tenant, user, ws


@override_settings(**_JWT)
@pytest.mark.django_db
def test_patch_workspace_goals_enabled_persists_and_round_trips(admin_client):
    client, tenant, user, ws = admin_client

    resp = client.get(f"/api/v1/workspaces/{ws.id}/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["goals_enabled"] is False
    assert resp.json()["goals_ai_enabled"] is False

    resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/",
        {"goals_enabled": True},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["goals_enabled"] is True
    assert resp.json()["goals_ai_enabled"] is False

    # Re-fetch to confirm persistence beyond the in-memory response.
    resp = client.get(f"/api/v1/workspaces/{ws.id}/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["goals_enabled"] is True

    resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/",
        {"goals_ai_enabled": True},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["goals_enabled"] is True
    assert resp.json()["goals_ai_enabled"] is True
