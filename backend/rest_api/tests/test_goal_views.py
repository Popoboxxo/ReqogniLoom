"""
Tests for GoalViewSet REST endpoints (REQ-L2-TE-020, Task 6).

Covers:
  GET  /api/v1/goals/?workspace_id=<id>
  POST /api/v1/goals/
  GET  /api/v1/goals/{pk}/versions/

Uses DRF APIRequestFactory with a real AuthContext attached to the request
and real DB fixtures (django_db) — no service mocking — so the full
ViewSet -> GoalService -> DB round trip is exercised, mirroring the pattern
used by rest_api/tests/test_needs_routing.py and
rest_api/tests/test_glossary_versioning_views.py. There is no
``auth_client_factory`` fixture in this codebase (verified: no such fixture
exists in rest_api/tests/conftest.py or elsewhere), so the request-factory +
``req.auth_context`` pattern used by every other ViewSet test is mirrored
instead.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from rest_api.views import GoalViewSet

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
    """Create a Tenant + Workspace under an active TenantContext.

    persistence.tenancy.TenantScopedModel.objects.create() requires
    TenantContext.set_tenant() before any tenant-scoped query (ARCH-L1-011);
    mirrors application/tests/test_main_goal_service.py's setUp pattern.
    """
    tenant = Tenant.objects.create(name=tenant_name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, **workspace_kwargs)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def test_create_and_list_goal():
    tenant, workspace = _new_tenant_and_workspace("T1", name="W1", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)

    factory = APIRequestFactory()
    create_req = factory.post(
        "/api/v1/goals/",
        {
            "workspace_id": str(workspace.id),
            "title": "Reduce onboarding time",
            "description": "Cut onboarding from 5 days to 2 days.",
        },
        format="json",
    )
    create_req.auth_context = ctx
    create_resp = GoalViewSet.as_view({"post": "create"})(create_req)

    assert create_resp.status_code == 201
    assert create_resp.data["title"] == "Reduce onboarding time"
    assert create_resp.data["sequence_number"] == 1

    list_req = factory.get(f"/api/v1/goals/?workspace_id={workspace.id}")
    list_req.auth_context = ctx
    list_resp = GoalViewSet.as_view({"get": "list"})(list_req)

    assert list_resp.status_code == 200
    assert len(list_resp.data["results"]) == 1
    assert list_resp.data["results"][0]["title"] == "Reduce onboarding time"


def test_create_goal_requires_goals_enabled():
    tenant, workspace = _new_tenant_and_workspace("T2", name="W2", goals_enabled=False)
    ctx = _make_auth_context(tenant_id=tenant.id)

    factory = APIRequestFactory()
    req = factory.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace.id), "title": "Some goal"},
        format="json",
    )
    req.auth_context = ctx
    resp = GoalViewSet.as_view({"post": "create"})(req)

    # Feature-gate/authorization concern → 403, not a 400 validation error
    # (#271 item 4: PermissionDeniedError instead of ValidationError).
    assert resp.status_code == 403


def test_list_goal_requires_workspace_id():
    tenant = Tenant.objects.create(name="T3")
    ctx = _make_auth_context(tenant_id=tenant.id)

    factory = APIRequestFactory()
    req = factory.get("/api/v1/goals/")
    req.auth_context = ctx
    resp = GoalViewSet.as_view({"get": "list"})(req)

    assert resp.status_code == 400


def test_goal_versions_endpoint_lists_lineage():
    tenant, workspace = _new_tenant_and_workspace("T4", name="W4", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace.id), "title": "Goal v1"},
        format="json",
    )
    create_req.auth_context = ctx
    first = GoalViewSet.as_view({"post": "create"})(create_req)
    assert first.status_code == 201

    second_req = factory.post(
        "/api/v1/goals/",
        {
            "workspace_id": str(workspace.id),
            "title": "Goal v2",
            "lineage_id": first.data["lineage_id"],
        },
        format="json",
    )
    second_req.auth_context = ctx
    second = GoalViewSet.as_view({"post": "create"})(second_req)
    assert second.status_code == 201

    versions_req = factory.get(f"/api/v1/goals/{first.data['id']}/versions/")
    versions_req.auth_context = ctx
    versions_resp = GoalViewSet.as_view({"get": "versions"})(versions_req, pk=first.data["id"])

    assert versions_resp.status_code == 200
    assert len(versions_resp.data) == 2
    assert versions_resp.data[0]["sequence_number"] == 1
    assert versions_resp.data[1]["sequence_number"] == 2


def _provision_goal_workflow(workspace):
    """Create a real WorkflowEngineDefinition for Goal on *workspace*.

    Mirrors rest_api/tests/test_main_goal_views.py's
    ``_provision_main_goal_workflow``: ad-hoc test workspaces bypass
    ``workspace_provisioning.provision_workspace_defaults``, so the
    transitions endpoint would otherwise have no WorkflowItemState to move.
    """
    from persistence.tenancy import TenantContext
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="goal_default",
            item_type="Goal",
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


def test_goal_transitions_endpoint_approves_goal():
    """End-to-end Goal workflow transition over REST (WorkflowTransitionsMixin).

    Entwurf -> Freigegeben is gated to approver/admin with a mandatory
    change_reason (workflow/definition_store.py ``_goal_transitions``).
    """
    tenant, workspace = _new_tenant_and_workspace(
        "T5", name="W5", goals_enabled=True
    )
    _provision_goal_workflow(workspace)
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace.id), "title": "Goal to approve"},
        format="json",
    )
    create_req.auth_context = ctx
    created = GoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201
    goal_id = created.data["id"]
    assert created.data["status"] == "Entwurf"

    available_req = factory.get(f"/api/v1/goals/{goal_id}/transitions/")
    available_req.auth_context = ctx
    available_resp = GoalViewSet.as_view({"get": "transitions"})(
        available_req, pk=goal_id
    )
    assert available_resp.status_code == 200
    assert "Freigegeben" in [
        t["target_state"] for t in available_resp.data["allowed_transitions"]
    ]

    transition_req = factory.post(
        f"/api/v1/goals/{goal_id}/transitions/",
        {"target_state": "Freigegeben", "change_reason": "Reviewed and approved."},
        format="json",
    )
    transition_req.auth_context = ctx
    transition_resp = GoalViewSet.as_view({"post": "transitions"})(
        transition_req, pk=goal_id
    )
    assert transition_resp.status_code == 200
    assert transition_resp.data["new_state"] == "Freigegeben"

    retrieve_req = factory.get(f"/api/v1/goals/{goal_id}/")
    retrieve_req.auth_context = ctx
    retrieve_resp = GoalViewSet.as_view({"get": "retrieve"})(retrieve_req, pk=goal_id)
    assert retrieve_resp.data["status"] == "Freigegeben"


def test_goal_patch_returns_405_not_500():
    """Regression test for #235: PATCH /api/v1/goals/{id}/ crashed with an
    uncaught NotImplementedError (HTML 500) because GoalViewSet never
    overrode BaseEntityViewSet.partial_update(). It must now fail cleanly
    with a JSON 405 instead of crashing the server.
    """
    tenant, workspace = _new_tenant_and_workspace("T6", name="W6", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace.id), "title": "Goal to patch"},
        format="json",
    )
    create_req.auth_context = ctx
    created = GoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201
    goal_id = created.data["id"]

    patch_req = factory.patch(
        f"/api/v1/goals/{goal_id}/", {"title": "Renamed"}, format="json"
    )
    patch_req.auth_context = ctx
    patch_resp = GoalViewSet.as_view({"patch": "partial_update"})(patch_req, pk=goal_id)

    assert patch_resp.status_code == 405
    assert "error" in patch_resp.data


def test_goal_delete_returns_405_not_500():
    """Regression test for #235: DELETE /api/v1/goals/{id}/ crashed with an
    uncaught NotImplementedError (HTML 500) because GoalViewSet never
    overrode BaseEntityViewSet.destroy().
    """
    tenant, workspace = _new_tenant_and_workspace("T7", name="W7", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace.id), "title": "Goal to delete"},
        format="json",
    )
    create_req.auth_context = ctx
    created = GoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201
    goal_id = created.data["id"]

    delete_req = factory.delete(f"/api/v1/goals/{goal_id}/")
    delete_req.auth_context = ctx
    delete_resp = GoalViewSet.as_view({"delete": "destroy"})(delete_req, pk=goal_id)

    assert delete_resp.status_code == 405
    assert "error" in delete_resp.data


def _create_goal(factory, ctx, workspace_id, title, description=""):
    req = factory.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace_id), "title": title, "description": description},
        format="json",
    )
    req.auth_context = ctx
    resp = GoalViewSet.as_view({"post": "create"})(req)
    assert resp.status_code == 201
    return resp.data


def test_goal_list_search_filters_by_title_and_description():
    """Regression test for #236: ?search= was silently ignored."""
    tenant, workspace = _new_tenant_and_workspace("T8", name="W8", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    _create_goal(factory, ctx, workspace.id, "Reduce onboarding time")
    _create_goal(factory, ctx, workspace.id, "Improve support quality")

    list_req = factory.get(f"/api/v1/goals/?workspace_id={workspace.id}&search=onboarding")
    list_req.auth_context = ctx
    resp = GoalViewSet.as_view({"get": "list"})(list_req)

    assert resp.status_code == 200
    assert len(resp.data["results"]) == 1
    assert resp.data["results"][0]["title"] == "Reduce onboarding time"


def test_goal_list_ordering_by_title():
    """Regression test for #236: ?ordering= was silently ignored."""
    tenant, workspace = _new_tenant_and_workspace("T9", name="W9", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    _create_goal(factory, ctx, workspace.id, "Zebra goal")
    _create_goal(factory, ctx, workspace.id, "Apple goal")

    list_req = factory.get(f"/api/v1/goals/?workspace_id={workspace.id}&ordering=title")
    list_req.auth_context = ctx
    resp = GoalViewSet.as_view({"get": "list"})(list_req)

    assert resp.status_code == 200
    titles = [item["title"] for item in resp.data["results"]]
    assert titles == ["Apple goal", "Zebra goal"]


def test_goal_list_limit_caps_results():
    """Regression test for #236: ?limit= was silently ignored."""
    tenant, workspace = _new_tenant_and_workspace("T10", name="W10", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    _create_goal(factory, ctx, workspace.id, "Goal A")
    _create_goal(factory, ctx, workspace.id, "Goal B")

    list_req = factory.get(f"/api/v1/goals/?workspace_id={workspace.id}&limit=1")
    list_req.auth_context = ctx
    resp = GoalViewSet.as_view({"get": "list"})(list_req)

    assert resp.status_code == 200
    assert len(resp.data["results"]) == 1


def test_goal_list_negative_limit_returns_400():
    """Regression test for #236: ?limit=-1 must be rejected, not accepted."""
    tenant, workspace = _new_tenant_and_workspace("T11", name="W11", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    _create_goal(factory, ctx, workspace.id, "Goal A")

    list_req = factory.get(f"/api/v1/goals/?workspace_id={workspace.id}&limit=-1")
    list_req.auth_context = ctx
    resp = GoalViewSet.as_view({"get": "list"})(list_req)

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# #739: POST /api/v1/goals/{pk}/outdate/ and .../reactivate/ (REST parity
# with the MCP goal.delete / goal.reactivate tools; see
# mcp_server/tests/test_goal_query_delete.py for the MCP-side equivalents
# this mirrors).
# ---------------------------------------------------------------------------


def test_goal_outdate_archives_a_draft_goal():
    """Equivalent of MCP's test_goal_delete_archives_a_draft_goal."""
    tenant, workspace = _new_tenant_and_workspace(
        "T13", name="W13", goals_enabled=True
    )
    _provision_goal_workflow(workspace)
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()

    created = _create_goal(factory, ctx, workspace.id, "Goal to archive")
    assert created["status"] == "Entwurf"
    goal_id = created["id"]

    outdate_req = factory.post(f"/api/v1/goals/{goal_id}/outdate/", {}, format="json")
    outdate_req.auth_context = ctx
    outdate_resp = GoalViewSet.as_view({"post": "outdate"})(outdate_req, pk=goal_id)

    assert outdate_resp.status_code == 200
    assert outdate_resp.data["status"] == "Archiviert"
    assert outdate_resp.data["id"] == goal_id

    retrieve_req = factory.get(f"/api/v1/goals/{goal_id}/")
    retrieve_req.auth_context = ctx
    retrieve_resp = GoalViewSet.as_view({"get": "retrieve"})(retrieve_req, pk=goal_id)
    assert retrieve_resp.data["status"] == "Archiviert"


def test_goal_outdate_matches_mcp_goal_delete_outcome():
    """REST .../outdate/ and MCP goal.delete must reach the same end state.

    Drives one goal through each path in the same workspace and asserts both
    land on the identical status ("Archiviert") via the identical
    GoalService.archive() call — i.e. the two entry points are not diverging
    implementations of "archive a goal".
    """
    from mcp_server.tools.goals import GoalToolGroup

    tenant, workspace = _new_tenant_and_workspace(
        "T14", name="W14", goals_enabled=True
    )
    _provision_goal_workflow(workspace)
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()

    rest_goal = _create_goal(factory, ctx, workspace.id, "REST-archived goal")
    outdate_req = factory.post(
        f"/api/v1/goals/{rest_goal['id']}/outdate/", {}, format="json"
    )
    outdate_req.auth_context = ctx
    rest_resp = GoalViewSet.as_view({"post": "outdate"})(
        outdate_req, pk=rest_goal["id"]
    )
    assert rest_resp.status_code == 200

    group = GoalToolGroup()
    mcp_goal = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "MCP-archived goal"},
        auth_context=ctx,
        api_key="reqlo_testkey1234",
    )
    mcp_result = group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": mcp_goal.data["id"]},
        auth_context=ctx,
        api_key="reqlo_testkey1234",
    )
    assert mcp_result.success is True, mcp_result.message

    assert rest_resp.data["status"] == mcp_result.data["status"] == "Archiviert"


def test_goal_outdate_rejects_role_without_approver_permission():
    """Equivalent of MCP's test_goal_delete_rejects_role_without_approver_permission."""
    tenant, workspace = _new_tenant_and_workspace(
        "T15", name="W15", goals_enabled=True
    )
    _provision_goal_workflow(workspace)
    admin_ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    editor_ctx = _make_auth_context(tenant_id=tenant.id, roles=("editor",))
    factory = APIRequestFactory()

    created = _create_goal(factory, admin_ctx, workspace.id, "Goal A")

    outdate_req = factory.post(
        f"/api/v1/goals/{created['id']}/outdate/", {}, format="json"
    )
    outdate_req.auth_context = editor_ctx
    resp = GoalViewSet.as_view({"post": "outdate"})(outdate_req, pk=created["id"])

    assert resp.status_code == 403


def test_goal_outdate_unknown_id_returns_404():
    """Equivalent of MCP's test_goal_delete_unknown_id_returns_not_found."""
    tenant = Tenant.objects.create(name="T16")
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    missing_id = str(uuid.uuid4())
    outdate_req = factory.post(f"/api/v1/goals/{missing_id}/outdate/", {}, format="json")
    outdate_req.auth_context = ctx
    resp = GoalViewSet.as_view({"post": "outdate"})(outdate_req, pk=missing_id)

    assert resp.status_code == 404


def test_goal_reactivate_restores_an_archived_goal_to_draft():
    """A Goal archived via .../outdate/ can be restored via .../reactivate/.

    GoalService.restore() always resets to the workflow's initial state
    ("Entwurf"), mirroring MCP's goal.reactivate contract.
    """
    tenant, workspace = _new_tenant_and_workspace(
        "T17", name="W17", goals_enabled=True
    )
    _provision_goal_workflow(workspace)
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()

    created = _create_goal(factory, ctx, workspace.id, "Goal to restore")
    goal_id = created["id"]

    outdate_req = factory.post(f"/api/v1/goals/{goal_id}/outdate/", {}, format="json")
    outdate_req.auth_context = ctx
    outdate_resp = GoalViewSet.as_view({"post": "outdate"})(outdate_req, pk=goal_id)
    assert outdate_resp.status_code == 200
    assert outdate_resp.data["status"] == "Archiviert"

    reactivate_req = factory.post(
        f"/api/v1/goals/{goal_id}/reactivate/",
        {"change_reason": "Restore for rework."},
        format="json",
    )
    reactivate_req.auth_context = ctx
    reactivate_resp = GoalViewSet.as_view({"post": "reactivate"})(
        reactivate_req, pk=goal_id
    )

    assert reactivate_resp.status_code == 200
    assert reactivate_resp.data["status"] == "Entwurf"


def test_goal_list_status_filter():
    """Regression test for #236: ?status= was silently ignored.

    Every newly created Goal starts in "Entwurf", so filtering by an unused
    status value must return no results while filtering by "Entwurf" returns
    every goal.
    """
    tenant, workspace = _new_tenant_and_workspace("T12", name="W12", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    _create_goal(factory, ctx, workspace.id, "Goal A")

    matching_req = factory.get(f"/api/v1/goals/?workspace_id={workspace.id}&status=Entwurf")
    matching_req.auth_context = ctx
    matching_resp = GoalViewSet.as_view({"get": "list"})(matching_req)
    assert matching_resp.status_code == 200
    assert len(matching_resp.data["results"]) == 1

    non_matching_req = factory.get(
        f"/api/v1/goals/?workspace_id={workspace.id}&status=Freigegeben"
    )
    non_matching_req.auth_context = ctx
    non_matching_resp = GoalViewSet.as_view({"get": "list"})(non_matching_req)
    assert non_matching_resp.status_code == 200
    assert len(non_matching_resp.data["results"]) == 0
