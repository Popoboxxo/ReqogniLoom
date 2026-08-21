"""
REST tests for Task 8 — workspace member assign/suspend/reactivate.

Covers:
- POST /api/v1/workspaces/<workspace_id>/members/            (assign role)
- POST /api/v1/workspaces/<workspace_id>/members/<uid>/suspend/
- POST /api/v1/workspaces/<workspace_id>/members/<uid>/reactivate/
- Cross-tenant IDOR regression: a caller from tenant A must not be able to
  assign a role into a workspace owned by tenant B, even when they hold
  admin/tenant-admin standing in their own tenant A (mirrors the exact class
  of cross-tenant IDOR fixed in Task 7's review for the analogous endpoints).
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="WSM-T", slug="wsm-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WSM-WS", preset={"name": "extended"})
    finally:
        clear_request_tenant()


@pytest.fixture
def admin_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(username="wsm-admin", email="wsm-admin@t.test", tenant=tenant)
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "wsm-admin", "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed


@pytest.mark.django_db
def test_assign_role_via_rest(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target", email="wsm-target@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/",
        {"user_id": str(target.id), "role": "editor", "preset": "extended"},
        format="json",
    )
    assert resp.status_code == 201, resp.content

    set_request_tenant(tenant.id)
    try:
        assert UserRole.objects.filter(user=target, workspace=workspace, role="editor").exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_suspend_and_reactivate_role_via_rest(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target2", email="wsm-target2@t.test", tenant=tenant)
        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role="editor")
    finally:
        clear_request_tenant()

    suspend = admin_client.post(f"/api/v1/workspaces/{workspace.id}/members/{target.id}/suspend/", {"role": "editor"}, format="json")
    assert suspend.status_code == 200, suspend.content
    set_request_tenant(tenant.id)
    try:
        role = UserRole.objects.get(user=target, workspace=workspace, role="editor")
        assert role.suspended_at is not None
    finally:
        clear_request_tenant()

    reactivate = admin_client.post(f"/api/v1/workspaces/{workspace.id}/members/{target.id}/reactivate/", {"role": "editor"}, format="json")
    assert reactivate.status_code == 200, reactivate.content
    set_request_tenant(tenant.id)
    try:
        role = UserRole.objects.get(user=target, workspace=workspace, role="editor")
        assert role.suspended_at is None
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_suspend_blocks_last_workspace_admin(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        admin_user = User.objects.get(username="wsm-admin")
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/{admin_user.id}/suspend/", {"role": "admin"}, format="json"
    )
    assert resp.status_code == 409, resp.content
    assert resp.json()["error"] == "LAST_ADMIN"


@pytest.mark.django_db
def test_assign_role_rejects_cross_tenant_workspace(admin_client, tenant, workspace):
    """A tenant-A admin/workspace-admin must not be able to assign a role
    into a workspace that belongs to tenant B (cross-tenant IDOR regression,
    mirrors the class of bug fixed in Task 7's review for analogous
    endpoints). ``AuthorizationService.assign_role`` self-enforces that
    ``workspace_id`` belongs to the caller's own ``tenant_id`` and raises
    ``NotFoundError`` otherwise, which the view maps to 404.
    """
    tenant_b = Tenant.objects.create(name="WSM-T-B", slug="wsm-t-b", is_active=True)
    set_request_tenant(tenant_b.id)
    try:
        workspace_b = Workspace.objects.create(tenant=tenant_b, name="WSM-WS-B", preset={"name": "extended"})
        target_b = User.objects.create(username="wsm-target-b", email="wsm-target-b@t.test", tenant=tenant_b)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace_b.id}/members/",
        {"user_id": str(target_b.id), "role": "editor", "preset": "extended"},
        format="json",
    )
    # NotFoundError from AuthorizationService.assign_role maps to 404; a 403
    # would also be an acceptable deny, but the real, demonstrated behaviour
    # of this exact code path is 404 (workspace not found under the caller's
    # tenant) — assert that explicitly rather than accepting either.
    assert resp.status_code == 404, resp.content

    set_request_tenant(tenant_b.id)
    try:
        assert not UserRole.objects.filter(user=target_b, workspace=workspace_b, role="editor").exists()
    finally:
        clear_request_tenant()
