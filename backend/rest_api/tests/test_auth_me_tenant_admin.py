# backend/rest_api/tests/test_auth_me_tenant_admin.py
"""
Multi-user management — `is_tenant_admin` on the identity payload (Task 12
unplanned extension).

`/api/v1/auth/login/` and `/api/v1/auth/me/` expose `is_tenant_admin`
alongside the existing `roles` field so the SPA can gate the
tenant-admin-only User Management surface (frontend/src/components/Settings/
UserManagement/UserManagement.tsx) without inventing a new client-side RBAC
concept. Backed by `AuthorizationService.is_tenant_admin` — the same call
`UserViewSet` (Task 7) already uses to gate every user-management endpoint,
so this is a read-only projection of an already-enforced permission, not a
new authorization decision.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_VIEWER, TenantRole, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="MEV-T", slug="mev-t", is_active=True)


def _make_user(tenant: Tenant, *, username: str, is_tenant_admin: bool) -> User:
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(username=username, email=f"{username}@t.test", tenant=tenant)
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        if is_tenant_admin:
            TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
        # `/auth/me/` still goes through the normal RBAC "read" check
        # (mirrors `test_auth_cookie.py`'s `admin_user` fixture) — tenant-
        # admin status is workspace-independent, but the endpoint itself is
        # not exempt from needing at least one active workspace role.
        workspace = Workspace.objects.create(tenant=tenant, name=f"{username}-ws", preset={"name": "extended"})
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER)
        return user
    finally:
        clear_request_tenant()


def _login(username: str) -> "dict":
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/", {"username": username, "password": "hunter2pass"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    return resp.json()


@pytest.mark.django_db
def test_login_reports_is_tenant_admin_true_for_tenant_admin(tenant):
    _make_user(tenant, username="mev-admin", is_tenant_admin=True)
    body = _login("mev-admin")
    assert body["is_tenant_admin"] is True


@pytest.mark.django_db
def test_login_reports_is_tenant_admin_false_for_plain_user(tenant):
    _make_user(tenant, username="mev-plain", is_tenant_admin=False)
    body = _login("mev-plain")
    assert body["is_tenant_admin"] is False


@pytest.mark.django_db
def test_me_reports_is_tenant_admin_true_for_tenant_admin(tenant):
    _make_user(tenant, username="mev-admin2", is_tenant_admin=True)
    token = _login("mev-admin2")["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = authed.get("/api/v1/auth/me/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_tenant_admin"] is True


@pytest.mark.django_db
def test_me_reports_is_tenant_admin_false_for_plain_user(tenant):
    _make_user(tenant, username="mev-plain2", is_tenant_admin=False)
    token = _login("mev-plain2")["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = authed.get("/api/v1/auth/me/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_tenant_admin"] is False
