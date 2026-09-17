# backend/rest_api/tests/test_api_key_views_rbac.py
"""RBAC regression tests for ApiKeyViewSet (issue #716).

A workspace Viewer previously had ZERO path to programmatic API access:
``POST /api/v1/api-keys/`` demanded workspace ``write`` (the ``RbacPermission``
HTTP-method default for POST), which only Editor/Approver/Admin hold. Since
API-key creation/revocation is inherently self-scoped (a user only ever
manages THEIR OWN keys — see ``ApiKeyViewSet``'s service calls), the fix
declares ``required_operation = Operation.READ`` on the ViewSet so a Viewer
(who does hold READ) can create and revoke their own key, while a user with
no role anywhere in the tenant (who holds neither READ nor WRITE) remains
correctly denied.

Uses the same real-login-via-APIClient pattern as
``rest_api/tests/test_user_management_views.py`` so the actual DRF
``RbacPermission`` permission-check pipeline is exercised end to end (unlike
the pre-existing unit tests in ``auth_tenancy/tests/test_api_key_rest.py``,
which call ``ApiKeyViewSet`` methods directly and therefore never go through
permission_classes at all).
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="AK-RBAC-T", slug="ak-rbac-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="AK-RBAC-WS", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


def _make_authed_client(
    tenant: Tenant, workspace: Workspace | None, *, role: str | None
) -> APIClient:
    """Create a user, log them in, and return an authed client.

    ``role=None`` creates a user with NO role assignment anywhere in the
    tenant (the "correctly still denied" control case).
    """
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=f"ak-rbac-{role or 'none'}",
            email=f"ak-rbac-{role or 'none'}@t.test",
            tenant=tenant,
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        if role is not None:
            assert workspace is not None
            UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=role)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.mark.django_db
def test_create_api_key_succeeds_for_viewer_role(tenant, workspace):
    """A Viewer (READ-only role) can create their own API key (#716)."""
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    resp = client.post("/api/v1/api-keys/", {"name": "my-viewer-key"}, format="json")

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["name"] == "my-viewer-key"
    assert body["plaintext"].startswith("reqlo_")


@pytest.mark.django_db
def test_create_api_key_denied_for_user_with_no_role_anywhere(tenant, workspace):
    """A user with NO role in any workspace remains denied (no loosening beyond #716)."""
    client = _make_authed_client(tenant, workspace, role=None)

    resp = client.post("/api/v1/api-keys/", {"name": "should-fail"}, format="json")

    assert resp.status_code == 403, resp.content


@pytest.mark.django_db
def test_viewer_can_revoke_their_own_api_key(tenant, workspace):
    """A Viewer can also revoke (DELETE) the key they just created.

    Without this, a Viewer could create a key but nobody (least of all
    the Viewer themself, since revocation is scoped to the caller's own
    user id) could ever revoke it again.
    """
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    create_resp = client.post("/api/v1/api-keys/", {"name": "revoke-me"}, format="json")
    assert create_resp.status_code == 201, create_resp.content
    key_id = create_resp.json()["id"]

    destroy_resp = client.delete(f"/api/v1/api-keys/{key_id}/")
    assert destroy_resp.status_code == 204, destroy_resp.content


@pytest.mark.django_db
def test_viewer_can_list_their_own_api_keys(tenant, workspace):
    """GET already worked before the fix (READ was already the default);
    kept here as a regression guard that the fix did not narrow it."""
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    resp = client.get("/api/v1/api-keys/")

    assert resp.status_code == 200, resp.content
