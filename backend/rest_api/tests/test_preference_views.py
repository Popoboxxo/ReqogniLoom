"""
REQ-L1-027 — UserWorkspacePreference REST endpoint tests.

End-to-end HTTP coverage for:
- GET  /api/v1/users/me/preferences/?workspace_id=<uuid>
- PATCH /api/v1/users/me/preferences/

Uses the same JWT + APIClient pattern as test_auth_login.py.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def pref_user(db):
    """An admin user with a workspace for preference tests."""
    tenant = Tenant.objects.create(name="Pref T", slug="pref-t", is_active=True)
    user = User.objects.create(
        username="prefadmin", email="prefadmin@t.test", tenant=tenant
    )
    user.set_password("prefpass123")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Pref WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
        yield user
    finally:
        clear_request_tenant()


def _login(client: APIClient) -> str:
    """Log in and return the Bearer token."""
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "prefadmin", "password": "prefpass123"},
        format="json",
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def _auth(client: APIClient, token: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_preferences_404_when_none(pref_user):
    """GET returns 404 when no preference row exists yet."""
    client = APIClient()
    token = _login(client)
    _auth(client, token)

    ws = Workspace.objects.get(name="Pref WS")
    resp = client.get(f"/api/v1/users/me/preferences/?workspace_id={ws.id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_preferences_400_without_workspace_id(pref_user):
    """GET without workspace_id returns 400."""
    client = APIClient()
    token = _login(client)
    _auth(client, token)

    resp = client.get("/api/v1/users/me/preferences/")
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_creates_preference(pref_user):
    """PATCH creates a preference row on first access and returns it."""
    client = APIClient()
    token = _login(client)
    _auth(client, token)

    ws = Workspace.objects.get(name="Pref WS")
    resp = client.patch(
        "/api/v1/users/me/preferences/",
        {
            "workspace_id": str(ws.id),
            "optional_artifact_visibility": {"adr": False, "risk": True},
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["optional_artifact_visibility"]["adr"] is False
    assert body["optional_artifact_visibility"]["risk"] is True
    assert body["workspace_id"] == str(ws.id)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_merges_overrides(pref_user):
    """Second PATCH merges with existing overrides."""
    client = APIClient()
    token = _login(client)
    _auth(client, token)

    ws = Workspace.objects.get(name="Pref WS")

    # First PATCH
    client.patch(
        "/api/v1/users/me/preferences/",
        {
            "workspace_id": str(ws.id),
            "optional_artifact_visibility": {"adr": False},
        },
        format="json",
    )

    # Second PATCH — should merge, not replace
    resp = client.patch(
        "/api/v1/users/me/preferences/",
        {
            "workspace_id": str(ws.id),
            "optional_artifact_visibility": {"issue": False},
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["optional_artifact_visibility"]["adr"] is False
    assert body["optional_artifact_visibility"]["issue"] is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_after_patch(pref_user):
    """GET returns the preference after a PATCH has created it."""
    client = APIClient()
    token = _login(client)
    _auth(client, token)

    ws = Workspace.objects.get(name="Pref WS")
    client.patch(
        "/api/v1/users/me/preferences/",
        {
            "workspace_id": str(ws.id),
            "optional_artifact_visibility": {"diagrams": False},
        },
        format="json",
    )

    resp = client.get(f"/api/v1/users/me/preferences/?workspace_id={ws.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["optional_artifact_visibility"]["diagrams"] is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_rejects_non_bool_values(pref_user):
    """PATCH rejects non-boolean values in the visibility dict."""
    client = APIClient()
    token = _login(client)
    _auth(client, token)

    ws = Workspace.objects.get(name="Pref WS")
    resp = client.patch(
        "/api/v1/users/me/preferences/",
        {
            "workspace_id": str(ws.id),
            "optional_artifact_visibility": {"adr": "yes"},
        },
        format="json",
    )
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_unauthenticated_returns_401(pref_user):
    """Unauthenticated requests are rejected."""
    client = APIClient()
    ws = Workspace.objects.get(name="Pref WS")
    resp = client.get(f"/api/v1/users/me/preferences/?workspace_id={ws.id}")
    assert resp.status_code in (401, 403)
