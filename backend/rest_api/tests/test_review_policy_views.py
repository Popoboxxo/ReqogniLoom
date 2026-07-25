"""
REQ-L2-RV-001 — ReviewPolicy REST endpoint tests.

Covers:
- GET/PUT /api/v1/workspaces/{workspace_id}/review-policy/ (admin-only).
- Default response (no row yet) is mode="auto", min_confidence=0.7.
- Non-admin roles are rejected with 403.
- Invalid mode / out-of-range min_confidence are rejected with 400.

Uses the same JWT + APIClient pattern as test_llm_settings.py.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import ReviewPolicy, Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def review_policy_tenant(db):
    """A tenant with an admin, an editor user, and a workspace."""
    tenant = Tenant.objects.create(name="RV T", slug="rv-t", is_active=True)
    admin = User.objects.create(
        username="rvadmin", email="rvadmin@t.test", tenant=tenant
    )
    admin.set_password("rvpass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(
        username="rveditor", email="rveditor@t.test", tenant=tenant
    )
    editor.set_password("rvpass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="RV WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        yield tenant, workspace
    finally:
        clear_request_tenant()


def _login(client: APIClient, username: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "rvpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.json()["token"]


def _auth(client: APIClient, token: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_admin_can_get_and_update_review_policy(review_policy_tenant):
    tenant, workspace = review_policy_tenant
    client = APIClient()
    _auth(client, _login(client, "rvadmin"))

    resp = client.get(f"/api/v1/workspaces/{workspace.id}/review-policy/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "auto"
    assert body["min_confidence"] == 0.7

    resp = client.put(
        f"/api/v1/workspaces/{workspace.id}/review-policy/",
        {"mode": "review_all", "min_confidence": 0.9},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "review_all"
    assert body["min_confidence"] == 0.9

    set_request_tenant(tenant.id)
    row = ReviewPolicy.objects.get(tenant_id=tenant.id, workspace_id=workspace.id)
    assert row.mode == "review_all"
    assert row.min_confidence == 0.9


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_admin_cannot_read_or_update_review_policy(review_policy_tenant):
    _tenant, workspace = review_policy_tenant
    client = APIClient()
    _auth(client, _login(client, "rveditor"))

    assert (
        client.get(f"/api/v1/workspaces/{workspace.id}/review-policy/").status_code
        == 403
    )
    resp = client.put(
        f"/api/v1/workspaces/{workspace.id}/review-policy/",
        {"mode": "review_all", "min_confidence": 0.9},
        format="json",
    )
    assert resp.status_code == 403


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_update_review_policy_rejects_invalid_mode(review_policy_tenant):
    _tenant, workspace = review_policy_tenant
    client = APIClient()
    _auth(client, _login(client, "rvadmin"))

    resp = client.put(
        f"/api/v1/workspaces/{workspace.id}/review-policy/",
        {"mode": "bogus", "min_confidence": 0.9},
        format="json",
    )
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_update_review_policy_rejects_out_of_range_confidence(review_policy_tenant):
    _tenant, workspace = review_policy_tenant
    client = APIClient()
    _auth(client, _login(client, "rvadmin"))

    resp = client.put(
        f"/api/v1/workspaces/{workspace.id}/review-policy/",
        {"mode": "auto", "min_confidence": 1.5},
        format="json",
    )
    assert resp.status_code == 400
