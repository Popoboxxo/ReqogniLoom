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
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from auth_tenancy.resource_scope import workspace_fence_denial
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

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
