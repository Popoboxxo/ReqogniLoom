"""Goal/MainGoal effective-version selection runs off the workflow engine.

Datenmodell-Konsolidierung Phase 1. The German state names (Entwurf /
Freigegeben / Archiviert) are the goal_default preset's declared states and are
deliberately unchanged.
"""
import inspect
import uuid

import pytest

from application import goal_service, main_goal_service


@pytest.fixture
def goal_env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition

    tenant = Tenant.objects.create(name="t-goal-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-goal-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Goal",
        preset="standard",
        workflow_json={
            "states": ["Entwurf", "Freigegeben", "Archiviert"],
            "transitions": [],
        },
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )
    return tenant, workspace, definition, ctx


def make_goal(env, lineage_id, sequence_number, state):
    from persistence.models import Artifact
    from workflow.models import WorkflowItemState

    from application.models import Goal

    tenant, workspace, definition, _ctx = env
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Goal"
    )
    goal = Goal.objects.create(
        artifact=artifact,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        title=f"G{sequence_number}",
        description="d",
        lineage_id=lineage_id,
        sequence_number=sequence_number,
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=goal.id,
        item_type="Goal",
        workspace_id=workspace.id,
        definition=definition,
        current_state=state,
    )
    return goal.id


def test_goal_service_has_no_status_column_filter():
    source = inspect.getsource(goal_service)
    assert "status=APPROVED_STATE" not in source
    assert "status=ARCHIVED_STATE" not in source
    assert "from workflow import state_reader" in source


def test_main_goal_service_has_no_status_column_filter():
    source = inspect.getsource(main_goal_service)
    assert 'status="Entwurf"' not in source
    assert 'status="Freigegeben"' not in source
    assert "from workflow import state_reader" in source


@pytest.mark.django_db
class TestListEffective:
    def test_only_approved_lineage_head_is_effective(self, goal_env):
        from application.goal_service import GoalService

        _tenant, workspace, _definition, ctx = goal_env
        lineage = uuid.uuid4()
        approved_id = make_goal(goal_env, lineage, 1, "Freigegeben")
        make_goal(goal_env, lineage, 2, "Entwurf")

        result = GoalService().list_effective(workspace.id, ctx)

        assert [g.id for g in result] == [approved_id]

    def test_never_approved_lineage_contributes_nothing(self, goal_env):
        from application.goal_service import GoalService

        _tenant, workspace, _definition, ctx = goal_env
        make_goal(goal_env, uuid.uuid4(), 1, "Entwurf")

        assert GoalService().list_effective(workspace.id, ctx) == []
