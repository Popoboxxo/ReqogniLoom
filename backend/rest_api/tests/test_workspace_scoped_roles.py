"""Workspace-scoped role resolution for the REST adapter (GitHub #103).

Security-critical regression coverage for a HIGH-severity cross-workspace
privilege escalation.

Vulnerability
-------------
``UserRole`` is modelled per workspace (the ``workspace`` FK is NOT NULL, so a
tenant-wide role does not exist in the data model). Role resolution on the REST
path, however, aggregated every non-suspended assignment of a user across the
*whole tenant*:

* ``PasswordAuthenticationService.resolve_roles`` — baked the tenant-wide union
  into the ``roles`` claim of the issued JWT.
* ``auth_tenancy.rest._resolve_roles_from_db`` — same union for API keys and
  role-less (stale) JWTs.

``RbacPermission`` and every ``ctx.has_role("admin")`` gate then evaluated that
union, so an admin/editor in workspace A was effectively admin/editor in *every*
workspace of the tenant.

Expected behaviour
------------------
When a request targets an identifiable workspace, the caller's effective roles
must be exactly their non-suspended roles **in that workspace** — never a union
across workspaces. Holding no role in the target workspace means no access.

Legitimate multi-workspace membership (an explicit ``UserRole`` row per
workspace) must keep working; that is the only supported way to be admin in
more than one workspace.

leaf_id : COMP-RA-003 (RbacPermission) + COMP-AT-001 (role resolution)
req_id  : GitHub #103
"""
from __future__ import annotations

import time
import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "workspace-scope-test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)
_PASSWORD = "hunter2pass"

_AUTH_METHODS = ("session", "jwt", "api_key")


def _tenant_with_two_workspaces() -> tuple[Tenant, User, Workspace, Workspace]:
    """Create one tenant, one user and two workspaces (A and B), no roles yet."""
    slug = f"wsscope-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace_a = Workspace.objects.create(
            tenant=tenant, name=f"WS-A-{slug}", preset={"name": "extended"}
        )
        workspace_b = Workspace.objects.create(
            tenant=tenant, name=f"WS-B-{slug}", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace_a, workspace_b


def _grant(tenant: Tenant, user: User, workspace: Workspace, role: str) -> None:
    """Create a non-suspended role assignment for ``user`` in ``workspace``."""
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()


def _mint_bearer(user: User, tenant: Tenant, roles: list[str]) -> str:
    """Mint a valid JWT carrying ``roles`` as its (tenant-wide) roles claim."""
    now = int(time.time())
    return encode_hs256(
        {
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "roles": roles,
            "iss": "reqflow",
            "aud": "reqflow-api",
            "iat": now,
            "exp": now + 3600,
        },
        secret=_SECRET,
    )


def _authed_client(
    method: str, user: User, tenant: Tenant, *, jwt_roles: list[str] | None = None
) -> APIClient:
    """Return an APIClient authenticated for ``user`` via ``method``."""
    client = APIClient()

    if method == "session":
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": user.username, "password": _PASSWORD},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert ACCESS_COOKIE_NAME in client.cookies
        return client

    if method == "jwt":
        # Worst case for the escalation: the claim already carries the elevated
        # role. A workspace-scoped decision must not trust it.
        token = _mint_bearer(user, tenant, jwt_roles or [ROLE_ADMIN])
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    if method == "api_key":
        result = AuthenticationService().create_api_key(
            user_id=user.id, tenant_id=tenant.id, name="wsscope-key"
        )
        client.credentials(HTTP_X_API_KEY=result.plaintext)
        return client

    raise ValueError(f"unknown auth method: {method}")


# ---------------------------------------------------------------------------
# The vulnerability: role in workspace A must not grant access to workspace B
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_admin_in_workspace_a_cannot_write_in_workspace_b(auth_method: str) -> None:
    """An admin in A holds no role in B and must be denied writes there (#103)."""
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    client = _authed_client(auth_method, user, tenant)

    resp = client.post(
        f"/api/v1/workspaces/{ws_b.id}/needs/",
        {"title": "escalated-need"},
        format="json",
    )

    assert resp.status_code == 403, (
        f"[{auth_method}] cross-workspace write must be denied (403) but got "
        f"{resp.status_code}: {resp.content!r} — roles leaked from workspace A "
        "into workspace B (#103)."
    )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_admin_in_workspace_a_cannot_read_in_workspace_b(auth_method: str) -> None:
    """Not being a member of B must deny reads there too (#103)."""
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    client = _authed_client(auth_method, user, tenant)

    resp = client.get(f"/api/v1/workspaces/{ws_b.id}/needs/")

    assert resp.status_code == 403, (
        f"[{auth_method}] cross-workspace read must be denied (403) but got "
        f"{resp.status_code}: {resp.content!r} (#103)."
    )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_viewer_in_target_workspace_is_not_elevated_by_admin_elsewhere(
    auth_method: str,
) -> None:
    """Sharpest case: viewer in A + admin in B must still be read-only in A.

    Under the tenant-wide union the caller was ``{admin, viewer}`` everywhere,
    so the write in A was allowed. Scoped resolution yields ``{viewer}`` in A.
    """
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_VIEWER)
    _grant(tenant, user, ws_b, ROLE_ADMIN)
    client = _authed_client(auth_method, user, tenant)

    read = client.get(f"/api/v1/workspaces/{ws_a.id}/needs/")
    assert read.status_code == 200, (
        f"[{auth_method}] viewer must keep READ in workspace A: "
        f"{read.status_code}: {read.content!r}"
    )

    write = client.post(
        f"/api/v1/workspaces/{ws_a.id}/needs/",
        {"title": "viewer-should-not-write"},
        format="json",
    )
    assert write.status_code == 403, (
        f"[{auth_method}] viewer in workspace A must not be elevated by the "
        f"admin role held in workspace B, got {write.status_code}: "
        f"{write.content!r} (#103)."
    )


# ---------------------------------------------------------------------------
# Regression guards: legitimate access must keep working
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_role_in_target_workspace_still_grants_access(auth_method: str) -> None:
    """The normal case must be unaffected: editor in A may write in A."""
    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    client = _authed_client(auth_method, user, tenant, jwt_roles=[ROLE_EDITOR])

    read = client.get(f"/api/v1/workspaces/{ws_a.id}/needs/")
    assert read.status_code == 200, f"{read.status_code}: {read.content!r}"

    write = client.post(
        f"/api/v1/workspaces/{ws_a.id}/needs/",
        {"title": "legitimate-need"},
        format="json",
    )
    assert write.status_code == 201, f"{write.status_code}: {write.content!r}"


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_explicit_multi_workspace_admin_keeps_access_everywhere(
    auth_method: str,
) -> None:
    """Legitimate cross-workspace admin: one UserRole row per workspace.

    This is the supported way to hold rights in several workspaces and must not
    be broken by the scoping fix.
    """
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    _grant(tenant, user, ws_b, ROLE_ADMIN)
    client = _authed_client(auth_method, user, tenant)

    for workspace in (ws_a, ws_b):
        resp = client.post(
            f"/api/v1/workspaces/{workspace.id}/needs/",
            {"title": f"multi-ws-{workspace.id}"},
            format="json",
        )
        assert resp.status_code == 201, (
            f"[{auth_method}] explicit admin in {workspace.name} must be allowed, "
            f"got {resp.status_code}: {resp.content!r}"
        )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_suspended_role_in_target_workspace_denies_access(auth_method: str) -> None:
    """A suspended assignment in the target workspace grants nothing."""
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    set_request_tenant(tenant.id)
    try:
        from django.utils import timezone

        UserRole.objects.create(
            tenant=tenant,
            user=user,
            workspace=ws_b,
            role=ROLE_ADMIN,
            suspended_at=timezone.now(),
        )
    finally:
        clear_request_tenant()

    client = _authed_client(auth_method, user, tenant)
    resp = client.post(
        f"/api/v1/workspaces/{ws_b.id}/needs/",
        {"title": "suspended-should-not-write"},
        format="json",
    )
    assert resp.status_code == 403, (
        f"[{auth_method}] suspended role must not grant write, got "
        f"{resp.status_code}: {resp.content!r}"
    )
