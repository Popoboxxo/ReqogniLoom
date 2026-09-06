"""Every artifact serializer resolves `status` from the workflow engine.

Datenmodell-Konsolidierung Phase 0 / Milestone M0.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from application.adr_service import AdrService
from application.goal_service import DRAFT_STATE, GoalService
from application.models import Goal
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from rest_api import serializers as api_serializers
from rest_api.mixins.workflow_state import WorkflowStateSerializerMixin
from rest_api.views import AdrViewSet, _goal_to_dict
from workflow.services import create_default_workflow

EXPECTED_ITEM_TYPES = {
    "RequirementSerializer": "Requirement",
    "StakeholderNeedSerializer": "StakeholderNeed",
    "TestCaseSerializer": "TestCase",
    "AdrSerializer": "Adr",
    "RiskSerializer": "Risk",
    "IssueSerializer": "Issue",
    "ChangeRequestSerializer": "ChangeRequest",
    "GoalSerializer": "Goal",
    "MainGoalSerializer": "MainGoal",
}


@pytest.mark.parametrize("name,item_type", sorted(EXPECTED_ITEM_TYPES.items()))
def test_serializer_uses_the_engine_seam(name, item_type):
    cls = getattr(api_serializers, name)
    assert issubclass(cls, WorkflowStateSerializerMixin), f"{name} must use the mixin"
    assert cls.workflow_item_type == item_type


@pytest.mark.parametrize("name", sorted(EXPECTED_ITEM_TYPES))
def test_status_is_read_only(name):
    cls = getattr(api_serializers, name)
    field = cls().fields["status"]
    assert isinstance(field, serializers.SerializerMethodField)
    assert field.read_only is True


@pytest.mark.django_db
def test_untracked_goal_falls_back_to_its_own_status_column():
    """D-1 / Phase 0 must be value-neutral: Goal has no WorkflowItemState
    backfill at all (workflow/migrations/0005 covers only Adr/Risk/Issue/
    ChangeRequest/TestCase), so a freshly created Goal has no engine row —
    the response must still show the real column value, not "".
    """
    tenant = Tenant.objects.create(name="T-untracked-goal")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="W-untracked-goal", goals_enabled=True
        )
        ctx = MagicMock(tenant_id=tenant.id, user_id=uuid.uuid4(), active_roles=("editor",))
        ctx.has_role = lambda role: role in ctx.active_roles

        result = GoalService().create_version(
            workspace_id=workspace.id, title="Untracked goal", ctx=ctx
        )
        assert result["status"] == DRAFT_STATE  # sanity: the column itself is set

        # No WorkflowEngineDefinition was ever provisioned for "Goal" in this
        # workspace, so initialize_workflow_states() was a silent no-op above
        # — the serializer must still report DRAFT_STATE via the fallback,
        # not "". Uses the real REST call shape (_goal_to_dict), same as
        # GoalViewSet.
        goal = Goal.objects.get(id=result["id"])
        data = api_serializers.GoalSerializer(_goal_to_dict(goal)).data
        assert data["status"] == DRAFT_STATE
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_list_endpoint_resolves_status_in_one_query():
    """No list endpoint for any of the nine types calls its serializer with
    ``many=True`` — they go through ``_paginate(..., serialize_page=...)``
    (Task 3 fix-round), which batches the whole page into one serializer
    instance instead of building a fresh one per row via a per-item lambda.
    Without that, WorkflowStateSerializerMixin's per-instance status cache
    never survives past one row and every row pays its own
    ``WorkflowItemState`` query (N+1). Adr picked as the representative case
    (any of the nine wired the same way would do)."""
    tenant = Tenant.objects.create(name="T-list-n-plus-1")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="W-list-n-plus-1")
        create_default_workflow(
            workspace_id=workspace.id,
            preset="adr_default",
            item_type="Adr",
            tenant_id=tenant.id,
        )
        ctx = MagicMock(tenant_id=tenant.id, user_id=uuid.uuid4(), active_roles=("editor",))
        ctx.has_role = lambda role: role in ctx.active_roles
        svc = AdrService()
        for i in range(3):
            svc.create_adr(
                workspace_id=workspace.id, title=f"ADR {i}", description="", ctx=ctx
            )

        req = APIRequestFactory().get(f"/api/v1/adrs/?workspace_id={workspace.id}")
        req.auth_context = ctx
        view = AdrViewSet.as_view({"get": "list"})

        from workflow import state_reader

        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            wraps=state_reader.current_states,
        ) as spy:
            resp = view(req)

        assert resp.status_code == 200
        assert len(resp.data["results"]) == 3
        assert spy.call_count == 1, "status resolution must batch, not N+1"
    finally:
        TenantContext.clear_tenant()
