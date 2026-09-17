"""
Tests for MainGoalViewSet REST endpoints (REQ-L2-TE-020, Task 6).

Covers:
  GET  /api/v1/main-goals/?workspace_id=<id>
  POST /api/v1/main-goals/
  POST /api/v1/main-goals/{pk}/approve/
  GET  /api/v1/main-goals/current/?workspace_id=<id>
  GET  /api/v1/main-goals/{pk}/versions/

Uses DRF APIRequestFactory with a real AuthContext attached to the request
and real DB fixtures (django_db) — no service mocking — mirroring the
pattern used elsewhere in this test suite (e.g.
rest_api/tests/test_needs_routing.py, rest_api/tests/test_change_request_api.py).
There is no ``auth_client_factory`` fixture in this codebase.

``approve`` requires a real WorkflowEngineDefinition (main_goal_default
preset) to be provisioned for the workspace/item_type, mirroring
application/tests/test_main_goal_service.py's
``_provision_main_goal_workflow`` helper, and an ``approver``/``admin`` role
per workflow/definition_store.py's ``_goal_transitions`` (Entwurf ->
Freigegeben is gated to ``["approver", "admin"]`` with
``requires_change_reason=True``) — the brief's sample test approved with
the same "editor" role used for creation, which the real WorkflowEngine
role gate would reject; verified against the real preset definition instead
of assumed.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from rest_api.views import MainGoalViewSet

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


def _provision_main_goal_workflow(workspace):
    """Create a real WorkflowEngineDefinition for MainGoal on *workspace*.

    Mirrors application/tests/test_main_goal_service.py's
    ``_provision_main_goal_workflow``: ad-hoc test workspaces bypass
    ``workspace_provisioning.provision_workspace_defaults`` (which does not
    include Goal/MainGoal), so ``approve``'s WorkflowEngine call would
    otherwise have no WorkflowItemState to transition.
    """
    from persistence.tenancy import TenantContext
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="main_goal_default",
            item_type="MainGoal",
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


def test_create_manual_and_approve_main_goal():
    tenant, workspace = _new_tenant_and_workspace("T1", name="W1", goals_enabled=True)
    _provision_main_goal_workflow(workspace)
    ctx = _make_auth_context(tenant_id=tenant.id, roles=("admin",))
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Manually authored."},
        format="json",
    )
    create_req.auth_context = ctx
    create_resp = MainGoalViewSet.as_view({"post": "create"})(create_req)

    assert create_resp.status_code == 201
    main_goal_id = create_resp.data["id"]

    approve_req = factory.post(
        f"/api/v1/main-goals/{main_goal_id}/approve/",
        {"change_reason": "Reviewed and approved."},
        format="json",
    )
    approve_req.auth_context = ctx
    approve_resp = MainGoalViewSet.as_view({"post": "approve"})(approve_req, pk=main_goal_id)

    assert approve_resp.status_code == 200
    assert approve_resp.data["status"] == "Freigegeben"
    # The approve response must be a FULLY serialized MainGoal, not the
    # service's bare {id, sequence_number, status} dict: MainGoalPanel replaces
    # its panel state with it and rendered an empty panel when `content` was
    # missing (fix round, finding C2).
    assert approve_resp.data["id"] == main_goal_id
    assert approve_resp.data["content"] == "Manually authored."
    assert approve_resp.data["source"] == "manual"
    assert approve_resp.data["workspace_id"] == str(workspace.id)

    current_req = factory.get(f"/api/v1/main-goals/current/?workspace_id={workspace.id}")
    current_req.auth_context = ctx
    current_resp = MainGoalViewSet.as_view({"get": "current"})(current_req)

    assert current_resp.status_code == 200
    assert current_resp.data["id"] == main_goal_id


def test_create_manual_requires_goals_enabled():
    tenant, workspace = _new_tenant_and_workspace("T2", name="W2", goals_enabled=False)
    ctx = _make_auth_context(tenant_id=tenant.id)

    factory = APIRequestFactory()
    req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft."},
        format="json",
    )
    req.auth_context = ctx
    resp = MainGoalViewSet.as_view({"post": "create"})(req)

    # Feature-gate/authorization concern → 403, not a 400 validation error
    # (#271 item 4: PermissionDeniedError instead of ValidationError).
    assert resp.status_code == 403


def test_approve_rejects_editor_role():
    """Entwurf -> Freigegeben is gated to approver/admin; editor must be rejected."""
    tenant, workspace = _new_tenant_and_workspace("T3", name="W3", goals_enabled=True)
    _provision_main_goal_workflow(workspace)
    editor_ctx = _make_auth_context(tenant_id=tenant.id, roles=("editor",))
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft."},
        format="json",
    )
    create_req.auth_context = editor_ctx
    create_resp = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert create_resp.status_code == 201
    main_goal_id = create_resp.data["id"]

    approve_req = factory.post(
        f"/api/v1/main-goals/{main_goal_id}/approve/",
        {"change_reason": "Trying without approver role."},
        format="json",
    )
    approve_req.auth_context = editor_ctx
    approve_resp = MainGoalViewSet.as_view({"post": "approve"})(approve_req, pk=main_goal_id)

    # GitHub Issue #214 fix: WorkflowFacade._remap_workflow_exc now correctly
    # compares exc.error_code against the actual EC_ROLE_NOT_ALLOWED constant.
    # Role-based rejections now properly map to 403 PermissionDenied.
    assert approve_resp.status_code == 403


def test_current_returns_none_when_never_approved():
    tenant, workspace = _new_tenant_and_workspace("T4", name="W4", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    req = factory.get(f"/api/v1/main-goals/current/?workspace_id={workspace.id}")
    req.auth_context = ctx
    resp = MainGoalViewSet.as_view({"get": "current"})(req)

    assert resp.status_code == 200
    assert resp.data is None


def test_main_goal_versions_endpoint():
    tenant, workspace = _new_tenant_and_workspace("T5", name="W5", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft v1."},
        format="json",
    )
    create_req.auth_context = ctx
    created = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201

    versions_req = factory.get(f"/api/v1/main-goals/{created.data['id']}/versions/")
    versions_req.auth_context = ctx
    versions_resp = MainGoalViewSet.as_view({"get": "versions"})(
        versions_req, pk=created.data["id"]
    )

    assert versions_resp.status_code == 200
    assert len(versions_resp.data) == 1
    assert versions_resp.data[0]["sequence_number"] == 1


def test_list_main_goals_returns_all_versions_for_workspace():
    """GET /api/v1/main-goals/?workspace_id=<id> — regression test for reviewer
    finding C1: MainGoalViewSet previously had no ``list()`` override and
    inherited BaseEntityViewSet's ``raise NotImplementedError`` stub, causing
    an unhandled 500 for this route (Task 6 fix round 1).
    """
    tenant, workspace = _new_tenant_and_workspace("T6", name="W6", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft v1."},
        format="json",
    )
    create_req.auth_context = ctx
    created = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201

    list_req = factory.get(f"/api/v1/main-goals/?workspace_id={workspace.id}")
    list_req.auth_context = ctx
    list_resp = MainGoalViewSet.as_view({"get": "list"})(list_req)

    assert list_resp.status_code == 200
    results = list_resp.data["results"]
    assert len(results) == 1
    assert results[0]["id"] == created.data["id"]
    assert results[0]["content"] == "Draft v1."
    assert results[0]["workspace_id"] == str(workspace.id)


def test_list_main_goals_requires_workspace_id():
    tenant, _workspace = _new_tenant_and_workspace("T7", name="W7", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    req = factory.get("/api/v1/main-goals/")
    req.auth_context = ctx
    resp = MainGoalViewSet.as_view({"get": "list"})(req)

    assert resp.status_code == 400


def test_main_goal_retrieve_returns_detail_not_500():
    """GET /api/v1/main-goals/{pk}/ — regression test for #235:
    MainGoalViewSet had no ``retrieve()`` override and inherited
    BaseEntityViewSet's ``raise NotImplementedError`` stub, uncaught by the
    except-blocks elsewhere in this file, causing an HTML 500 crash instead
    of the expected detail payload.
    """
    tenant, workspace = _new_tenant_and_workspace("T8", name="W8", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft to retrieve."},
        format="json",
    )
    create_req.auth_context = ctx
    created = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201
    main_goal_id = created.data["id"]

    retrieve_req = factory.get(f"/api/v1/main-goals/{main_goal_id}/")
    retrieve_req.auth_context = ctx
    retrieve_resp = MainGoalViewSet.as_view({"get": "retrieve"})(retrieve_req, pk=main_goal_id)

    assert retrieve_resp.status_code == 200
    assert retrieve_resp.data["id"] == main_goal_id
    assert retrieve_resp.data["content"] == "Draft to retrieve."


def test_main_goal_patch_returns_405_not_500():
    """PATCH /api/v1/main-goals/{pk}/ — regression test for #235:
    MainGoalViewSet inherited BaseEntityViewSet.partial_update()'s
    ``raise NotImplementedError`` stub. It must now fail cleanly with a
    JSON 405 instead of crashing the server.
    """
    tenant, workspace = _new_tenant_and_workspace("T9", name="W9", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft to patch."},
        format="json",
    )
    create_req.auth_context = ctx
    created = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201
    main_goal_id = created.data["id"]

    patch_req = factory.patch(
        f"/api/v1/main-goals/{main_goal_id}/", {"content": "Renamed"}, format="json"
    )
    patch_req.auth_context = ctx
    patch_resp = MainGoalViewSet.as_view({"patch": "partial_update"})(
        patch_req, pk=main_goal_id
    )

    assert patch_resp.status_code == 405
    assert "error" in patch_resp.data


def test_main_goal_delete_returns_405_not_500():
    """DELETE /api/v1/main-goals/{pk}/ — regression test for #235:
    MainGoalViewSet inherited BaseEntityViewSet.destroy()'s
    ``raise NotImplementedError`` stub.
    """
    tenant, workspace = _new_tenant_and_workspace("T10", name="W10", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Draft to delete."},
        format="json",
    )
    create_req.auth_context = ctx
    created = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201
    main_goal_id = created.data["id"]

    delete_req = factory.delete(f"/api/v1/main-goals/{main_goal_id}/")
    delete_req.auth_context = ctx
    delete_resp = MainGoalViewSet.as_view({"delete": "destroy"})(delete_req, pk=main_goal_id)

    assert delete_resp.status_code == 405
    assert "error" in delete_resp.data


def test_main_goal_list_source_filter():
    """Regression test for #236: ?source= was silently ignored.

    Seeds one "manual" MainGoal (via the real create_manual write path) and
    one "ai" MainGoal (via MainGoalService._create_row, mirroring what
    generate_ai persists) and asserts ?source=ai/?source=manual each return
    only the matching row.
    """
    from application.main_goal_service import MainGoalService

    tenant, workspace = _new_tenant_and_workspace("T11", name="W11", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    create_req = factory.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "Manually authored."},
        format="json",
    )
    create_req.auth_context = ctx
    created = MainGoalViewSet.as_view({"post": "create"})(create_req)
    assert created.status_code == 201

    svc = MainGoalService()
    tenant_obj, workspace_obj = svc._resolve_tenant_and_workspace(workspace.id, ctx)
    svc._create_row(
        workspace=workspace_obj,
        tenant=tenant_obj,
        content="AI-aggregated content.",
        source="ai",
        generated_from_goal_ids=[],
        ctx=ctx,
    )

    ai_req = factory.get(f"/api/v1/main-goals/?workspace_id={workspace.id}&source=ai")
    ai_req.auth_context = ctx
    ai_resp = MainGoalViewSet.as_view({"get": "list"})(ai_req)
    assert ai_resp.status_code == 200
    assert len(ai_resp.data["results"]) == 1
    assert ai_resp.data["results"][0]["source"] == "ai"

    manual_req = factory.get(
        f"/api/v1/main-goals/?workspace_id={workspace.id}&source=manual"
    )
    manual_req.auth_context = ctx
    manual_resp = MainGoalViewSet.as_view({"get": "list"})(manual_req)
    assert manual_resp.status_code == 200
    assert len(manual_resp.data["results"]) == 1
    assert manual_resp.data["results"][0]["source"] == "manual"


def test_main_goal_list_limit_and_negative_limit():
    """Regression test for #236: ?limit= must cap results; negative rejected."""
    tenant, workspace = _new_tenant_and_workspace("T12", name="W12", goals_enabled=True)
    ctx = _make_auth_context(tenant_id=tenant.id)
    factory = APIRequestFactory()

    for content in ("Draft one.", "Draft two."):
        req = factory.post(
            "/api/v1/main-goals/",
            {"workspace_id": str(workspace.id), "content": content},
            format="json",
        )
        req.auth_context = ctx
        resp = MainGoalViewSet.as_view({"post": "create"})(req)
        assert resp.status_code == 201

    limited_req = factory.get(f"/api/v1/main-goals/?workspace_id={workspace.id}&limit=1")
    limited_req.auth_context = ctx
    limited_resp = MainGoalViewSet.as_view({"get": "list"})(limited_req)
    assert limited_resp.status_code == 200
    assert len(limited_resp.data["results"]) == 1

    negative_req = factory.get(f"/api/v1/main-goals/?workspace_id={workspace.id}&limit=-1")
    negative_req.auth_context = ctx
    negative_resp = MainGoalViewSet.as_view({"get": "list"})(negative_req)
    assert negative_resp.status_code == 400
