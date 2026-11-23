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

The same role x auth-method matrix is applied to the credential/governance
endpoints (#1731 evidence). Those endpoints deliberately do NOT all follow the
workspace write rule:

    /api/v1/api-keys/            -- self-service (#716/#723): every role may
        GET its OWN keys, POST a read-scoped key and DELETE its own key; a
        foreign pk answers 404 (not 403). A write-scoped key is bounded by the
        creator's own effective rights (#1608): viewer -> 403, others -> 201.
    /api/v1/users/               -- tenant-admin gate (TenantRole), NOT the
        workspace RBAC matrix: tenant-admin -> 200/201, every workspace role
        (including workspace-admin) -> 403.
    /api/v1/permission-defaults/ -- global admin gate (ctx.has_role(admin)):
        admin -> 200, viewer/editor/approver -> 403. An explicit viewer-403
        assertion pins this boundary.

These are regression guards only — the intentional viewer self-service on
/api/v1/api-keys/ is preserved, never tightened to a blanket 403.

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
issues  : #716 / #723 (Viewer self-service: create/read/revoke OWN keys),
          #865 (API-key capability tier on key-management mutations),
          #1608 (write-tier key bounded by the creator's effective rights),
          #1731 (credential listing is self-scoped — verified working as
          intended; this module pins that boundary, it does not change it)
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
    TenantRole,
    UserRole,
)
from auth_tenancy.rest import ACCESS_COOKIE_NAME
from auth_tenancy.services.authentication import AuthenticationService
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


# ---------------------------------------------------------------------------
# Credential / governance endpoints (#1731 evidence — test-only extension)
# ---------------------------------------------------------------------------
#
# The workspace-need matrix above drives the three auth methods through ONE
# role pipeline. The identity that an endpoint trusts decides its outcome:
#   * /api-keys/            -> the caller's own keys (self-service, #716/#723)
#   * /users/               -> TenantRole admin (AuthorizationService)
#   * /permission-defaults/ -> ctx.has_role(ROLE_ADMIN) over the same roles the
#                              needs matrix resolves.
# These tests pin each boundary without changing any behaviour.


def _setup_tenant_admin() -> tuple[User, Tenant]:
    """Create an active user holding the tenant-wide admin ``TenantRole``.

    Tenant-admin authority is deliberately independent of workspace
    ``UserRole`` rows (``AuthorizationService.is_tenant_admin`` reads
    ``TenantRole``), so this user holds NO workspace role. A workspace-only
    admin (``_setup_user_with_role(ROLE_ADMIN)``) must still get 403 on
    ``/api/v1/users/`` — that distinction is exactly what these tests pin.
    """
    slug = f"matrix-ta-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        TenantRole.objects.create(
            tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return user, tenant


def _second_workspace_member(tenant: Tenant, workspace: Workspace, role: str) -> User:
    """Create a second role holder in the SAME tenant/workspace as another user."""
    suffix = uuid.uuid4().hex[:8]
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=f"matrix-{role}-{suffix}",
            email=f"{role}-{suffix}@t.test",
            tenant=tenant,
        )
        user.set_password(_PASSWORD)
        user.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=role)
    finally:
        clear_request_tenant()
    return user


def _plain_user(tenant: Tenant, name: str, *, is_active: bool = True) -> User:
    """Create a role-less user in ``tenant`` as an activate/deactivate/grant target."""
    set_request_tenant(tenant.id)
    try:
        return User.objects.create(
            username=name, email=f"{name}@t.test", tenant=tenant, is_active=is_active
        )
    finally:
        clear_request_tenant()


def _tenant_admin_user(tenant: Tenant, name: str) -> User:
    """Create a second tenant-admin in ``tenant`` as a revoke target."""
    user = _plain_user(tenant, name)
    set_request_tenant(tenant.id)
    try:
        TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    finally:
        clear_request_tenant()
    return user


# --- /api/v1/api-keys/ ------------------------------------------------------

_API_KEYS = "/api/v1/api-keys/"


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
@pytest.mark.parametrize("role", list(_WRITE_ALLOWED))
def test_api_key_self_service_lifecycle_across_auth_methods(
    role: str, auth_method: str
) -> None:
    """GET list + GET retrieve + POST(read) + DELETE all work for every role.

    The #716/#723 self-service rule stays: no blanket viewer-403 here. The
    api_key credential minted by ``_authed_client`` is write-scoped (tier 2),
    so it clears the key-management capability gate (#865); the newly created
    key is read-scoped, so #1608's creator-rights bound passes for every role.
    """
    user, tenant, _workspace = _setup_user_with_role(role)
    client = _authed_client(auth_method, user, tenant)

    listed = client.get(_API_KEYS)
    assert listed.status_code == 200, (
        f"[{role}/{auth_method}] list own keys: {listed.content!r}"
    )

    created = client.post(
        _API_KEYS,
        {"name": f"{role}-{auth_method}-key", "scope": "read"},
        format="json",
    )
    assert created.status_code == 201, (
        f"[{role}/{auth_method}] create read-scoped key: {created.content!r}"
    )
    key_id = created.json()["id"]

    retrieved = client.get(f"{_API_KEYS}{key_id}/")
    assert retrieved.status_code == 200, (
        f"[{role}/{auth_method}] retrieve own key: {retrieved.content!r}"
    )
    assert retrieved.json()["id"] == key_id

    revoked = client.delete(f"{_API_KEYS}{key_id}/")
    assert revoked.status_code == 204, (
        f"[{role}/{auth_method}] revoke own key: {revoked.content!r}"
    )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_api_key_foreign_pk_answers_404_not_403(auth_method: str) -> None:
    """A viewer never sees another user's key — not via detail, not via list.

    The #1731 "credential landscape" suspicion is refuted here: the lookup is
    scoped to the caller's own keys, so a foreign id answers 404 (it must not
    even confirm existence) while an empty listing still answers 200.
    """
    owner, tenant, workspace = _setup_user_with_role(ROLE_VIEWER)
    intruder = _second_workspace_member(tenant, workspace, ROLE_VIEWER)
    owner_client = _authed_client(auth_method, owner, tenant)
    intruder_client = _authed_client(auth_method, intruder, tenant)

    created = owner_client.post(
        _API_KEYS, {"name": "private-key", "scope": "read"}, format="json"
    )
    assert created.status_code == 201, created.content
    key_id = created.json()["id"]

    detail = intruder_client.get(f"{_API_KEYS}{key_id}/")
    assert detail.status_code == 404, (
        f"[{auth_method}] foreign key detail must be 404, got "
        f"{detail.status_code}: {detail.content!r}"
    )

    listing = intruder_client.get(_API_KEYS)
    assert listing.status_code == 200, listing.content
    assert key_id not in {k["id"] for k in listing.json()["results"]}


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
@pytest.mark.parametrize("role", list(_WRITE_ALLOWED))
def test_api_key_create_scope_gate_matches_across_auth_methods(
    role: str, auth_method: str
) -> None:
    """A write-tier key is bounded by its creator's own rights (#1608).

    viewer -> 403 PERMISSION_DENIED even though the endpoint is self-service;
    admin/editor/approver -> 201. ``scope=read`` stays open to every role.
    The verdict is identical for session, JWT and API-key credentials.
    """
    user, tenant, _workspace = _setup_user_with_role(role)
    client = _authed_client(auth_method, user, tenant)

    write = client.post(
        _API_KEYS,
        {"name": f"{role}-{auth_method}-write", "scope": "write"},
        format="json",
    )
    if _WRITE_ALLOWED[role]:
        assert write.status_code == 201, (
            f"[{role}/{auth_method}] write-scoped key should be allowed: "
            f"{write.content!r}"
        )
    else:
        assert write.status_code == 403, (
            f"[{role}/{auth_method}] viewer must not mint a write-scoped key: "
            f"{write.status_code}: {write.content!r}"
        )
        assert write.json()["error"]["code"] == "PERMISSION_DENIED"


# --- /api/v1/users/ ---------------------------------------------------------

_USERS = "/api/v1/users/"


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_users_endpoints_allow_tenant_admin_across_auth_methods(
    auth_method: str,
) -> None:
    """Every user-management operation succeeds for a TenantRole admin.

    list 200, create 201, activate/deactivate 200, grant/revoke 200. A
    tenant-admin needs no workspace role at all — that is the whole point of
    the TenantRole-based gate on this ViewSet.
    """
    admin_user, tenant = _setup_tenant_admin()
    client = _authed_client(auth_method, admin_user, tenant)
    suffix = uuid.uuid4().hex[:8]

    assert client.get(_USERS).status_code == 200

    created = client.post(
        _USERS,
        {
            "username": f"newbie-{suffix}",
            "email": f"newbie-{suffix}@t.test",
            "password": "a-real-password-123",
        },
        format="json",
    )
    assert created.status_code == 201, created.content

    inactive = _plain_user(tenant, f"inactive-{suffix}", is_active=False)
    assert client.post(f"{_USERS}{inactive.id}/activate/").status_code == 200

    active = _plain_user(tenant, f"active-{suffix}")
    assert client.post(f"{_USERS}{active.id}/deactivate/").status_code == 200

    grant_target = _plain_user(tenant, f"grant-{suffix}")
    assert client.post(f"{_USERS}{grant_target.id}/tenant-admin/").status_code == 200

    revoke_target = _tenant_admin_user(tenant, f"revoke-{suffix}")
    assert client.delete(f"{_USERS}{revoke_target.id}/tenant-admin/").status_code == 200


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
@pytest.mark.parametrize(
    "role", [ROLE_VIEWER, ROLE_ADMIN, ROLE_APPROVER, ROLE_EDITOR]
)
def test_users_endpoints_deny_workspace_roles_across_auth_methods(
    role: str, auth_method: str
) -> None:
    """No workspace role — including workspace-admin — grants /users/ access.

    Every workspace role is denied (viewer, editor, approver and admin), and
    ``ROLE_ADMIN`` here is a workspace ``UserRole`` admin, NOT a ``TenantRole``
    admin (that case is tested separately above). Every operation is a 403,
    identically for session, JWT and API-key credentials.
    """
    user, tenant, _workspace = _setup_user_with_role(role)
    client = _authed_client(auth_method, user, tenant)
    suffix = uuid.uuid4().hex[:8]
    target = _plain_user(tenant, f"target-{suffix}")

    assert client.get(_USERS).status_code == 403
    assert client.post(
        _USERS,
        {
            "username": f"denied-{suffix}",
            "email": f"denied-{suffix}@t.test",
            "password": "a-real-password-123",
        },
        format="json",
    ).status_code == 403
    assert client.post(f"{_USERS}{target.id}/activate/").status_code == 403
    assert client.post(f"{_USERS}{target.id}/deactivate/").status_code == 403
    assert client.post(f"{_USERS}{target.id}/tenant-admin/").status_code == 403
    assert client.delete(f"{_USERS}{target.id}/tenant-admin/").status_code == 403


# --- /api/v1/permission-defaults/ -------------------------------------------

_PERM_DEFAULTS = "/api/v1/permission-defaults/"
_ENFORCEMENT = f"{_PERM_DEFAULTS}enforcement/"
_FLIP = f"{_PERM_DEFAULTS}enforcement/flip/"


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
def test_permission_defaults_allow_admin_across_auth_methods(
    auth_method: str,
) -> None:
    """GET/PUT/PATCH, enforcement GET and the guarded flip work for an admin.

    Admin authority comes from the workspace ``UserRole`` resolved into
    ``ctx.active_roles`` by the same DB fallback the needs matrix exercises —
    including the empty-JWT-claim and API-key identities.
    """
    user, tenant, _workspace = _setup_user_with_role(ROLE_ADMIN)
    client = _authed_client(auth_method, user, tenant)

    current = client.get(_PERM_DEFAULTS)
    assert current.status_code == 200, current.content
    matrix = current.json()["permission_json"]

    replaced = client.put(_PERM_DEFAULTS, {"permission_json": matrix}, format="json")
    assert replaced.status_code == 200, replaced.content

    patched = client.patch(
        _PERM_DEFAULTS,
        {"permission_json": {"viewer": {"write": True}}},
        format="json",
    )
    assert patched.status_code == 200, patched.content

    assert client.get(_ENFORCEMENT).status_code == 200

    flipped = client.post(_FLIP, {"enforcement_mode": "shadow"}, format="json")
    assert flipped.status_code == 200, flipped.content


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("auth_method", _AUTH_METHODS)
@pytest.mark.parametrize("role", [ROLE_VIEWER, ROLE_APPROVER, ROLE_EDITOR])
def test_permission_defaults_deny_non_admin_roles_across_auth_methods(
    auth_method: str, role: str
) -> None:
    """Every permission-defaults operation is a 403 for every non-admin role.

    Viewer, editor and approver all hold READ (and the latter two also hold
    WRITE in the workspace matrix), yet none holds the global
    ``ctx.has_role(ROLE_ADMIN)`` this surface requires. Verdict is identical
    for session, JWT and API-key credentials.
    """
    user, tenant, _workspace = _setup_user_with_role(role)
    client = _authed_client(auth_method, user, tenant)

    assert client.get(_PERM_DEFAULTS).status_code == 403
    assert client.put(
        _PERM_DEFAULTS, {"permission_json": {"admin": {}}}, format="json"
    ).status_code == 403
    assert client.patch(
        _PERM_DEFAULTS,
        {"permission_json": {"viewer": {"write": True}}},
        format="json",
    ).status_code == 403
    assert client.get(_ENFORCEMENT).status_code == 403
    assert client.post(_FLIP, {"enforcement_mode": "shadow"}, format="json").status_code == 403


@pytest.mark.django_db
def test_viewer_is_denied_on_permission_defaults() -> None:
    """Explicit viewer-403 guard for /permission-defaults/ (session baseline).

    Kept as a standalone, plainly named assertion so this governance boundary
    cannot be lost inside the parametrised matrix. The admin counterpart above
    proves the same routes answer 200 for an admin.
    """
    user, tenant, _workspace = _setup_user_with_role(ROLE_VIEWER)
    client = _authed_client("session", user, tenant)

    assert client.get("/api/v1/permission-defaults/").status_code == 403
