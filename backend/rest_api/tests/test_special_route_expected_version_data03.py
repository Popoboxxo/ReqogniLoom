"""DATA-03 (AUD-2026-09-282) — special REST routes must be CAS-protected.

The generic ``transitions/`` action already forwards ``If-Match`` /
``expected_version`` into the engine (CR-08). The dedicated special routes that
go through a service wrapper did not, so a stale revision was silently
overwritten. ``/adrs/{pk}/supersede/`` and
``/change-requests/{pk}/transition/`` were fixed by ``5e392aa7``; this file
pins the remaining two on the REST surface:

* ``POST /api/v1/main-goals/{pk}/approve/``
* ``POST /api/v1/goals/{pk}/outdate/``
* ``POST /api/v1/goals/{pk}/reactivate/``

Each stale case must answer **409 CONFLICT** (``OptimisticLockError``), and the
current revision must still succeed. Before the fix the view dropped the
asserted revision entirely and answered 200.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from rest_api.views import GoalViewSet, MainGoalViewSet
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


def _make_auth_context(*, tenant_id, roles=("admin",)):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _new_tenant_and_workspace(tenant_name: str, **workspace_kwargs):
    tenant = Tenant.objects.create(name=tenant_name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, **workspace_kwargs)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _provision(workspace, preset: str, item_type: str) -> None:
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


def _engine_version(tenant_id, item_id, item_type, workspace_id) -> int:
    TenantContext.set_tenant(tenant_id)
    try:
        return WorkflowItemState.objects.get(
            item_id=item_id, item_type=item_type, workspace_id=workspace_id
        ).version
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# MainGoal approve
# ---------------------------------------------------------------------------


def test_main_goal_approve_stale_revision_is_409_and_current_succeeds():
    tenant, workspace = _new_tenant_and_workspace(
        "data03-rest-main-goal", name="W", goals_enabled=True
    )
    _provision(workspace, "main_goal_default", "MainGoal")
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft."},
        format="json",
    )
    create_req.auth_context = ctx
    created = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201, created.data
    main_goal_id = created.data["id"]
    current = _engine_version(tenant.id, main_goal_id, "MainGoal", workspace.id)

    stale_req = factory.post(
        f"/api/v1/main-goals/{main_goal_id}/approve/",
        {"change_reason": "stale", "expected_version": current + 1},
        format="json",
    )
    stale_req.auth_context = ctx
    stale = MainGoalViewSet.as_view({"post": "approve"})(stale_req, pk=main_goal_id)
    assert stale.status_code == 409, stale.data
    assert stale.data["error"]["code"] == "CONFLICT"

    # The rejected attempt must not have mutated the row, so the current
    # revision still succeeds on the next try.
    ok_req = factory.post(
        f"/api/v1/main-goals/{main_goal_id}/approve/",
        {"change_reason": "approved", "expected_version": current},
        format="json",
    )
    ok_req.auth_context = ctx
    ok = MainGoalViewSet.as_view({"post": "approve"})(ok_req, pk=main_goal_id)
    assert ok.status_code == 200, ok.data
    assert ok.data["status"] == "Freigegeben"


# ---------------------------------------------------------------------------
# Goal outdate / reactivate
# ---------------------------------------------------------------------------


def _create_goal(factory, ctx, workspace) -> str:
    req = factory.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace.id), "title": "DATA-03 goal"},
        format="json",
    )
    req.auth_context = ctx
    resp = GoalViewSet.as_view({"post": "create"})(req)
    assert resp.status_code == 201, resp.data
    return resp.data["id"]


def test_goal_outdate_stale_revision_is_409_and_current_succeeds():
    tenant, workspace = _new_tenant_and_workspace(
        "data03-rest-goal-outdate", name="W", goals_enabled=True
    )
    _provision(workspace, "goal_default", "Goal")
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()
    goal_id = _create_goal(factory, ctx, workspace)
    current = _engine_version(tenant.id, goal_id, "Goal", workspace.id)

    stale_req = factory.post(
        f"/api/v1/goals/{goal_id}/outdate/",
        {"change_reason": "stale", "expected_version": current + 1},
        format="json",
    )
    stale_req.auth_context = ctx
    stale = GoalViewSet.as_view({"post": "outdate"})(stale_req, pk=goal_id)
    assert stale.status_code == 409, stale.data
    assert stale.data["error"]["code"] == "CONFLICT"

    ok_req = factory.post(
        f"/api/v1/goals/{goal_id}/outdate/",
        {"change_reason": "archive", "expected_version": current},
        format="json",
    )
    ok_req.auth_context = ctx
    ok = GoalViewSet.as_view({"post": "outdate"})(ok_req, pk=goal_id)
    assert ok.status_code == 200, ok.data
    assert ok.data["status"] == "Archiviert"


def test_goal_reactivate_stale_revision_is_409_and_current_succeeds():
    tenant, workspace = _new_tenant_and_workspace(
        "data03-rest-goal-reactivate", name="W", goals_enabled=True
    )
    _provision(workspace, "goal_default", "Goal")
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()
    goal_id = _create_goal(factory, ctx, workspace)

    # Archive once so a genuinely stale revision exists.
    archive_req = factory.post(
        f"/api/v1/goals/{goal_id}/outdate/",
        {"change_reason": "archive"},
        format="json",
    )
    archive_req.auth_context = ctx
    archived = GoalViewSet.as_view({"post": "outdate"})(archive_req, pk=goal_id)
    assert archived.status_code == 200, archived.data
    current = _engine_version(tenant.id, goal_id, "Goal", workspace.id)

    stale_req = factory.post(
        f"/api/v1/goals/{goal_id}/reactivate/",
        {"change_reason": "stale", "expected_version": current - 1},
        format="json",
    )
    stale_req.auth_context = ctx
    stale = GoalViewSet.as_view({"post": "reactivate"})(stale_req, pk=goal_id)
    assert stale.status_code == 409, stale.data
    assert stale.data["error"]["code"] == "CONFLICT"

    ok_req = factory.post(
        f"/api/v1/goals/{goal_id}/reactivate/",
        {"change_reason": "restore", "expected_version": current},
        format="json",
    )
    ok_req.auth_context = ctx
    ok = GoalViewSet.as_view({"post": "reactivate"})(ok_req, pk=goal_id)
    assert ok.status_code == 200, ok.data
    assert ok.data["status"] == "Entwurf"
