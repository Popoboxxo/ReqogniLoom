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

from typing import Any

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
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
    tenant: Tenant,
    workspace: Workspace | None,
    *,
    role: str | None,
    suffix: str = "",
) -> APIClient:
    """Create a user, log them in, and return an authed client.

    ``role=None`` creates a user with NO role assignment anywhere in the
    tenant (the "correctly still denied" control case). ``suffix`` keeps
    usernames unique when one test needs two actors of the same role.
    """
    name = f"ak-rbac-{role or 'none'}{suffix}"
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=name,
            email=f"{name}@t.test",
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
    """A Viewer (READ-only role) can create their own API key (#716).

    #1608 bounds the *scope* of the key, not the ability to mint one: a
    Viewer keeps the #716 access path by asking for a read-scoped key
    explicitly. A Viewer asking for write is refused — see the
    ``test_viewer_*`` cases below.
    """
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    resp = client.post(
        "/api/v1/api-keys/", {"name": "my-viewer-key", "scope": "read"}, format="json"
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["name"] == "my-viewer-key"
    assert body["plaintext"].startswith("reqlo_")
    assert body["scope"] == "read"


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

    create_resp = client.post(
        "/api/v1/api-keys/", {"name": "revoke-me", "scope": "read"}, format="json"
    )
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


# ---------------------------------------------------------------------------
# #1608 — the key's scope may not exceed its creator's own effective rights
# ---------------------------------------------------------------------------
#
# ``POST /api/v1/api-keys/`` is deliberately self-service (READ, #716), which
# also means the RBAC matrix does not answer "may this caller hand out a write
# capability?". ``scope`` is a capability tier above the matrix, so an
# unbounded create let a Viewer mint an ADMIN-tier credential. The rule
# implemented below: any scope above read-only requires effective ``write`` in
# at least one *addressed* workspace (the key's fence for agent keys; every
# workspace where the owner holds a role otherwise). ``read`` stays open to
# every role — no silent downgrade, a refusal is a 403 ``PERMISSION_DENIED``.

_FUTURE_EXPIRY = "2999-01-01T00:00:00+00:00"


def _create(client: APIClient, payload: dict) -> Any:
    return client.post("/api/v1/api-keys/", payload, format="json")


def _assert_scope_denied(resp: Any) -> None:
    """A refused scope is a 403 PERMISSION_DENIED, never a 400 or a downgrade."""
    assert resp.status_code == 403, resp.content
    body = resp.json()
    assert body["error"]["code"] == "PERMISSION_DENIED", body
    assert body["error"]["message"], body


@pytest.mark.django_db
def test_viewer_cannot_create_write_scoped_key(tenant, workspace):
    """The #1608 repro: viewer + scope=write must not mint a key."""
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    resp = _create(client, {"name": "escalation", "scope": "write"})

    _assert_scope_denied(resp)
    # Nothing was persisted: no orphan credential, not even a read-scoped one.
    listed = client.get("/api/v1/api-keys/").json()
    assert listed["results"] == []


@pytest.mark.django_db
def test_viewer_cannot_create_key_with_the_default_scope(tenant, workspace):
    """Omitting ``scope`` defaults to write — that default is bounded too.

    Without this case a Viewer could dodge the bound by simply not naming a
    scope, because user keys default to ``write`` in the service.
    """
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    resp = _create(client, {"name": "implicit-write"})

    _assert_scope_denied(resp)


@pytest.mark.django_db
def test_viewer_can_create_read_scoped_key_with_both_spellings(tenant, workspace):
    """``read`` and ``read_only`` stay available to every role in the tenant."""
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    legacy = _create(client, {"name": "read-legacy", "scope": "read"})
    canonical = _create(client, {"name": "read-canonical", "scope": "read_only"})

    assert legacy.status_code == 201, legacy.content
    assert canonical.status_code == 201, canonical.content


@pytest.mark.django_db
@pytest.mark.parametrize("role", [ROLE_EDITOR, ROLE_APPROVER, ROLE_ADMIN])
def test_write_capable_roles_can_create_write_scoped_key(tenant, workspace, role):
    """Editor/Approver/Admin hold WRITE in the addressed workspace, so 201."""
    client = _make_authed_client(tenant, workspace, role=role)

    resp = _create(client, {"name": f"{role}-write", "scope": "write"})

    assert resp.status_code == 201, resp.content
    assert resp.json()["scope"] == "write"


@pytest.mark.django_db
def test_editor_can_create_author_scoped_key(tenant, workspace):
    """``author`` is a narrower write tier than ``write``; WRITE still covers it."""
    client = _make_authed_client(tenant, workspace, role=ROLE_EDITOR)

    resp = _create(client, {"name": "editor-author", "scope": "author"})

    assert resp.status_code == 201, resp.content
    assert resp.json()["scope"] == "author"


@pytest.mark.django_db
def test_viewer_agent_key_is_bounded_by_the_creator_roles(tenant, workspace):
    """``principal_type=agent`` inherits the same bound, not a loophole."""
    client = _make_authed_client(tenant, workspace, role=ROLE_VIEWER)

    resp = _create(
        client,
        {
            "name": "viewer-agent",
            "principal_type": "agent",
            "agent_label": "probe",
            "scope": "author",
            "workspace_ids": [str(workspace.id)],
            "expires_at": _FUTURE_EXPIRY,
        },
    )

    _assert_scope_denied(resp)


@pytest.mark.django_db
def test_editor_agent_key_is_allowed_inside_the_fence(tenant, workspace):
    """An editor's agent key may carry a write tier for the fenced workspace."""
    client = _make_authed_client(tenant, workspace, role=ROLE_EDITOR)

    resp = _create(
        client,
        {
            "name": "editor-agent",
            "principal_type": "agent",
            "agent_label": "probe",
            "scope": "author",
            "workspace_ids": [str(workspace.id)],
            "expires_at": _FUTURE_EXPIRY,
        },
    )

    assert resp.status_code == 201, resp.content


@pytest.mark.django_db
def test_the_fence_is_the_addressed_workspace_not_every_membership(tenant, workspace):
    """Write rights elsewhere do not authorise a write tier for a foreign fence.

    The rule is "write in at least one *addressed* workspace": an editor who
    is fenced to a workspace they hold no role in addresses only that
    workspace, so the key may be read-scoped but not write-scoped.
    """
    set_request_tenant(tenant.id)
    try:
        other = Workspace.objects.create(
            tenant=tenant, name="AK-RBAC-OTHER", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()
    client = _make_authed_client(tenant, workspace, role=ROLE_EDITOR)

    resp = _create(
        client,
        {
            "name": "foreign-fence",
            "principal_type": "agent",
            "agent_label": "probe",
            "scope": "author",
            "workspace_ids": [str(other.id)],
            "expires_at": _FUTURE_EXPIRY,
        },
    )

    _assert_scope_denied(resp)


@pytest.mark.django_db
def test_scope_bound_helper_activates_the_tenant_it_judges(tenant, workspace):
    """The shared helper works for callers without an active tenant context.

    Routed traffic always arrives with the tenant activated by
    ``AuthTenancyAuthentication``, but the helper is the documented seam for any
    future issuing surface (an MCP tool, a management command). It therefore
    activates the tenant it was asked about for its tenant-scoped role lookups
    and restores the caller's state afterwards, instead of raising
    ``TenantContextNotSetError`` or silently reading another tenant.
    """
    from auth_tenancy.resource_scope import api_key_scope_creation_denial
    from persistence.tenancy import TenantContext

    _make_authed_client(tenant, workspace, role=ROLE_VIEWER)
    viewer = User.objects.get(username="ak-rbac-viewer")

    assert TenantContext.is_set() is False

    assert (
        api_key_scope_creation_denial(
            user_id=viewer.id, tenant_id=tenant.id, scope="write"
        )
        is not None
    )
    assert (
        api_key_scope_creation_denial(
            user_id=viewer.id, tenant_id=tenant.id, scope="read"
        )
        is None
    )
    # The caller's (empty) context is restored — the helper leaked nothing.
    assert TenantContext.is_set() is False

