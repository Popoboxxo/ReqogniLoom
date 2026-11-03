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

    # Detail for an uninitialized (item_type, preset) → initialized:false, no
    # 404. Workspace provisioning pre-seeds the three rigor presets for every
    # item type, so use a preset key this type does not provision.
    resp = client.get("/api/v1/workflow-defaults/Document/ccb_approval/")
    assert resp.status_code == 200
    assert resp.json()["initialized"] is False

    # Initialize, then add a state.
    resp = client.post("/api/v1/workflow-defaults/Document/ccb_approval/initialize/")
    assert resp.status_code == 201, resp.content
    assert resp.json()["scope"] == "global"

    resp = client.post(
        "/api/v1/workflow-defaults/Document/ccb_approval/states/", {"name": "draft"}
    )
    assert resp.status_code == 201, resp.content
    assert "draft" in resp.json()["states"]

    # Re-initialize → 409 already initialized.
    resp = client.post("/api/v1/workflow-defaults/Document/ccb_approval/initialize/")
    assert resp.status_code == 409


@override_settings(**_JWT)
@pytest.mark.django_db
def test_unknown_workflow_item_type_is_not_found(admin_client):
    """R-F2-2 (Plan F F2-T2): a typo must not look like an empty workflow."""
    client, tenant, user, ws = admin_client

    resp = client.get("/api/v1/workflow-defaults/NoSuchType/extended/")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"

    resp = client.post("/api/v1/workflow-defaults/NoSuchType/extended/initialize/")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"

    resp = client.post(
        "/api/v1/workflow-defaults/NoSuchType/extended/states/", {"name": "draft"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


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
def test_workspace_permission_catalog_is_preset_truthful(admin_client):
    """#1592: the workspace catalogue advertises only assignable roles.

    ``members`` rejects ``approver`` outside the extended preset; the catalogue
    must not advertise it there. The stored matrix keeps the row so a later
    preset upgrade is lossless, and a GET→PUT round-trip of the filtered
    catalogue is accepted.
    """
    client, tenant, user, extended_ws = admin_client
    TenantContext.set_tenant(tenant.id)
    try:
        ctx = _admin_ctx(tenant, user)
        minimal_ws = WorkspaceService().create_workspace(
            ctx, name="WS-minimal", preset="minimal"
        )
        standard_ws = WorkspaceService().create_workspace(
            ctx, name="WS-standard", preset="standard"
        )
    finally:
        TenantContext.clear_tenant()

    minimal_catalog = None
    for ws in (minimal_ws, standard_ws):
        body = client.get(
            f"/api/v1/workspaces/{ws.id}/permission-definition/"
        ).json()
        assert set(body["permission_json"]) == {"admin", "editor", "viewer"}
        assert body["assignable_roles"] == ["admin", "editor", "viewer"]
        assert "approver" not in body["permission_json"]
        if ws is minimal_ws:
            minimal_catalog = body["permission_json"]

    extended = client.get(
        f"/api/v1/workspaces/{extended_ws.id}/permission-definition/"
    ).json()
    assert set(extended["permission_json"]) == {
        "admin",
        "editor",
        "viewer",
        "approver",
    }
    assert extended["assignable_roles"] == [
        "admin",
        "editor",
        "viewer",
        "approver",
    ]

    # Echoing the filtered catalogue back must not fail matrix validation —
    # the non-assignable approver row is restored from the stored matrix.
    echoed = client.put(
        f"/api/v1/workspaces/{minimal_ws.id}/permission-definition/",
        {"permission_json": minimal_catalog},
        format="json",
    )
    assert echoed.status_code == 200, echoed.content
    assert "approver" not in echoed.json()["permission_json"]


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
