"""
Integration tests for symmetric role resolution on the Bearer-Token path (REQ-126).

Root-cause: AuthTenancyAuthentication used JWT claims as the sole source of roles.
When a user logs in with no assigned roles (claims.roles == []), all write
operations fail with 403 — even after a workspace role is granted, because the old
token still carries empty roles.

Fix: auth_tenancy/rest.py _resolve_roles_from_db() — DB-Fallback when
  * Auth method is API_KEY (claims.roles is always ())
  * Auth method is BEARER_TOKEN and claims.roles is empty (stale JWT / new user)

leaf_id : COMP-AT-001 (AuthTenancyAuthentication role resolution)
req_id  : REQ-126
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_EDITOR, UserRole
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
def user_without_role(db):
    """An active user with NO UserRole at login time (simulates fresh sign-up).

    The login JWT will carry roles=[], making this user unable to write via a
    stale Bearer token BEFORE the REQ-126 fix.
    """
    tenant = Tenant.objects.create(name="Bearer T", slug="bearer-t", is_active=True)
    user = User.objects.create(
        username="freshuser", email="freshuser@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    return user


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_needs_with_bearer_token_after_fresh_login(user_without_role):
    """REQ-126: Bearer token with empty JWT roles uses DB-Fallback → 201 on POST.

    Scenario:
    1. User logs in (no UserRole exists → JWT encodes roles=[]).
    2. Workspace + editor role assigned AFTER login (JWT not re-issued).
    3. Old Bearer token (stale roles=[]) used for write operations.
    4. Expected: 201 (DB-Fallback resolves role from UserRole table).

    Without the fix all three writes return 403 (RBAC: no active role permits WRITE).
    """
    # --- Step 1: Login — JWT minted with empty roles ---
    client = APIClient()
    login_resp = client.post(
        "/api/v1/auth/login/",
        {"username": "freshuser", "password": "hunter2pass"},
        format="json",
    )
    assert login_resp.status_code == 200, login_resp.json()
    login_body = login_resp.json()
    bearer_token = login_body["token"]
    # Precondition: verify JWT carries no roles (proves the scenario is correct).
    assert login_body["roles"] == [], (
        "Precondition failed: expected user to have no roles at login time"
    )

    # --- Step 2: Assign workspace role AFTER token issuance ---
    user = user_without_role
    tenant = user.tenant
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS Bearer", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant,
            user=user,
            workspace=workspace,
            role=ROLE_EDITOR,
        )
    finally:
        clear_request_tenant()

    # --- Step 3: Use the stale Bearer token (roles=[] in JWT) for write ops ---
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {bearer_token}")

    # Needs — workspace-scoped URL; workspace_id injected from path by view.
    need_resp = authed.post(
        f"/api/v1/workspaces/{workspace.id}/needs/",
        {"title": "Bearer Need"},
        format="json",
    )
    assert need_resp.status_code == 201, (
        f"POST /workspaces/.../needs/ returned {need_resp.status_code}: "
        f"{need_resp.json()}"
    )

    # Requirements — workspace_id in request body.
    req_resp = authed.post(
        "/api/v1/requirements/",
        {"title": "Bearer Requirement", "workspace_id": str(workspace.id)},
        format="json",
    )
    assert req_resp.status_code == 201, (
        f"POST /requirements/ returned {req_resp.status_code}: {req_resp.json()}"
    )

    # Architecture elements — workspace_id in request body.
    arch_resp = authed.post(
        "/api/v1/architecture/",
        {"title": "Bearer Arch Element", "workspace_id": str(workspace.id)},
        format="json",
    )
    assert arch_resp.status_code == 201, (
        f"POST /architecture/ returned {arch_resp.status_code}: {arch_resp.json()}"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_bearer_token_with_roles_in_jwt_still_works(db):
    """REQ-126: JWT with non-empty roles is used as-is (fast path, no regression).

    Regression guard: tokens that already carry roles must not be affected by the
    DB-Fallback. The fallback only triggers when claims.roles is empty.
    """
    # Create user WITH a role before login so the JWT embeds the role.
    tenant = Tenant.objects.create(name="Fast T", slug="fast-t", is_active=True)
    user = User.objects.create(
        username="roleuser", email="roleuser@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS Fast", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login_resp = client.post(
        "/api/v1/auth/login/",
        {"username": "roleuser", "password": "hunter2pass"},
        format="json",
    )
    assert login_resp.status_code == 200, login_resp.json()
    login_body = login_resp.json()
    bearer_token = login_body["token"]
    # Verify JWT carries the role (fast path should be used, no DB lookup).
    assert ROLE_EDITOR in login_body["roles"], (
        f"Precondition: expected '{ROLE_EDITOR}' in JWT roles, got {login_body['roles']}"
    )

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {bearer_token}")

    resp = authed.post(
        f"/api/v1/workspaces/{workspace.id}/needs/",
        {"title": "Fast-Path Need"},
        format="json",
    )
    assert resp.status_code == 201, (
        f"Fast-path regression: POST /needs/ returned {resp.status_code}: "
        f"{resp.json()}"
    )
