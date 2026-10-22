"""E1.2 — REST: fence before RBAC, filtered workspace list, honest errors.

Plan E (2026-10-21), E1.2 / issue #1444. Pins the REST half of the fenced-key
contract:

* ``GET /api/v1/workspaces/`` with a workspace-scoped key returns only the
  workspaces the key is issued for **and** its owner holds a role in;
* an owner with no role in any fence workspace gets the specific 403 instead of
  the generic RBAC text;
* a workspace-less call outside the list names the fence (the fence precheck
  now runs *before* the RBAC matrix);
* a Bearer token's list is unchanged.
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
from auth_tenancy.models import ROLE_EDITOR, UserRole
from auth_tenancy.resource_scope import (
    API_KEY_NO_OWNER_ROLE_IN_FENCE_DENIAL,
    workspace_fence_denial,
)
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "e1-2-rest-fence-test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)
_PASSWORD = "hunter2pass"


def _tenant_with_two_workspaces() -> tuple[Tenant, User, Workspace, Workspace]:
    slug = f"e12-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(tenant=tenant, name=f"WS-A-{slug}", preset={})
        ws_b = Workspace.objects.create(tenant=tenant, name=f"WS-B-{slug}", preset={})
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


def _fenced_key_client(
    tenant: Tenant, user: User, workspace_ids: list[Workspace]
) -> APIClient:
    result = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="e12-fenced",
        principal_type="agent",
        scope="author",
        workspace_ids=[str(ws.id) for ws in workspace_ids],
        expires_at=timezone.now() + timedelta(days=1),
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=result.plaintext)
    return client


def _bearer_client(user: User, tenant: Tenant, roles: list[str]) -> APIClient:
    now = int(time.time())
    token = encode_hs256(
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
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_fenced_key_lists_only_its_workspaces() -> None:
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    _grant(tenant, user, ws_b, ROLE_EDITOR)
    client = _fenced_key_client(tenant, user, [ws_a])

    resp = client.get("/api/v1/workspaces/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] == 1, body
    assert [row["id"] for row in body["results"]] == [str(ws_a.id)]


@pytest.mark.django_db
def test_fenced_key_without_owner_role_gets_specific_403() -> None:
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    # The owner holds a role only in B, the key is fenced to A.
    _grant(tenant, user, ws_b, ROLE_EDITOR)
    client = _fenced_key_client(tenant, user, [ws_a])

    resp = client.get("/api/v1/workspaces/")

    assert resp.status_code == 403, resp.content
    error = resp.json()["error"]
    assert error["code"] == "PERMISSION_DENIED"
    assert error["message"] == API_KEY_NO_OWNER_ROLE_IN_FENCE_DENIAL


@pytest.mark.django_db
def test_fenced_key_workspaceless_call_names_the_fence() -> None:
    """The fence precheck runs before the RBAC matrix, so the caller sees the
    fence text instead of "no active role permits 'read'"."""
    tenant, user, ws_a, _ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    client = _fenced_key_client(tenant, user, [ws_a])

    resp = client.get("/api/v1/search/?q=x")

    assert resp.status_code == 403, resp.content
    error = resp.json()["error"]
    assert error["code"] == "PERMISSION_DENIED"
    expected = workspace_fence_denial([str(ws_a.id)], None)
    assert expected is not None
    assert error["message"] == expected


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
def test_bearer_list_unchanged() -> None:
    tenant, user, ws_a, ws_b = _tenant_with_two_workspaces()
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    client = _bearer_client(user, tenant, [ROLE_EDITOR])

    resp = client.get("/api/v1/workspaces/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] == 2, body
    assert {row["id"] for row in body["results"]} == {str(ws_a.id), str(ws_b.id)}
