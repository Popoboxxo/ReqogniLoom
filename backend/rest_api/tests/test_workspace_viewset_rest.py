"""REST-level coverage for WorkspaceViewSet (views.py).

leaf_id : COMP-RA-WS (WorkspaceViewSet)
req_id  : REQ-L2-RF-007, REQ-L2-RF-012, REQ-L1-042, REQ-176

The captcha hard-delete paths are already pinned by ``test_workspace_delete*``;
this module covers the remaining handler surface through the real middleware
stack (JWT, RBAC, service layer, test database):

  - ``list``/``retrieve`` happy paths plus the cross-tenant read fence;
  - ``create`` validation (serializer errors, unusable ``preset`` shapes);
  - ``partial_update`` field forwarding, the ``is_active`` lifecycle toggle
    (including every ``_coerce_bool`` acceptance/refusal branch) and the
    "no recognized field" pass-through;
  - ``set_preset``/``clone``/``close``/``reactivate`` action contracts.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant with one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"ws-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ws-{suffix}", email=f"ws-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS Roundtrip", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


# ---------------------------------------------------------------------------
# Auth + read surface
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/workspaces/").status_code == 401


def test_list_returns_only_the_callers_tenant_workspaces() -> None:
    _, user, workspace = _scenario()
    _, _, other_ws = _scenario()

    resp = _client(user).get("/api/v1/workspaces/")

    assert resp.status_code == 200, resp.content
    ids = [row["id"] for row in resp.json()["results"]]
    assert str(workspace.id) in ids
    assert str(other_ws.id) not in ids, "another tenant's workspace leaked"


def test_retrieve_and_unknown_id_contract() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    ok = client.get(f"/api/v1/workspaces/{workspace.id}/")
    assert ok.status_code == 200, ok.content
    assert ok.json()["name"] == "WS Roundtrip"

    missing = client.get(f"/api/v1/workspaces/{uuid.uuid4()}/")
    assert missing.status_code == 404, missing.content
    assert missing.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# create — serializer validation and preset-shape handling
# ---------------------------------------------------------------------------


def test_create_without_name_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post("/api/v1/workspaces/", {"preset": "standard"}, format="json")

    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "name" in fields


def test_create_with_unusable_preset_object_returns_400() -> None:
    """GH-411 accepts a tier string or an object carrying one — nothing else."""
    _, user, _ = _scenario()
    resp = _client(user).post(
        "/api/v1/workspaces/", {"name": "WS X", "preset": {"-color": "blue"}}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert "preset must be" in resp.json()["error"]["message"]


def test_create_roundtrips_the_resolved_preset_object_shape() -> None:
    """A client may POST back the resolved ``{"tier": ...}`` shape it GETs."""
    _, user, _ = _scenario()
    resp = _client(user).post(
        "/api/v1/workspaces/",
        {"name": "WS Tier Object", "preset": {"tier": "standard", "name": "standard"}},
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["preset"]["tier"] == "standard"


# ---------------------------------------------------------------------------
# partial_update — metadata, lifecycle toggle and the pass-through branch
# ---------------------------------------------------------------------------


def test_patch_updates_name_and_serializes_the_result() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{workspace.id}/",
        {"name": "WS Renamed", "language": "en"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["name"] == "WS Renamed"


def test_patch_with_only_unknown_fields_returns_current_state() -> None:
    """A body with no recognized field is not an error — it is a no-op read."""
    _, user, workspace = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{workspace.id}/", {"ai_prompts": {"x": 1}}, format="json"
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["id"] == str(workspace.id)


def test_patch_with_non_boolean_is_active_returns_400() -> None:
    """``_coerce_bool`` refuses: a non-boolean must not be silently truthy."""
    _, user, workspace = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{workspace.id}/", {"is_active": "maybe"}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "is_active must be a boolean"


def test_patch_string_lifecycle_toggles_close_and_reactivate() -> None:
    """``"off"``/``"yes"`` strings ride the same close/reactivate service calls."""
    _, user, workspace = _scenario()
    client = _client(user)

    closed = client.patch(
        f"/api/v1/workspaces/{workspace.id}/", {"is_active": "off"}, format="json"
    )
    assert closed.status_code == 200, closed.content
    assert closed.json()["is_active"] is False
    assert closed.json()["closed_at"] is not None

    reopened = client.patch(
        f"/api/v1/workspaces/{workspace.id}/", {"is_active": "yes"}, format="json"
    )
    assert reopened.status_code == 200, reopened.content
    assert reopened.json()["is_active"] is True


def test_patch_integer_is_active_is_coerced() -> None:
    """DRF-BooleanField-compatible ``0``/``1`` integers are accepted."""
    _, user, workspace = _scenario()
    client = _client(user)

    closed = client.patch(
        f"/api/v1/workspaces/{workspace.id}/", {"is_active": 0}, format="json"
    )
    assert closed.status_code == 200, closed.content
    assert closed.json()["is_active"] is False

    reopened = client.patch(
        f"/api/v1/workspaces/{workspace.id}/", {"is_active": 1}, format="json"
    )
    assert reopened.status_code == 200, reopened.content
    assert reopened.json()["is_active"] is True


def test_patch_unknown_workspace_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{uuid.uuid4()}/", {"name": "x"}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_patch_of_foreign_tenant_workspace_is_refused() -> None:
    """Cross-tenant write fence on the metadata route."""
    _, user, _ = _scenario()
    _, _, foreign = _scenario()

    resp = _client(user).patch(
        f"/api/v1/workspaces/{foreign.id}/", {"name": "hijacked"}, format="json"
    )
    assert resp.status_code in (403, 404), resp.content


# ---------------------------------------------------------------------------
# Action endpoints: preset / clone / close / reactivate
# ---------------------------------------------------------------------------


def test_set_preset_switches_the_active_tier() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{workspace.id}/preset/", {"preset": "minimal"}, format="json"
    )

    assert resp.status_code == 200, resp.content
    assert resp.json() == {"id": str(workspace.id), "preset": "minimal"}


def test_set_preset_with_unusable_shape_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).patch(
        f"/api/v1/workspaces/{workspace.id}/preset/", {"preset": 42}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert "preset must be" in resp.json()["error"]["message"]


def test_set_preset_of_foreign_tenant_workspace_returns_403() -> None:
    """SYSTEMAUDIT-2026-08-27 AP-6 M-1: the gate's CrossTenantWorkspaceError
    must surface as 403, not fall through to a masked 500."""
    _, user, _ = _scenario()
    _, _, foreign = _scenario()

    resp = _client(user).patch(
        f"/api/v1/workspaces/{foreign.id}/preset/", {"preset": "standard"}, format="json"
    )

    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


def test_clone_requires_target_name() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        f"/api/v1/workspaces/{workspace.id}/clone/", {"target_name": "   "}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "target_name is required"


def test_clone_creates_a_new_workspace_with_the_requested_name() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        f"/api/v1/workspaces/{workspace.id}/clone/",
        {"target_name": "WS Clone"},
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["name"] == "WS Clone"
    assert body["id"] != str(workspace.id)


def test_close_and_reactivate_actions_manage_the_lifecycle() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    closed = client.post(f"/api/v1/workspaces/{workspace.id}/close/", {}, format="json")
    assert closed.status_code == 200, closed.content
    assert closed.json()["is_active"] is False

    revived = client.post(
        f"/api/v1/workspaces/{workspace.id}/reactivate/", {}, format="json"
    )
    assert revived.status_code == 200, revived.content
    assert revived.json()["is_active"] is True


def test_close_of_unknown_workspace_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        f"/api/v1/workspaces/{uuid.uuid4()}/close/", {}, format="json"
    )
    assert resp.status_code == 404, resp.content
