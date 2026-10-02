"""SEC-02 + SEC-03: object-derived workspace fence on REST (ADR-011).

Covers the two acceptance criteria from
``docs/audit/2026-09/review/plan/SECURITY_AUTHZ.md``:

* **SEC-02** — a Bearer/API-Key caller holding a role in workspace A but not in
  B is denied (403) when reaching a B object through a *detail route* that
  carries no ``workspace`` path segment (the leak Finding ``AUD-2026-09-222``).
  The object-derived seam is gated by ``AUTHZ_WORKSPACE_SCOPE_ENFORCED``; the
  tests turn it on explicitly where the enforcement is under test.
* **SEC-03** — the API-key ``workspace_ids`` fence and ``expires_at`` are
  enforced on REST too, using the *same* fence implementation as MCP
  (``auth_tenancy.resource_scope.workspace_fence_denial``).

req_id: ADR-011, findings 222 / N2 / 240 / 035.
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    TenantRole,
    UserRole,
)
from auth_tenancy.resource_scope import workspace_fence_denial
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    Risk,
    Tenant,
    User,
    Workspace,
)

_SECRET = "sec02-sec03-fence-test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)
_PASSWORD = "hunter2pass"


def _tenant_with_two_workspaces() -> tuple[Tenant, User, Workspace, Workspace]:
    slug = f"sec-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(
            tenant=tenant, name=f"WS-A-{slug}", preset={"name": "extended"}
        )
        ws_b = Workspace.objects.create(
            tenant=tenant, name=f"WS-B-{slug}", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()
    return tenant, user, ws_a, ws_b


def _grant(tenant: Tenant, user: User, workspace: Workspace, role: str) -> None:
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()


def _requirement_in(tenant: Tenant, workspace: Workspace) -> Requirement:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact=artifact,
            title=f"req-in-{workspace.name}",
            description="sec02 fixture",
        )
    finally:
        clear_request_tenant()


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


def _bearer_client(user: User, tenant: Tenant, roles: list[str] | None = None) -> APIClient:
    client = APIClient()
    # The claim carries the elevated role on purpose: a workspace-scoped
    # decision must not trust the tenant-wide snapshot.
    token = _mint_bearer(user, tenant, roles or [ROLE_ADMIN])
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _user_key_client(user: User, tenant: Tenant) -> APIClient:
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name="sec-user-key"
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=result.plaintext)
    return client


# ---------------------------------------------------------------------------
# SEC-02 — object-derived detail-route fence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_sec02_bearer_without_target_role_is_denied_on_detail_route() -> None:
    """Role in A, none in B: reading a B object via the detail route is 403."""
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    req_b = _requirement_in(tenant, ws_b)
    client = _bearer_client(user, tenant)

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 403, (
        "object-derived fence must deny a detail read of a workspace-B object "
        f"for a caller with no role in B (got {resp.status_code}: {resp.content!r})"
    )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_sec02_api_key_without_target_role_is_denied_on_detail_route() -> None:
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    req_b = _requirement_in(tenant, ws_b)
    client = _user_key_client(user, tenant)

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 403, resp.content


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_sec02_member_of_target_workspace_still_reads_detail_route() -> None:
    """No regression: a member of the object's workspace keeps access."""
    tenant, user, _ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_b, ROLE_EDITOR)
    req_b = _requirement_in(tenant, ws_b)
    client = _bearer_client(user, tenant, roles=[ROLE_EDITOR])

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 200, resp.content


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=False)
def test_sec02_flag_off_documents_pre_fix_leak() -> None:
    """Characterizes the gap the flag closes (kept OFF by the SEC-02 hard-stop).

    With enforcement disabled the same B-object detail read returns 200 — this
    is the measured Finding 222 leak, and it is exactly what
    ``AUTHZ_WORKSPACE_SCOPE_ENFORCED=True`` turns into a 403 above.
    """
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    req_b = _requirement_in(tenant, ws_b)
    client = _bearer_client(user, tenant)

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 200, resp.content


# ---------------------------------------------------------------------------
# SEC-03 — API-key workspace_ids fence + expires_at on REST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sec03_fenced_agent_key_denied_on_ws_b_detail_route() -> None:
    """A key fenced to WS A gets 403 for a WS-B object (default settings)."""
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    req_b = _requirement_in(tenant, ws_b)
    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="sec03-fenced",
        principal_type="agent",
        scope="write",
        workspace_ids=[str(ws_a.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=key.plaintext)

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
@override_settings(AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_sec03_fenced_agent_key_allowed_on_fenced_workspace() -> None:
    """No over-blocking: the fenced key keeps access inside its own workspace.

    With the scope seam on, the key's roles are resolved against the object's
    workspace (A) instead of being blanked on the workspace-less detail route,
    so the fence permits the call exactly inside its own workspace.
    """
    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    req_a = _requirement_in(tenant, ws_a)
    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="sec03-fenced-ok",
        principal_type="agent",
        scope="write",
        workspace_ids=[str(ws_a.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=key.plaintext)

    resp = client.get(f"/api/v1/requirements/{req_a.id}/")

    assert resp.status_code == 200, resp.content


@pytest.mark.django_db
def test_sec03_unfenced_user_key_unaffected() -> None:
    """A key without a fence keeps its pre-ADR behaviour."""
    tenant, user, _ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_b, ROLE_ADMIN)
    req_b = _requirement_in(tenant, ws_b)
    client = _user_key_client(user, tenant)

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 200, resp.content


@pytest.mark.django_db
def test_sec03_expired_key_returns_401_on_rest() -> None:
    """An expired key stops authenticating on REST (401 api_key_expired)."""
    tenant, user, _ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_b, ROLE_ADMIN)
    req_b = _requirement_in(tenant, ws_b)
    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="sec03-expired",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=key.plaintext)

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 401, resp.content
    assert resp.json()["error"]["code"] == "api_key_expired"


def test_sec03_rest_and_mcp_share_one_fence_implementation() -> None:
    """MCP's ``_check_workspace_fence`` delegates to the shared REST fence."""
    from mcp_server.tool_registry import ToolRegistry

    fenced_ctx = type(
        "Ctx", (), {"api_key_workspace_ids": ("11111111-1111-1111-1111-111111111111",)}
    )()
    unfenced_ctx = type("Ctx", (), {"api_key_workspace_ids": ()})()

    cases = [
        (fenced_ctx, "11111111-1111-1111-1111-111111111111"),  # inside fence
        (fenced_ctx, "22222222-2222-2222-2222-222222222222"),  # outside fence
        (fenced_ctx, None),  # no target -> fail closed
        (unfenced_ctx, None),  # no fence -> allow
    ]
    for ctx, target in cases:
        assert ToolRegistry._check_workspace_fence(ctx, target) == (
            workspace_fence_denial(ctx.api_key_workspace_ids, target)
        )


# ---------------------------------------------------------------------------
# ADR-013 — collection-route rule: no blanket 403 on list/create, and the
# 404-vs-403 rule on object routes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_collection_list_without_target_workspace_is_not_scope_denied() -> None:
    """A flat list with no workspace is answered by the endpoint (400), not 403.

    The seam must not blanket-deny a collection route: the list endpoint owns
    its workspace resolution and, absent one, its own validation is the answer.
    """
    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    client = _bearer_client(user, tenant)

    resp = client.get("/api/v1/needs/")

    assert resp.status_code == 400, (
        "list without a workspace must reach the endpoint's own validation, "
        f"not be scope-denied (got {resp.status_code}: {resp.content!r})"
    )
    assert resp.json()["error"]["code"] != "PERMISSION_DENIED"


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_collection_create_derives_target_workspace_from_payload() -> None:
    """Create on the flat route uses the payload ``workspace_id`` and succeeds.

    The auth layer scopes the caller's roles to that workspace, so a member is
    allowed; the seam itself does not deny the create.
    """
    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    client = _bearer_client(user, tenant)

    resp = client.post(
        "/api/v1/needs/",
        {"workspace_id": str(ws_a.id), "title": "ADR-013 flat create"},
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["workspace_id"] == str(ws_a.id)


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_object_route_for_missing_object_is_404_not_403() -> None:
    """A well-formed id with no row is 404, not a 403 that would leak existence."""
    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    client = _bearer_client(user, tenant)

    resp = client.get(f"/api/v1/requirements/{uuid.uuid4()}/")

    assert resp.status_code == 404, (
        f"missing object must answer 404, not 403 (got {resp.status_code}: "
        f"{resp.content!r})"
    )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_workspaceless_list_returns_only_the_named_workspace() -> None:
    """The list endpoint filters by the workspace named in the URL/query.

    This is the "list filters, does not blanket-403" half of the rule: a member
    of A sees A's objects and none of B's.
    """
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    _requirement_in(tenant, ws_a)
    _requirement_in(tenant, ws_b)
    client = _bearer_client(user, tenant)

    resp = client.get(f"/api/v1/requirements/?workspace_id={ws_a.id}")

    assert resp.status_code == 200, resp.content
    titles = {item["title"] for item in resp.json()["results"]}
    assert "req-in-WS-A" in titles or any("WS-A" in t for t in titles), titles
    assert all("WS-B" not in t for t in titles), titles


# ---------------------------------------------------------------------------
# SEC-02 review M1 — content-type-independent create fence (form/multipart)
# ---------------------------------------------------------------------------


def _grant_tenant_admin(tenant: Tenant, user: User) -> None:
    set_request_tenant(tenant.id)
    try:
        TenantRole.objects.create(
            tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN
        )
    finally:
        clear_request_tenant()


def _risks_in(tenant: Tenant, workspace: Workspace) -> int:
    set_request_tenant(tenant.id)
    try:
        return Risk.objects.filter(workspace_id=workspace.id).count()
    finally:
        clear_request_tenant()


@pytest.mark.parametrize(
    "post_kwargs",
    [
        {"content_type": "application/x-www-form-urlencoded"},
        {"format": "multipart"},
    ],
)
@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_form_create_with_foreign_workspace_is_denied_and_never_written(
    post_kwargs: dict,
) -> None:
    """M1 regression: a non-JSON create smuggling a foreign ``workspace_id``.

    The caller holds a role in WS-A only. The create names WS-B in a
    form-urlencoded / multipart body. Without the content-type-independent
    resolution the auth layer would have kept the tenant-wide admin roles and
    the write would land in WS-B; with it the target resolves and the request
    is denied. Nothing may be written to WS-B.
    """
    from urllib.parse import urlencode

    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    before = _risks_in(tenant, ws_b)
    client = _bearer_client(user, tenant)
    body = {"workspace_id": str(ws_b.id), "title": "smuggled"}
    if "format" not in post_kwargs:
        # ``content_type`` alone does not URL-encode an APIClient dict body, so
        # send the encoded string to guarantee a real form-encoded payload.
        body = urlencode(body)

    resp = client.post("/api/v1/risks/", body, **post_kwargs)

    assert resp.status_code == 403, (
        "a form/multipart create naming a foreign workspace must be denied at "
        f"the seam: got {resp.status_code}: {resp.content!r}"
    )
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
    assert _risks_in(tenant, ws_b) == before, "foreign workspace must not be written"


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_form_create_in_own_workspace_still_succeeds() -> None:
    """No over-blocking: the same form body targeting the caller's workspace works."""
    from urllib.parse import urlencode

    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    client = _bearer_client(user, tenant)

    resp = client.post(
        "/api/v1/risks/",
        urlencode({"workspace_id": str(ws_a.id), "title": "legit"}),
        content_type="application/x-www-form-urlencoded",
    )

    assert resp.status_code == 201, resp.content
    assert _risks_in(tenant, ws_a) == 1


# ---------------------------------------------------------------------------
# SEC-02 review residual — query/body workspace mismatch on a create
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "post_kwargs",
    [
        {"format": "json"},
        {"content_type": "application/x-www-form-urlencoded"},
    ],
)
@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_query_body_workspace_mismatch_is_denied_and_never_written(
    post_kwargs: dict,
) -> None:
    """Residual regression: query names WS-A, body names WS-B.

    The caller holds a role in WS-A only. Before the fix the query value scoped
    the caller's roles to WS-A while the serializer persisted the body value
    WS-B (same-tenant cross-workspace write). The request must be denied and
    nothing may be written to either workspace.
    """
    from urllib.parse import urlencode

    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    before_a = _risks_in(tenant, ws_a)
    before_b = _risks_in(tenant, ws_b)
    client = _bearer_client(user, tenant)
    body = {"workspace_id": str(ws_b.id), "title": "mismatch"}
    if "format" not in post_kwargs:
        body = urlencode(body)

    resp = client.post(
        f"/api/v1/risks/?workspace_id={ws_a.id}", body, **post_kwargs
    )

    assert resp.status_code == 403, (
        "a create naming WS-A in the query and WS-B in the body must be denied: "
        f"got {resp.status_code}: {resp.content!r}"
    )
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
    assert _risks_in(tenant, ws_b) == before_b, "WS-B must not be written"
    assert _risks_in(tenant, ws_a) == before_a, "WS-A must not be written"


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_query_body_workspace_mismatch_denied_even_with_role_in_both() -> None:
    """The mismatch is rejected outright, not silently resolved to the body.

    The caller holds a role in both workspaces, so RBAC alone would admit the
    call; only the explicit mismatch denial keeps the two named targets from
    diverging. This is the assertion that isolates the seam decision.
    """
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    _grant(tenant, user, ws_b, ROLE_ADMIN)
    before_a = _risks_in(tenant, ws_a)
    before_b = _risks_in(tenant, ws_b)
    client = _bearer_client(user, tenant)

    resp = client.post(
        f"/api/v1/risks/?workspace_id={ws_a.id}",
        {"workspace_id": str(ws_b.id), "title": "mismatch"},
        format="json",
    )

    assert resp.status_code == 403, resp.content
    assert "does not match" in str(resp.json()["error"]), (
        "expected the mismatch denial, not a generic RBAC denial: "
        f"{resp.json()['error']!r}"
    )
    assert _risks_in(tenant, ws_a) == before_a
    assert _risks_in(tenant, ws_b) == before_b


@pytest.mark.parametrize(
    "post_kwargs",
    [
        {"format": "json"},
        {"content_type": "application/x-www-form-urlencoded"},
    ],
)
@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_create_with_consistent_query_and_body_still_succeeds(
    post_kwargs: dict,
) -> None:
    """No over-blocking: a create naming the same workspace in query and body works."""
    from urllib.parse import urlencode

    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    before_a = _risks_in(tenant, ws_a)
    client = _bearer_client(user, tenant)
    body = {"workspace_id": str(ws_a.id), "title": "consistent"}
    if "format" not in post_kwargs:
        body = urlencode(body)

    resp = client.post(
        f"/api/v1/risks/?workspace_id={ws_a.id}", body, **post_kwargs
    )

    assert resp.status_code == 201, resp.content
    assert _risks_in(tenant, ws_a) == before_a + 1


# ---------------------------------------------------------------------------
# SEC-02 review M3 — no cross-tenant existence leak (foreign tenant => 404)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_foreign_tenant_object_detail_is_404_not_403() -> None:
    """An object in another tenant is indistinguishable from a missing one."""
    tenant_a, user_a, ws_a, _ws_a2 = _tenant_with_two_workspaces()
    _grant(tenant_a, user_a, ws_a, ROLE_ADMIN)
    tenant_b, _user_b, ws_b, _ws_b2 = _tenant_with_two_workspaces()
    req_b = _requirement_in(tenant_b, ws_b)
    client = _bearer_client(user_a, tenant_a)

    resp = client.get(f"/api/v1/requirements/{req_b.id}/")

    assert resp.status_code == 404, (
        "a foreign-tenant object must 404, never 403 (no existence leak): "
        f"got {resp.status_code}: {resp.content!r}"
    )


# ---------------------------------------------------------------------------
# SEC-02 review CODE-1 — central membership check on entity_key=None routes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path_tmpl,body",
    [
        ("put", "/api/v1/workspaces/{ws}/banner/", {"level": "info", "enabled": True}),
        (
            "put",
            "/api/v1/workspaces/{ws}/review-policy/",
            {"mode": "off", "min_confidence": 0.5},
        ),
        (
            "post",
            "/api/v1/workspaces/{ws}/members/",
            {"user_id": str(uuid.uuid4()), "role": ROLE_EDITOR},
        ),
    ],
)
@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_non_member_denied_on_workspace_named_write_route(
    method: str, path_tmpl: str, body: dict
) -> None:
    """A non-member is denied (403) on a workspace-scoped, workspace-named route.

    The JWT carries an elevated admin snapshot; authority is still derived from
    the target workspace, where the caller holds no role.
    """
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_ADMIN)
    client = _bearer_client(user, tenant)
    path = path_tmpl.format(ws=ws_b.id)

    resp = getattr(client, method)(path, body, format="json")

    assert resp.status_code == 403, (
        f"non-member on {method.upper()} {path_tmpl} must be denied: "
        f"got {resp.status_code}: {resp.content!r}"
    )


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES, AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_tenant_admin_elevation_still_reaches_workspace_named_route() -> None:
    """Defence in depth must not lock out the documented System-Admin elevation.

    A tenant admin holds no workspace-level ``UserRole`` (``active_roles=()``),
    but the restore of the central membership check must still admit them via
    the tenant-admin branch; the view/service applies the elevation.
    """
    tenant, user, _ws_a, ws_b = _tenant_with_two_workspaces()
    _grant_tenant_admin(tenant, user)
    client = _bearer_client(user, tenant)

    resp = client.put(
        f"/api/v1/workspaces/{ws_b.id}/banner/",
        {"level": "info", "enabled": True},
        format="json",
    )

    assert resp.status_code == 200, resp.content
