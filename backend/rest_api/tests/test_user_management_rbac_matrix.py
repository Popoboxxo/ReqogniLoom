# backend/rest_api/tests/test_user_management_rbac_matrix.py
"""Same permission matrix as mcp_server/tests/test_user_management_rbac_matrix.py,
driven through the REST surface instead — proves REST and MCP agree,
both against the one shared constant in auth_tenancy/tests/
user_management_matrix.py."""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_APPROVER, ROLE_EDITOR, ROLE_VIEWER, TenantRole, UserRole
from auth_tenancy.tests.user_management_matrix import ACTIONS, USER_MANAGEMENT_MATRIX
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


def _setup_and_login(role_label: str):
    """Create a tenant/workspace/caller (with role_label's role) + a
    separate target user, then log the caller in via the REST auth
    endpoint. Mirrors mcp_server/tests/test_user_management_rbac_matrix.py's
    ``_setup_caller_and_target`` (target is always a different user from
    the caller, and the assign_role matrix scenario below uses
    role="viewer", so the SEC-05 first-admin-bootstrap exception never
    accidentally fires for the "no-role" case)."""
    slug = f"umr-{role_label}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=slug, slug=slug, is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS", preset={"name": "extended"})
        caller = User.objects.create(username=f"caller-{slug}", email=f"caller-{slug}@t.test", tenant=tenant)
        caller.set_password("hunter2pass")
        caller.save(update_fields=["password"])
        target = User.objects.create(username=f"target-{slug}", email=f"target-{slug}@t.test", tenant=tenant)

        if role_label == "tenant-admin":
            TenantRole.objects.create(tenant=tenant, user=caller, role=TenantRole.ROLE_ADMIN)
        elif role_label == "workspace-admin":
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=ROLE_ADMIN)
        elif role_label in ("editor", "viewer", "approver"):
            role_map = {"editor": ROLE_EDITOR, "viewer": ROLE_VIEWER, "approver": ROLE_APPROVER}
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=role_map[role_label])
        # "no-role": no assignment at all

        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role=ROLE_EDITOR)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": caller.username, "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return {"client": authed, "tenant": tenant, "workspace": workspace, "target": target}


_ACTION_TO_REQUEST = {
    "user.create": lambda ids: ("post", "/api/v1/users/", {"username": f"u-{uuid.uuid4().hex[:8]}", "email": f"{uuid.uuid4().hex[:8]}@t.test", "password": "a-real-password-123"}),
    "user.activate": lambda ids: ("post", f"/api/v1/users/{ids['target'].id}/activate/", {}),
    "user.deactivate": lambda ids: ("post", f"/api/v1/users/{ids['target'].id}/deactivate/", {}),
    "workspace.assign_role": lambda ids: ("post", f"/api/v1/workspaces/{ids['workspace'].id}/members/", {"user_id": str(ids["target"].id), "role": "viewer", "preset": "extended"}),
    "workspace.suspend_role": lambda ids: ("post", f"/api/v1/workspaces/{ids['workspace'].id}/members/{ids['target'].id}/suspend/", {"role": "editor"}),
    "workspace.reactivate_role": lambda ids: ("post", f"/api/v1/workspaces/{ids['workspace'].id}/members/{ids['target'].id}/reactivate/", {"role": "editor"}),
    "tenant.assign_admin": lambda ids: ("post", f"/api/v1/users/{ids['target'].id}/tenant-admin/", {}),
    "tenant.revoke_admin": lambda ids: ("delete", f"/api/v1/users/{ids['target'].id}/tenant-admin/", {}),
}


@pytest.mark.django_db
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("role_label", ["tenant-admin", "workspace-admin", "editor", "viewer", "approver", "no-role"])
def test_rest_permission_matches_matrix(action, role_label):
    expected_allowed = USER_MANAGEMENT_MATRIX[action][role_label]
    ids = _setup_and_login(role_label)
    method, path, body = _ACTION_TO_REQUEST[action](ids)

    client_call = getattr(ids["client"], method)
    resp = client_call(path, body, format="json")

    if expected_allowed:
        assert resp.status_code != 403, f"{role_label} should be ALLOWED for {path} but got 403: {resp.content}"
    else:
        assert resp.status_code == 403, f"{role_label} should be DENIED for {path} but got {resp.status_code}: {resp.content}"
