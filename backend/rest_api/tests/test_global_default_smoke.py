"""End-to-end smoke coverage for the global-default endpoints (REQ-178..187).

Exercises the full request path (auth + admin gate + service + persistence) for
the global workflow default lifecycle, the global permission matrix + guarded
enforcement flip, workspace permission override/reset, workspace workflow reset,
and the mismatch review log.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext

_JWT = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _admin_ctx(tenant, user):
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def admin_client(db):
    tenant = Tenant.objects.create(name="SmokeTenant")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        tenant=tenant, username="smokeadmin", email="a@x.io", is_active=True
    )
    user.set_password("smokepass123")
    user.save()
    ctx = _admin_ctx(tenant, user)
    # create_workspace() already grants the creator an 'admin' UserRole (#232).
    ws = WorkspaceService().create_workspace(ctx, name="WS", preset="extended")

    client = APIClient()
    with override_settings(**_JWT):
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": "smokeadmin", "password": "smokepass123"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    TenantContext.clear_tenant()
    return client, tenant, user, ws


@override_settings(**_JWT)
@pytest.mark.django_db
def test_global_workflow_default_lifecycle(admin_client):
    client, tenant, user, ws = admin_client

    # List returns the backfilled/provisioned globals.
    resp = client.get("/api/v1/workflow-defaults/")
    assert resp.status_code == 200, resp.content
    assert "workflow_defaults" in resp.json()

    # Detail for an uninitialized (item_type, preset) → initialized:false, no 404.
    resp = client.get("/api/v1/workflow-defaults/SmokeType/extended/")
    assert resp.status_code == 200
    assert resp.json()["initialized"] is False

    # Initialize, then add a state.
    resp = client.post("/api/v1/workflow-defaults/SmokeType/extended/initialize/")
    assert resp.status_code == 201, resp.content
    assert resp.json()["scope"] == "global"

    resp = client.post(
        "/api/v1/workflow-defaults/SmokeType/extended/states/", {"name": "draft"}
    )
    assert resp.status_code == 201, resp.content
    assert "draft" in resp.json()["states"]

    # Re-initialize → 409 already initialized.
    resp = client.post("/api/v1/workflow-defaults/SmokeType/extended/initialize/")
    assert resp.status_code == 409


@override_settings(**_JWT)
@pytest.mark.django_db
def test_global_permission_matrix_and_flip(admin_client):
    client, tenant, user, ws = admin_client

    resp = client.get("/api/v1/permission-defaults/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    # SEC-02: new tenants start authoritative (matrix mirrors legacy 1:1).
    assert body["enforcement_mode"] == "authoritative"
    assert body["permission_json"]["editor"]["read"] is True

    # PUT with enforcement_mode in body → 400 ENFORCEMENT_MODE_NOT_EDITABLE_HERE.
    resp = client.put(
        "/api/v1/permission-defaults/",
        {"permission_json": body["permission_json"], "enforcement_mode": "authoritative"},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ENFORCEMENT_MODE_NOT_EDITABLE_HERE"

    # PUT a malformed matrix → 400 VALIDATION_ERROR.
    resp = client.put(
        "/api/v1/permission-defaults/", {"permission_json": {"admin": {}}}, format="json"
    )
    assert resp.status_code == 400

    # PATCH a single capability (deep-merge + full revalidate) → 200.
    resp = client.patch(
        "/api/v1/permission-defaults/",
        {"permission_json": {"viewer": {"write": True}}},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["permission_json"]["viewer"]["write"] is True

    # Enforcement status: zero mismatches → ready.
    resp = client.get("/api/v1/permission-defaults/enforcement/")
    assert resp.status_code == 200
    assert resp.json()["pending_mismatch_count"] == 0

    # Rollback to shadow needs no confirmation (puts the tenant into the
    # shadow phase so the guarded shadow→authoritative flip can be tested).
    resp = client.post(
        "/api/v1/permission-defaults/enforcement/flip/",
        {"enforcement_mode": "shadow"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["enforcement_mode"] == "shadow"

    # Flip guard: wrong confirmed count → 409 MISMATCH_COUNT_STALE.
    resp = client.post(
        "/api/v1/permission-defaults/enforcement/flip/",
        {"enforcement_mode": "authoritative", "confirm_pending_mismatch_count": 99},
        format="json",
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "MISMATCH_COUNT_STALE"

    # Flip with correct count → 200.
    resp = client.post(
        "/api/v1/permission-defaults/enforcement/flip/",
        {"enforcement_mode": "authoritative", "confirm_pending_mismatch_count": 0},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["enforcement_mode"] == "authoritative"


@override_settings(**_JWT)
@pytest.mark.django_db
def test_workspace_permission_override_and_reset(admin_client):
    client, tenant, user, ws = admin_client

    resp = client.get(f"/api/v1/workspaces/{ws.id}/permission-definition/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_customized"] is False

    resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/permission-definition/",
        {"permission_json": {"viewer": {"write": True}}},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_customized"] is True
    assert resp.json()["permission_json"]["viewer"]["write"] is True

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/permission-definition/reset/"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_customized"] is False
    assert resp.json()["permission_json"]["viewer"]["write"] is False


@override_settings(**_JWT)
@pytest.mark.django_db
def test_workspace_workflow_reset(admin_client):
    client, tenant, user, ws = admin_client

    # Edit the workspace Requirement workflow → is_customized flips True.
    resp = client.post(
        "/api/v1/workflows/definition/states/",
        {"workspace_id": str(ws.id), "item_type": "Requirement", "name": "smoke_state"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["is_customized"] is True

    # Reset → mirrors global, is_customized False.
    resp = client.post(
        "/api/v1/workflows/definition/reset/",
        {"workspace_id": str(ws.id), "item_type": "Requirement"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["is_customized"] is False
    assert "smoke_state" not in resp.json()["states"]


@override_settings(**_JWT)
@pytest.mark.django_db
def test_mismatch_list_empty(admin_client):
    client, tenant, user, ws = admin_client
    resp = client.get("/api/v1/permission-mismatches/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] == 0
    assert body["results"] == []
