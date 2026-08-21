# backend/rest_api/tests/test_user_management_views.py
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="UMV-T", slug="umv-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="UMV-WS", preset={"name": "extended"})
    finally:
        clear_request_tenant()


def _make_authed_client(tenant: Tenant, workspace: Workspace, *, is_tenant_admin: bool, is_workspace_admin: bool = False) -> APIClient:
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(username=f"umv-{is_tenant_admin}-{is_workspace_admin}", email=f"umv-{is_tenant_admin}-{is_workspace_admin}@t.test", tenant=tenant)
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        if is_tenant_admin:
            TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
        if is_workspace_admin:
            UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": user.username, "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.mark.django_db
def test_create_user_requires_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=False, is_workspace_admin=True)
    resp = client.post("/api/v1/users/", {"username": "newbie", "email": "newbie@t.test", "password": "a-real-password-123"}, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_user_succeeds_for_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    resp = client.post("/api/v1/users/", {"username": "newbie2", "email": "newbie2@t.test", "password": "a-real-password-123"}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.json()["username"] == "newbie2"


@pytest.mark.django_db
def test_deactivate_blocks_last_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    set_request_tenant(tenant.id)
    try:
        target = User.objects.get(username__startswith="umv-True")
    finally:
        clear_request_tenant()
    resp = client.post(f"/api/v1/users/{target.id}/deactivate/")
    assert resp.status_code == 409, resp.content
    assert resp.json()["error"] == "LAST_ADMIN"


@pytest.mark.django_db
def test_activate_succeeds_for_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    set_request_tenant(tenant.id)
    try:
        other = User.objects.create(username="umv-inactive", email="umv-inactive@t.test", tenant=tenant, is_active=False)
    finally:
        clear_request_tenant()
    resp = client.post(f"/api/v1/users/{other.id}/activate/")
    assert resp.status_code == 200, resp.content
    other.refresh_from_db()
    assert other.is_active is True


@pytest.mark.django_db
def test_grant_and_revoke_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="umv-future-admin", email="umv-future@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    grant = client.post(f"/api/v1/users/{target.id}/tenant-admin/")
    assert grant.status_code == 200, grant.content

    revoke = client.delete(f"/api/v1/users/{target.id}/tenant-admin/")
    assert revoke.status_code == 200, revoke.content

    set_request_tenant(tenant.id)
    try:
        assert AuthorizationService().is_tenant_admin(user_id=target.id, tenant_id=tenant.id) is False
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_activate_rejects_cross_tenant_target(tenant, workspace):
    """IDOR guard: a tenant-admin of tenant A must not be able to activate a
    user belonging to tenant B via the REST endpoint (403, not 500)."""
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)

    other_tenant = Tenant.objects.create(name="UMV-OTHER", slug="umv-other", is_active=True)
    set_request_tenant(other_tenant.id)
    try:
        foreign_user = User.objects.create(
            username="umv-foreign-inactive",
            email="umv-foreign-inactive@t.test",
            tenant=other_tenant,
            is_active=False,
        )
    finally:
        clear_request_tenant()

    resp = client.post(f"/api/v1/users/{foreign_user.id}/activate/")
    assert resp.status_code == 403, resp.content
    assert resp.json()["error"] == "PERMISSION_DENIED"

    set_request_tenant(other_tenant.id)
    try:
        foreign_user.refresh_from_db()
    finally:
        clear_request_tenant()
    assert foreign_user.is_active is False


@pytest.mark.django_db
def test_deactivate_rejects_cross_tenant_target(tenant, workspace):
    """IDOR guard: a tenant-admin of tenant A must not be able to deactivate
    a user belonging to tenant B via the REST endpoint (403, not 500)."""
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)

    other_tenant = Tenant.objects.create(name="UMV-OTHER2", slug="umv-other2", is_active=True)
    set_request_tenant(other_tenant.id)
    try:
        foreign_user = User.objects.create(
            username="umv-foreign-active",
            email="umv-foreign-active@t.test",
            tenant=other_tenant,
            is_active=True,
        )
    finally:
        clear_request_tenant()

    resp = client.post(f"/api/v1/users/{foreign_user.id}/deactivate/")
    assert resp.status_code == 403, resp.content
    assert resp.json()["error"] == "PERMISSION_DENIED"

    set_request_tenant(other_tenant.id)
    try:
        foreign_user.refresh_from_db()
    finally:
        clear_request_tenant()
    assert foreign_user.is_active is True


@pytest.mark.django_db
def test_grant_tenant_admin_rejects_cross_tenant_target(tenant, workspace):
    """Critical IDOR guard: a tenant-admin of tenant A must not be able to
    grant tenant-admin to a user belonging to tenant B via the REST endpoint
    (403, not 200) — and no cross-tenant TenantRole row must be created."""
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)

    other_tenant = Tenant.objects.create(name="UMV-OTHER3", slug="umv-other3", is_active=True)
    set_request_tenant(other_tenant.id)
    try:
        foreign_user = User.objects.create(
            username="umv-foreign-target",
            email="umv-foreign-target@t.test",
            tenant=other_tenant,
            is_active=True,
        )
    finally:
        clear_request_tenant()

    resp = client.post(f"/api/v1/users/{foreign_user.id}/tenant-admin/")
    assert resp.status_code == 403, resp.content
    assert resp.json()["error"] == "PERMISSION_DENIED"

    set_request_tenant(tenant.id)
    try:
        assert not TenantRole.objects.filter(
            tenant_id=tenant.id, user_id=foreign_user.id
        ).exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_list_users_succeeds_for_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    resp = client.get("/api/v1/users/")
    assert resp.status_code == 200, resp.content
    usernames = {u["username"] for u in resp.json()}
    assert "umv-True-False" in usernames


@pytest.mark.django_db
def test_list_users_requires_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=False, is_workspace_admin=True)
    resp = client.get("/api/v1/users/")
    assert resp.status_code == 403, resp.content


@pytest.mark.django_db
def test_grant_tenant_admin_returns_404_for_unknown_user(tenant, workspace):
    """Fix round 2 / Fix 2: an unknown target user id on the grant endpoint
    must return a clean 404, not an unhandled 500 (User.DoesNotExist)."""
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    unknown_id = "00000000-0000-0000-0000-000000000000"
    resp = client.post(f"/api/v1/users/{unknown_id}/tenant-admin/")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"] == "NOT_FOUND"


from auth_tenancy.services import AuthorizationService  # noqa: E402 (used above)
