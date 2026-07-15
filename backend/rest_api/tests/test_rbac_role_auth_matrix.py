"""
RBAC role x auth-method matrix for the REST adapter (REQ-126, REQ-127).

Security-critical regression coverage. It asserts that RBAC is enforced
*identically* regardless of how the caller authenticated, i.e. that JWT Bearer
tokens and MCP-style API keys resolve the caller's roles through the SAME
pipeline as a browser session — the single source of truth being the
``UserRole`` table via ``auth_tenancy``'s role resolution.

Matrix (one read endpoint + one write endpoint per cell):
    roles  : admin, editor, viewer, approver
    auth   : session (httpOnly access cookie), jwt (Authorization: Bearer),
             api_key (X-API-Key)
    read   : GET  /api/v1/workspaces/<ws>/needs/     -> allowed for every role
    write  : POST /api/v1/workspaces/<ws>/needs/     -> allowed for admin /
             editor / approver, DENIED (403) for viewer

Why this reproduces the findings:
    * REQ-126 (Bearer): the JWT is minted with an EMPTY ``roles`` claim, so the
      request can only be authorised if role resolution falls back to the DB
      (``auth_tenancy/rest.py::_resolve_roles_from_db``). Before the fix every
      write returned 403 because ``claims.roles`` was the sole source.
    * REQ-127 (API key): API-key claims always carry ``roles=()``; the caller
      must still have its ``UserRole`` roles loaded. Before the fix write ops
      failed with 403 for every API-key identity.

Both must behave exactly like the session (cookie) baseline.

CSRF is deliberately out of scope here: the default DRF ``APIClient`` disables
CSRF enforcement so these cases isolate the RBAC decision. CSRF on the cookie
path is covered by ``test_auth_cookie.py`` / ``test_csrf_regression.py``.

leaf_id : COMP-RA-003 (RbacPermission) + COMP-AT-001 (role resolution)
req_id  : REQ-126, REQ-127
"""
from __future__ import annotations

import time
import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.rest import ACCESS_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "matrix-test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)
_PASSWORD = "hunter2pass"

# Each role and whether it may perform WRITE operations per the RBAC matrix.
# Every role may READ.
_WRITE_ALLOWED = {
    ROLE_ADMIN: True,
    ROLE_EDITOR: True,
    ROLE_APPROVER: True,
    ROLE_VIEWER: False,
}
_AUTH_METHODS = ("session", "jwt", "api_key")


def _setup_user_with_role(role: str) -> tuple[User, Tenant, Workspace]:
    """Create an active user holding exactly ``role`` in an Extended workspace."""
    slug = f"matrix-{role}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{role}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"WS-{role}", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()
    return user, tenant, workspace


def _mint_bearer_with_empty_roles(user: User, tenant: Tenant) -> str:
    """Mint a valid JWT whose ``roles`` claim is empty (REQ-126 scenario).

    Authorising a write with this token is only possible if role resolution
    falls back to the ``UserRole`` table.
    """
    now = int(time.time())
    return encode_hs256(
        {
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "roles": [],  # empty on purpose -> forces DB fallback (REQ-126)
            "iss": "reqflow",
            "aud": "reqflow-api",
            "iat": now,
            "exp": now + 3600,
        },
        secret=_SECRET,
    )


def _authed_client(method: str, user: User, tenant: Tenant) -> APIClient:
    """Return an APIClient authenticated via ``method`` for ``user``."""
    client = APIClient()

    if method == "session":
        # Browser-session baseline: log in so the httpOnly access cookie is set
        # and persisted by the client's cookie jar for subsequent requests.
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": user.username, "password": _PASSWORD},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert ACCESS_COOKIE_NAME in client.cookies, "login must set access cookie"
        return client

    if method == "jwt":
        token = _mint_bearer_with_empty_roles(user, tenant)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    if method == "api_key":
        result = AuthenticationService().create_api_key(
            user_id=user.id, tenant_id=tenant.id, name="matrix-key"
        )
        client.credentials(HTTP_X_API_KEY=result.plaintext)
        return client

    raise ValueError(f"unknown auth method: {method}")


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
@pytest.mark.parametrize("role", list(_WRITE_ALLOWED))
def test_read_endpoint_allowed_for_all_roles_and_auth_methods(
    role: str, auth_method: str
) -> None:
    """READ (GET) must succeed for every role via every auth method.

    A 403 here would mean role resolution failed for that auth method, since
    every role is granted READ by the RBAC matrix.
    """
    user, tenant, workspace = _setup_user_with_role(role)
    client = _authed_client(auth_method, user, tenant)

    resp = client.get(f"/api/v1/workspaces/{workspace.id}/needs/")
    assert resp.status_code == 200, (
        f"[{role}/{auth_method}] read denied ({resp.status_code}): {resp.content!r}"
    )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
@pytest.mark.parametrize("role", list(_WRITE_ALLOWED))
def test_write_endpoint_rbac_matches_across_auth_methods(
    role: str, auth_method: str
) -> None:
    """WRITE (POST) allow/deny must be identical across auth methods.

    admin/editor/approver -> 201 (role resolved from the DB even when the JWT
    carries no roles or the credential is an API key). viewer -> 403.
    """
    user, tenant, workspace = _setup_user_with_role(role)
    client = _authed_client(auth_method, user, tenant)

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/needs/",
        {"title": f"{role}-{auth_method}-need"},
        format="json",
    )

    if _WRITE_ALLOWED[role]:
        assert resp.status_code == 201, (
            f"[{role}/{auth_method}] write should be allowed but got "
            f"{resp.status_code}: {resp.content!r}. Role resolution likely "
            "failed for this auth method (REQ-126/REQ-127 regression)."
        )
    else:
        assert resp.status_code == 403, (
            f"[{role}/{auth_method}] viewer write must be denied (403) but got "
            f"{resp.status_code}: {resp.content!r}"
        )
