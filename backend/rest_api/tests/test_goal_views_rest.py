"""REST-level coverage for MainGoalViewSet and GoalViewSet (views.py).

leaf_id : COMP-RA-MG (MainGoalViewSet), COMP-RA-GL (GoalViewSet)
req_id  : REQ-L2-TE-020, REQ-176, GH-403

The Goal hierarchy endpoints (workspace-scoped Goal lineages plus the single
MainGoal version chain). This module drives the real middleware stack:

  - MainGoal: manual create, list scoping, retrieve, the approval gate
    (``approve``), the ``current`` empty-state contract, ``versions``/``diff``;
  - the ``generate`` action through the mock LLM provider (never a live call);
  - Goal: lineage create/retrieve/list with query params, the designed-in
    405s for PATCH/DELETE and the ``outdate``/``reactivate`` archive cycle.
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


def _scenario(*, goals_ai_enabled: bool = False) -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"go-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"go-{suffix}", email=f"go-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant,
            name="GO WS",
            preset={"name": "extended"},
            goals_ai_enabled=goals_ai_enabled,
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _initialize_workflow(client: APIClient, workspace: Workspace, item_type: str) -> None:
    """Seed the workflow definition the transition endpoints resolve against."""
    resp = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": item_type},
        format="json",
    )
    assert resp.status_code == 201, resp.content


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


def _create_main_goal(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "content": "the product shall delight its users",
        **overrides,
    }
    resp = client.post("/api/v1/main-goals/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _create_goal(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "GO goal",
        "description": "a measurable goal",
        **overrides,
    }
    resp = client.post("/api/v1/goals/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# MainGoalViewSet
# ---------------------------------------------------------------------------


def test_main_goal_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/main-goals/").status_code == 401


def test_main_goal_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/main-goals/?status=approved")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_main_goal_create_requires_content() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/main-goals/", {"workspace_id": str(workspace.id)}, format="json"
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "content" in fields


def test_main_goal_current_of_an_empty_workspace_is_null() -> None:
    """No approved MainGoal yet — the editor's empty state is 200 + null."""
    _, user, workspace = _scenario()
    resp = _client(user).get(f"/api/v1/main-goals/current/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.content in (b"", b"null"), resp.content


def test_main_goal_current_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/main-goals/current/")
    assert resp.status_code == 400, resp.content


def test_main_goal_create_retrieve_list_roundtrip() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = _create_main_goal(client, workspace)
    main_goal_id = created["id"]
    assert created["source"] == "manual"

    detail = client.get(f"/api/v1/main-goals/{main_goal_id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["content"] == created["content"]

    listed = client.get(f"/api/v1/main-goals/?workspace_id={workspace.id}")
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [main_goal_id]

    missing = client.get(f"/api/v1/main-goals/{uuid.uuid4()}/")
    assert missing.status_code == 404, missing.content


def test_main_goal_list_is_scoped_to_the_tenant() -> None:
    _tenant, user, workspace = _scenario()
    _create_main_goal(_client(user), workspace)

    _, other_user, other_ws = _scenario()
    _create_main_goal(_client(other_user), other_ws)

    resp = _client(user).get(f"/api/v1/main-goals/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 1


def test_main_goal_approve_moves_the_draft_through_the_workflow() -> None:
    """The approval gate runs through the WorkflowEngine — not a raw field write."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    # The workflow graph must exist before the item is created, so the engine
    # finds a WorkflowItemState to transition.
    _initialize_workflow(client, workspace, "MainGoal")
    main_goal_id = _create_main_goal(client, workspace)["id"]

    resp = client.post(
        f"/api/v1/main-goals/{main_goal_id}/approve/",
        {"change_reason": "signed off"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["id"] == main_goal_id
    assert body["content"], "the full serialized goal comes back, not a bare dict"


def test_main_goal_approve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        f"/api/v1/main-goals/{uuid.uuid4()}/approve/", {}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_main_goal_versions_and_diff_read_actions() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    main_goal_id = _create_main_goal(client, workspace)["id"]

    versions = client.get(f"/api/v1/main-goals/{main_goal_id}/versions/")
    assert versions.status_code == 200, versions.content

    diff = client.get(
        f"/api/v1/main-goals/{main_goal_id}/diff/?from_version=0&to_version=1"
    )
    assert diff.status_code == 200, diff.content

    invalid = client.get(f"/api/v1/main-goals/{main_goal_id}/diff/?from_version=abc")
    assert invalid.status_code == 400, invalid.content


def test_main_goal_generate_uses_the_mock_provider() -> None:
    """``generate`` aggregates the workspace Goals — with LLM_PROVIDER=mock the
    call must answer deterministically without a live endpoint. Only approved
    (Freigegeben) Goals feed the aggregation, so the goal is approved first."""
    _tenant, user, workspace = _scenario(goals_ai_enabled=True)
    client = _client(user)
    # The workflow graph must exist before the goal is created, so the engine
    # finds a WorkflowItemState to transition.
    _initialize_workflow(client, workspace, "Goal")
    goal_id = _create_goal(client, workspace)["id"]

    approved = client.post(
        f"/api/v1/goals/{goal_id}/transitions/",
        {"target_state": "Freigegeben", "change_reason": "Reviewed and approved."},
        format="json",
    )
    assert approved.status_code == 200, approved.content
    assert approved.json()["new_state"] == "Freigegeben"

    resp = client.post(
        "/api/v1/main-goals/generate/",
        {"workspace_id": str(workspace.id)},
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["workspace_id"] == str(workspace.id)
    assert body["source"] == "ai"
    assert body["content"], "the mock provider drafts the aggregated content"
    assert "is_mock_fallback" in body


def test_main_goal_generate_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post("/api/v1/main-goals/generate/", {}, format="json")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_main_goal_generate_rejects_malformed_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        "/api/v1/main-goals/generate/", {"workspace_id": "nope"}, format="json"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


# ---------------------------------------------------------------------------
# GoalViewSet
# ---------------------------------------------------------------------------


def test_goal_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/goals/").status_code == 401


def test_goal_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/goals/?search=x")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_goal_create_and_retrieve_roundtrip() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)

    created = _create_goal(client, workspace, title="Lineage root")
    assert created["title"] == "Lineage root"

    detail = client.get(f"/api/v1/goals/{created['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["id"] == created["id"]

    listed = client.get(
        f"/api/v1/goals/?workspace_id={workspace.id}&search=Lineage&ordering=title"
    )
    assert listed.status_code == 200, listed.content
    assert [row["id"] for row in listed.json()["results"]] == [created["id"]]


def test_goal_create_appends_a_new_version_to_the_lineage() -> None:
    """Lineage semantics: POST with ``lineage_id`` creates a new version row."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    first = _create_goal(client, workspace, title="V1")

    second = _create_goal(
        client, workspace, title="V2", lineage_id=first["lineage_id"]
    )

    assert second["id"] != first["id"]
    assert second["lineage_id"] == first["lineage_id"]
    assert second["sequence_number"] > first["sequence_number"]


def test_goal_create_without_title_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        "/api/v1/goals/", {"workspace_id": str(workspace.id)}, format="json"
    )
    assert resp.status_code == 400, resp.content


def test_goal_retrieve_unknown_id_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/goals/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_goal_patch_is_refused_with_405() -> None:
    """Goals are lineage-versioned — in-place mutation is a designed-in 405."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    goal_id = _create_goal(client, workspace)["id"]

    resp = client.patch(
        f"/api/v1/goals/{goal_id}/", {"title": "edited"}, format="json"
    )

    assert resp.status_code == 405, resp.content
    assert "new version" in resp.json()["error"]["message"]


def test_goal_delete_is_refused_with_405() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    goal_id = _create_goal(client, workspace)["id"]

    resp = client.delete(f"/api/v1/goals/{goal_id}/")

    assert resp.status_code == 405, resp.content
    assert "outdate" in resp.json()["error"]["message"]


def test_goal_outdate_and_reactivate_roundtrip() -> None:
    """Archiving a Goal version is the documented way out of active use."""
    _tenant, user, workspace = _scenario()
    client = _client(user)
    # The workflow graph must exist before the item is created, so the engine
    # finds a WorkflowItemState to transition.
    _initialize_workflow(client, workspace, "Goal")
    goal_id = _create_goal(client, workspace)["id"]

    archived = client.post(
        f"/api/v1/goals/{goal_id}/outdate/", {"change_reason": "done"}, format="json"
    )
    assert archived.status_code == 200, archived.content

    hidden = client.get(f"/api/v1/goals/?workspace_id={workspace.id}")
    assert hidden.json()["count"] == 0, "the archived version leaves list_current"

    revived = client.post(f"/api/v1/goals/{goal_id}/reactivate/", {}, format="json")
    assert revived.status_code == 200, revived.content

    visible = client.get(f"/api/v1/goals/?workspace_id={workspace.id}")
    assert visible.json()["count"] == 1


def test_goal_versions_and_diff_read_actions() -> None:
    _tenant, user, workspace = _scenario()
    client = _client(user)
    goal_id = _create_goal(client, workspace)["id"]

    versions = client.get(f"/api/v1/goals/{goal_id}/versions/")
    assert versions.status_code == 200, versions.content

    diff = client.get(f"/api/v1/goals/{goal_id}/diff/?from_version=0&to_version=1")
    assert diff.status_code == 200, diff.content
