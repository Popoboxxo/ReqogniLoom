"""E1.1 — fenced workspace visibility (Plan E, 2026-10-21).

Pins :func:`auth_tenancy.resource_scope.fenced_visible_workspace_ids` and
:func:`~auth_tenancy.resource_scope.fenced_collection_roles`:

* the visible set is the intersection of the key's fence, the caller's tenant
  and the workspaces where the key **owner** holds a non-suspended role;
* a tenant-admin owner keeps the documented elevation (role condition drops);
* a foreign-tenant UUID inside the fence is never returned;
* a suspended role does not count;
* the helper is fenced-key only (assertion for an unfenced context);
* an unfenced Bearer request is unchanged and issues no extra query.

Issue #1444 / Plan E E1.1.
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    TenantRole,
    UserRole,
)
from auth_tenancy.resource_scope import (
    fenced_collection_roles,
    fenced_visible_workspace_ids,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "e1-1-fenced-visible-test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)
_PASSWORD = "hunter2pass"


def _tenant() -> tuple[Tenant, User]:
    slug = f"e11-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return tenant, user


def _workspace(tenant: Tenant, name: str = "WS") -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=f"{name}-{uuid.uuid4().hex[:6]}", preset={}
        )
    finally:
        clear_request_tenant()


def _grant(tenant: Tenant, user: User, workspace: Workspace, role: str) -> UserRole:
    set_request_tenant(tenant.id)
    try:
        return UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()


def _grant_tenant_admin(tenant: Tenant, user: User) -> None:
    set_request_tenant(tenant.id)
    try:
        TenantRole.objects.create(
            tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN
        )
    finally:
        clear_request_tenant()


def _fenced_ctx(
    tenant: Tenant, user: User, fence: tuple[Workspace, ...] | list[str]
) -> AuthContext:
    ids = tuple(
        str(item.id) if isinstance(item, Workspace) else str(item) for item in fence
    )
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_workspace_ids=ids,
    )


# ---------------------------------------------------------------------------
# (a) role in A + B, fence [A, C] -> (A,)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_workspaces_are_fence_intersected_with_owner_roles() -> None:
    tenant, user = _tenant()
    ws_a, ws_b, ws_c = (
        _workspace(tenant, "A"),
        _workspace(tenant, "B"),
        _workspace(tenant, "C"),
    )
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    _grant(tenant, user, ws_b, ROLE_EDITOR)

    ctx = _fenced_ctx(tenant, user, [ws_a, ws_c])

    set_request_tenant(tenant.id)
    try:
        assert fenced_visible_workspace_ids(ctx) == (ws_a.id,)
        assert fenced_collection_roles(ctx) == (ROLE_EDITOR,)
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# (b) tenant-admin owner -> (A, C)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tenant_admin_owner_sees_every_in_tenant_fence_workspace() -> None:
    tenant, user = _tenant()
    ws_a, ws_b, ws_c = (
        _workspace(tenant, "A"),
        _workspace(tenant, "B"),
        _workspace(tenant, "C"),
    )
    _grant_tenant_admin(tenant, user)

    ctx = _fenced_ctx(tenant, user, [ws_a, ws_c])

    set_request_tenant(tenant.id)
    try:
        assert fenced_visible_workspace_ids(ctx) == (ws_a.id, ws_c.id)
        assert fenced_collection_roles(ctx) == (ROLE_ADMIN,)
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# (c) foreign-tenant UUID inside the fence is never returned
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_foreign_tenant_workspace_inside_fence_is_never_returned() -> None:
    tenant, user = _tenant()
    ws_a = _workspace(tenant, "A")
    _grant(tenant, user, ws_a, ROLE_EDITOR)

    alien_tenant = Tenant.objects.create(
        name=f"alien-{uuid.uuid4().hex[:8]}",
        slug=f"alien-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    alien_ws = _workspace(alien_tenant, "ALIEN")
    # A role even in the foreign workspace must not make it visible either.
    _grant(alien_tenant, user, alien_ws, ROLE_EDITOR)

    ctx = _fenced_ctx(tenant, user, [ws_a, alien_ws])

    set_request_tenant(tenant.id)
    try:
        visible = fenced_visible_workspace_ids(ctx)
    finally:
        clear_request_tenant()

    assert visible == (ws_a.id,)
    assert alien_ws.id not in visible


# ---------------------------------------------------------------------------
# (d) suspended role does not count
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_suspended_role_does_not_make_a_workspace_visible() -> None:
    tenant, user = _tenant()
    ws_a, ws_c = _workspace(tenant, "A"), _workspace(tenant, "C")
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    suspended = _grant(tenant, user, ws_c, ROLE_EDITOR)

    from django.utils import timezone

    set_request_tenant(tenant.id)
    try:
        suspended.suspended_at = timezone.now()
        suspended.save(update_fields=["suspended_at"])
    finally:
        clear_request_tenant()

    ctx = _fenced_ctx(tenant, user, [ws_a, ws_c])

    set_request_tenant(tenant.id)
    try:
        assert fenced_visible_workspace_ids(ctx) == (ws_a.id,)
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Fenced-key-only contract
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unfenced_context_is_rejected() -> None:
    tenant, user = _tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_EDITOR,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    with pytest.raises(AssertionError):
        fenced_visible_workspace_ids(ctx)


# ---------------------------------------------------------------------------
# DoD: no extra query for unfenced keys (Bearer request unchanged)
# ---------------------------------------------------------------------------


def _mint_bearer(user: User, tenant: Tenant, roles: list[str]) -> str:
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


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
def test_bearer_workspace_list_issues_no_fence_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Bearer workspace list must not run the fence helpers at all.

    The proof is twofold: the helpers are patched to raise (so any call is a
    hard failure) and the query count equals the same request with the fence
    feature switch off — the pre-E1.1 profile.
    """
    tenant, user = _tenant()
    ws_a, ws_b = _workspace(tenant, "A"), _workspace(tenant, "B")
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    _grant(tenant, user, ws_b, ROLE_EDITOR)

    import auth_tenancy.resource_scope as resource_scope

    def _boom(*_args, **_kwargs):
        raise AssertionError("fence helper must not run for an unfenced key")

    monkeypatch.setattr(resource_scope, "fenced_visible_workspace_ids", _boom)
    monkeypatch.setattr(resource_scope, "fenced_collection_roles", _boom)

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {_mint_bearer(user, tenant, [ROLE_EDITOR])}"
    )

    # Warm the per-request caches (preset/tenant resolution) before measuring,
    # so both passes see the same steady-state query profile.
    assert client.get("/api/v1/workspaces/").status_code == 200

    with CaptureQueriesContext(connection) as with_fence:
        resp = client.get("/api/v1/workspaces/")
    assert resp.status_code == 200, resp.content

    with override_settings(AUTHZ_API_KEY_WORKSPACE_FENCE_ENFORCED=False):
        with CaptureQueriesContext(connection) as without_fence:
            resp2 = client.get("/api/v1/workspaces/")
    assert resp2.status_code == 200, resp2.content

    assert len(with_fence.captured_queries) == len(without_fence.captured_queries), (
        "an unfenced key must not pay for the fence: "
        f"{len(with_fence.captured_queries)} vs "
        f"{len(without_fence.captured_queries)} queries"
    )
    assert resp.json()["count"] == 2
