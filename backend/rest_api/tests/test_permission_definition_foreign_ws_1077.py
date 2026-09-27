"""GitHub #1077 — ``/workspaces/<id>/permission-definition/`` 500 + HTML on a
foreign workspace.

Observed on ``v1.8.0-beta.16``::

    GET /api/v1/workspaces/1111.../permission-definition/  -> 500  text/html
        <!doctype html> ... <title>Server Error (500)</title>

while the neighbouring routes on the same URL prefix answered properly::

    /members/    -> 403  {"error": "PERMISSION_DENIED", ...}
    /audit/      -> 404  {"error": {"code": "NOT_FOUND", ...}}

Root cause: the view resolved the workspace straight into
``PermissionDefinitionService.get_or_create_workspace``, which issues
``WorkspacePermissionDefinition.unscoped.get_or_create(workspace_id=...)``. A
workspace the caller has no standing over never reached an authorization check
— it failed the FK constraint, and the resulting ``InternalError`` is not a DRF
exception, so it escaped the exception handler as Django's HTML 500. That is
three defects at once: a 5xx for what is a permission question, HTML instead of
the JSON envelope every client parses, and a disclosure oracle for whether the
id exists.

Fix: ``rest_api.global_default_views._require_workspace_membership`` mirrors the
``/members/`` reference (same ``AuthorizationService.active_roles_for``
predicate) and answers ``403 PERMISSION_DENIED`` in the canonical envelope
before the service is ever called.

The two neighbouring contracts are pinned here too, because the fix must not
"helpfully" change them: ``/members/`` stays 403 and ``/audit/`` stays a
deliberate non-disclosure 404.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "permdef1077pass"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _tenant(slug: str) -> Tenant:
    return Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)


def _workspace(tenant: Tenant, name: str) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


def _admin_of(tenant: Tenant, workspace: Workspace, username: str) -> User:
    user = User.objects.create(
        username=username, email=f"{username}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return user


@pytest.fixture
def permdef_env():
    """Caller = tenant-admin of ``own_ws``; plus a foreign and a non-member ws.

    ``own_ws``    — the caller's own workspace (200 path).
    ``alien_ws``   — another tenant's workspace (the reported 500).
    ``neighbour_ws`` — same tenant, but the caller holds no role in it, which is
    the realistic variant of "a workspace the caller may not see".
    """
    own_tenant = _tenant(f"pd1077-own-{uuid.uuid4().hex[:8]}")
    other_tenant = _tenant(f"pd1077-other-{uuid.uuid4().hex[:8]}")

    own_ws = _workspace(own_tenant, "PD1077 Own WS")
    neighbour_ws = _workspace(own_tenant, "PD1077 Neighbour WS")
    alien_ws = _workspace(other_tenant, "PD1077 Alien WS")

    suffix = uuid.uuid4().hex[:8]
    admin = _admin_of(own_tenant, own_ws, f"pd1077-admin-{suffix}")

    return {
        "tenant": own_tenant,
        "other_tenant": other_tenant,
        "own_ws": own_ws,
        "neighbour_ws": neighbour_ws,
        "alien_ws": alien_ws,
        "admin": admin,
    }


def _client(user: User) -> APIClient:
    client = APIClient()
    with override_settings(**_JWT_OVERRIDES):
        login = client.post(
            "/api/v1/auth/login/",
            {"username": user.username, "password": _PASSWORD},
            format="json",
        )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _fake_ctx(user_id, tenant_id):
    """A tenant-admin AuthContext, as the view's own gate would see it."""
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _assert_canonical_403(response, *, what: str) -> None:
    """403, JSON content type, canonical envelope, no HTML anywhere.

    ``details`` is not constrained beyond being present: a 403 raised by DRF's
    RBAC gate carries the raw ``{"detail": ...}`` mapping, an explicit
    ``build_error_response`` 403 carries ``[]``.
    """
    assert response.status_code == 403, f"{what}: {response.status_code} {response.content!r}"
    content_type = response.headers.get("Content-Type", "")
    assert "application/json" in content_type, f"{what}: content type {content_type!r}"
    body = response.content.decode(errors="replace")
    assert "<html" not in body.lower(), f"{what}: HTML leaked into the body"
    assert "<!doctype" not in body.lower(), f"{what}: HTML leaked into the body"

    payload = response.json()
    assert set(payload) == {"error"}, payload
    assert set(payload["error"]) == {"code", "message", "details"}, payload
    assert payload["error"]["code"] == "PERMISSION_DENIED", payload
    assert payload["error"]["message"], payload


# ---------------------------------------------------------------------------
# The reported path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_foreign_workspace_permission_definition_answers_403_json(permdef_env) -> None:
    """#1077: a workspace in another tenant must be 403 + JSON, not 500 + HTML."""
    client = _client(permdef_env["admin"])

    response = client.get(
        f"/api/v1/workspaces/{permdef_env['alien_ws'].id}/permission-definition/"
    )

    _assert_canonical_403(response, what="GET foreign permission-definition")


@override_settings(**_JWT_OVERRIDES)
def test_non_member_workspace_permission_definition_answers_403_json(
    permdef_env,
) -> None:
    """Same-tenant but no role: also 403, never a 5xx."""
    client = _client(permdef_env["admin"])

    response = client.get(
        f"/api/v1/workspaces/{permdef_env['neighbour_ws'].id}/permission-definition/"
    )

    _assert_canonical_403(response, what="GET non-member permission-definition")


@override_settings(**_JWT_OVERRIDES)
def test_membership_gate_is_reached_for_a_tenant_admin_of_another_workspace(
    permdef_env,
) -> None:
    """The view's own gate must reject a tenant admin of a *different* workspace.

    Without the guard, a caller who passes the admin check still reached
    ``get_or_create_workspace`` and failed the FK. Whether the refusal comes
    from the view's ``_require_workspace_membership`` or from DRF's
    workspace-scoped RBAC gate, the client sees one 403 envelope.
    """
    from rest_api.global_default_views import _require_workspace_membership

    ctx = _fake_ctx(permdef_env["admin"].id, permdef_env["tenant"].id)
    set_request_tenant(permdef_env["tenant"].id)
    try:
        denied_foreign = _require_workspace_membership(
            ctx, str(permdef_env["alien_ws"].id), "en"
        )
        denied_neighbour = _require_workspace_membership(
            ctx, str(permdef_env["neighbour_ws"].id), "en"
        )
        allowed_own = _require_workspace_membership(
            ctx, str(permdef_env["own_ws"].id), "en"
        )
    finally:
        clear_request_tenant()

    assert denied_foreign is not None and denied_foreign.status_code == 403
    assert denied_neighbour is not None and denied_neighbour.status_code == 403
    assert allowed_own is None


@override_settings(**_JWT_OVERRIDES)
def test_write_verbs_are_guarded_too(permdef_env) -> None:
    """PATCH and the reset route reach the same service and must be guarded.

    Without the guard a foreign id failed the FK on the *write* as well, so a
    caller could not even get a clean 403 for a mutation.
    """
    client = _client(permdef_env["admin"])
    alien = permdef_env["alien_ws"].id

    patch = client.patch(
        f"/api/v1/workspaces/{alien}/permission-definition/",
        {"permission_json": {"viewer": {"write": True}}},
        format="json",
    )
    _assert_canonical_403(patch, what="PATCH foreign permission-definition")

    put = client.put(
        f"/api/v1/workspaces/{alien}/permission-definition/",
        {"permission_json": {"viewer": {"write": True}}},
        format="json",
    )
    _assert_canonical_403(put, what="PUT foreign permission-definition")

    reset = client.post(f"/api/v1/workspaces/{alien}/permission-definition/reset/")
    _assert_canonical_403(reset, what="POST foreign permission-definition/reset")


@override_settings(**_JWT_OVERRIDES)
def test_unknown_workspace_id_is_indistinguishable_from_a_foreign_one(
    permdef_env,
) -> None:
    """No existence oracle: an id that does not exist answers exactly the same.

    The 403 carries no distinguishing field, and a caller must not be able to
    tell "exists but not yours" from "never existed" — that difference is what
    made the old 500 an information leak.
    """
    client = _client(permdef_env["admin"])

    foreign = client.get(
        f"/api/v1/workspaces/{permdef_env['alien_ws'].id}/permission-definition/"
    )
    unknown = client.get(
        f"/api/v1/workspaces/{uuid.uuid4()}/permission-definition/"
    )

    assert foreign.status_code == unknown.status_code == 403
    assert foreign.json() == unknown.json(), (foreign.json(), unknown.json())


# ---------------------------------------------------------------------------
# No regression on the happy path or on the neighbouring routes
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_own_workspace_permission_definition_still_answers_200(permdef_env) -> None:
    client = _client(permdef_env["admin"])
    own = permdef_env["own_ws"].id

    assert (
        client.get(f"/api/v1/workspaces/{own}/permission-definition/").status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/workspaces/{own}/permission-definition/",
            {"permission_json": {"viewer": {"write": True}}},
            format="json",
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/workspaces/{own}/permission-definition/reset/").status_code
        == 200
    )


@override_settings(**_JWT_OVERRIDES)
def test_neighbouring_members_route_keeps_its_403(permdef_env) -> None:
    """``/members/`` is the reference and must keep answering 403.

    Only the *shape* of that body is #1081's business (it still emits the flat
    string form, see test_error_envelope_single_form_1081.py); the status is
    the contract pinned here.
    """
    client = _client(permdef_env["admin"])

    response = client.get(f"/api/v1/workspaces/{permdef_env['alien_ws'].id}/members/")

    assert response.status_code == 403, response.content


@override_settings(**_JWT_OVERRIDES)
def test_neighbouring_audit_route_keeps_its_non_disclosure_404(permdef_env) -> None:
    """``/audit/`` answers a deliberate 404 and must NOT be turned into a 403.

    ``_assert_workspace_in_tenant`` encodes a documented non-disclosure choice
    for that surface. This test exists so a future "consistency" sweep cannot
    silently overwrite it with the permission-definition semantics.
    """
    client = _client(permdef_env["admin"])
    alien_id = permdef_env["alien_ws"].id

    response = client.get(f"/api/v1/workspaces/{alien_id}/audit/")

    assert response.status_code == 404, response.content
    body = response.json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message", "details"}, body
    assert body["error"]["code"] == "NOT_FOUND", body
    assert body["error"]["message"] == (
        f"Workspace '{alien_id}' was not found in the caller's tenant."
    ), body
