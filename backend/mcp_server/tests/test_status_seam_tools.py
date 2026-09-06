"""MCP payloads carry the engine state, not a dropped mirror column.

Datenmodell-Konsolidierung Phase 1.
"""
from __future__ import annotations

import json
import pathlib
import uuid
from unittest.mock import patch

import pytest

MCP_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The exact bug pattern this task removes from each file: a `"status"` wire
# key built directly from the workflow-tracked entity's own (still-present,
# Phase 0 mirror) ORM attribute instead of the workflow-engine seam
# (`resolve_engine_status`). Scoped per file/variable rather than a blanket
# `\w+\.status` scan, because some files legitimately carry *other*,
# out-of-scope "status" keys on the same line shape:
#   - tools/tests.py also serialises TestRun/TestResult ("tr"/"r"), whose
#     lifecycle is owned by test_runs, not the workflow engine (not in the
#     Interfaces item-type list) -- those `.status` reads are correct as-is.
#   - tools/needs.py's `n.status` is a deliberate exception, not an
#     oversight: StakeholderNeedService.get()/.list_by_workspace()/.create()/
#     .update() already return a StakeholderNeedDTO whose `.status` is
#     resolved from the engine at the service layer
#     (application/stakeholder_need_service.py) -- reading it here reads an
#     already-resolved DTO field, not a raw ORM column.
_FORBIDDEN_STATUS_READS = {
    "tools/requirements.py": ['"status": req.status,'],
    "tools/goals.py": ['"status": goal.status,', '"status": main_goal.status,'],
    "tools/tests.py": ['"status": tc.status,'],
    "tools/interview.py": ['"status": session.status,'],
}


@pytest.mark.parametrize(
    "relpath",
    sorted(_FORBIDDEN_STATUS_READS),
)
def test_no_raw_status_column_read_onto_wire(relpath: str) -> None:
    text = (MCP_ROOT / relpath).read_text(encoding="utf-8")
    for forbidden in _FORBIDDEN_STATUS_READS[relpath]:
        assert forbidden not in text, f"{relpath}: found raw status read {forbidden!r}"


def test_generic_to_dict_resolves_status_via_engine_seam() -> None:
    """generic.py builds its dict dynamically (obj.__dict__), so there is no
    literal `"status": obj.status` line to grep for -- assert the resolution
    call is present instead."""
    text = (MCP_ROOT / "tools/generic.py").read_text(encoding="utf-8")
    assert "resolve_engine_status(" in text
    assert 'data["status"] = obj.status' not in text


# ---------------------------------------------------------------------------
# resolve_engine_status -- unit tests (mirrors the mock-based coverage of the
# equivalent REST seam in rest_api/tests/test_workflow_state_mixin.py).
# ---------------------------------------------------------------------------


class TestResolveEngineStatus:
    def test_resolves_from_engine_when_tracked(self) -> None:
        from mcp_server.tools.base import resolve_engine_status

        item_id = uuid.uuid4()
        with patch(
            "mcp_server.tools.base.state_reader.current_state",
            return_value="approved",
        ):
            assert resolve_engine_status("Requirement", item_id, "draft") == "approved"

    def test_falls_back_to_column_when_untracked(self) -> None:
        from mcp_server.tools.base import resolve_engine_status

        item_id = uuid.uuid4()
        with patch(
            "mcp_server.tools.base.state_reader.current_state",
            return_value=None,
        ):
            assert resolve_engine_status("Goal", item_id, "Entwurf") == "Entwurf"

    def test_batched_status_map_skips_per_item_query(self) -> None:
        from mcp_server.tools.base import resolve_engine_status

        item_id = uuid.uuid4()
        with patch("mcp_server.tools.base.state_reader.current_state") as spy:
            result = resolve_engine_status(
                "Requirement", item_id, "draft", status_map={str(item_id): "approved"}
            )
        assert result == "approved"
        spy.assert_not_called()

    def test_batched_status_map_falls_back_when_item_absent(self) -> None:
        from mcp_server.tools.base import resolve_engine_status

        item_id = uuid.uuid4()
        assert (
            resolve_engine_status("Requirement", item_id, "draft", status_map={}) == "draft"
        )

    def test_falls_back_when_no_tenant_context_is_active(self) -> None:
        """Production dispatch (ToolRegistry.dispatch_request) always sets a
        TenantContext before a handler runs; the only caller that can hit
        this branch is a unit test invoking execute_tool() directly against
        a mocked service. Must degrade to the column value, not blow up."""
        from mcp_server.tools.base import resolve_engine_status
        from persistence.tenancy import TenantContextNotSetError

        item_id = uuid.uuid4()
        with patch(
            "mcp_server.tools.base.state_reader.current_state",
            side_effect=TenantContextNotSetError("no tenant"),
        ):
            assert resolve_engine_status("Requirement", item_id, "draft") == "draft"


class TestResolveStatusMap:
    def test_returns_empty_mapping_when_no_tenant_context_is_active(self) -> None:
        from mcp_server.tools.base import resolve_status_map
        from persistence.tenancy import TenantContextNotSetError

        with patch(
            "mcp_server.tools.base.state_reader.current_states",
            side_effect=TenantContextNotSetError("no tenant"),
        ):
            assert resolve_status_map("Requirement", [uuid.uuid4()]) == {}

    def test_delegates_to_state_reader_when_tracked(self) -> None:
        from mcp_server.tools.base import resolve_status_map

        item_id = uuid.uuid4()
        with patch(
            "mcp_server.tools.base.state_reader.current_states",
            return_value={str(item_id): "approved"},
        ) as spy:
            result = resolve_status_map("Requirement", [item_id])

        assert result == {str(item_id): "approved"}
        spy.assert_called_once()


# ---------------------------------------------------------------------------
# End-to-end: requirement.get / requirement.query through the real service +
# real WorkflowItemState (same fixture shape as
# application/tests/test_requirement_status_seam.py).
# ---------------------------------------------------------------------------


@pytest.fixture
def requirement_tool_env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-mcp-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-mcp-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        preset="standard",
        workflow_json={"states": ["draft", "approved"], "transitions": []},
    )
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="REQ",
        description="d",
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=req.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        definition=definition,
        current_state="approved",
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )
    return ctx, definition, workspace, req


@pytest.mark.django_db
def test_requirement_get_payload_is_json_serialisable_and_uses_engine_status(
    requirement_tool_env,
):
    from mcp_server.tools.requirements import RequirementsToolGroup

    ctx, _definition, _workspace, req = requirement_tool_env
    result = RequirementsToolGroup().execute_tool(
        tool_name="requirement.get",
        params={"id": str(req.id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )

    assert result.success is True
    payload = result.data
    assert "content" not in payload
    # Task 12: the mirror column is dropped -- the fixture's WorkflowItemState
    # says "approved" and the response must reflect that (there is no column
    # left for it to compete with).
    assert payload["requirement"]["status"] == "approved"
    json.dumps(payload)


@pytest.mark.django_db
def test_requirement_get_falls_back_when_untracked(requirement_tool_env):
    """No WorkflowItemState row for this item -> the "draft" preset initial
    state, never an empty string. Task 12: the `status` column is dropped, so
    it can no longer report a legacy value (documented, reviewed data-loss
    tradeoff, see the Task 12 report Finding 2)."""
    from mcp_server.tools.requirements import RequirementsToolGroup
    from persistence.models import Artifact, Requirement
    from workflow.models import WorkflowItemState

    ctx, _definition, workspace, _req = requirement_tool_env
    untracked_artifact = Artifact.objects.create(
        tenant=workspace.tenant, workspace=workspace, artifact_type="Requirement"
    )
    untracked = Requirement.objects.create(
        tenant=workspace.tenant,
        artifact=untracked_artifact,
        workspace=workspace,
        title="Untracked",
        description="d",
    )
    assert not WorkflowItemState.objects.filter(item_id=untracked.id).exists()

    result = RequirementsToolGroup().execute_tool(
        tool_name="requirement.get",
        params={"id": str(untracked.id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )

    assert result.success is True
    assert result.data["requirement"]["status"] == "draft"


@pytest.mark.django_db
def test_requirement_query_batches_status_lookup_for_list(requirement_tool_env):
    """N+1 guard: requirement.query must resolve every row's status with a
    single ``state_reader.current_states`` call, not one per row (mirrors
    the REST list N+1 fix, rest_api/mixins/workflow_state.py)."""
    from mcp_server.tools.requirements import RequirementsToolGroup
    from persistence.models import Artifact, Requirement
    from workflow import state_reader
    from workflow.models import WorkflowItemState

    ctx, definition, workspace, _req = requirement_tool_env
    for i in range(3):
        artifact = Artifact.objects.create(
            tenant=workspace.tenant, workspace=workspace, artifact_type="Requirement"
        )
        extra = Requirement.objects.create(
            tenant=workspace.tenant,
            artifact=artifact,
            workspace=workspace,
            title=f"REQ {i}",
            description="d",
        )
        WorkflowItemState.objects.create(
            tenant=workspace.tenant,
            item_id=extra.id,
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state="approved",
        )

    with patch(
        "mcp_server.tools.base.state_reader.current_states",
        wraps=state_reader.current_states,
    ) as spy:
        result = RequirementsToolGroup().execute_tool(
            tool_name="requirement.query",
            params={"workspace_id": str(workspace.id)},
            auth_context=ctx,
            api_key="reqlo_test",
        )

    assert result.success is True
    assert result.data["count"] == 4  # fixture's req + the 3 created here
    assert all(r["status"] == "approved" for r in result.data["requirements"])
    assert spy.call_count == 1
    json.dumps(result.data)


# ---------------------------------------------------------------------------
# Coordinator review follow-up: goal.list_versions / main_goal.list_versions
# (GoalService.list_versions / MainGoalService.list_versions, application/
# layer) and interview.start / interview.get_state / interview.answer for
# single-kind sessions (InterviewService.get_state, application/ layer) were
# still building "status" from the raw ORM column -- outside this task's
# mcp_server/-scoped grep because the wire-shaping happens one layer down.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_goal_list_versions_uses_engine_status_not_frozen_column():
    """A version whose engine state has moved past what its own `status`
    column says must report the engine value -- proves list_versions() does
    not just echo the mirror column."""
    from application.goal_service import GoalService
    from application.models import Goal
    from auth_tenancy.context import AuthContext, AuthMethod
    from mcp_server.tools.goals import GoalToolGroup
    from persistence.models import Artifact, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-goal-versions-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-goal-versions-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Goal",
        preset="standard",
        workflow_json={"states": ["Entwurf", "Freigegeben"], "transitions": []},
    )
    artifact = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Goal")
    goal = Goal.objects.create(
        artifact=artifact,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        title="G1",
        description="d",
        lineage_id=uuid.uuid4(),
        sequence_number=1,
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=goal.id,
        item_type="Goal",
        workspace_id=workspace.id,
        definition=definition,
        current_state="Freigegeben",  # the engine has moved on
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )

    service_versions = GoalService().list_versions(goal.lineage_id, ctx)
    assert service_versions[0]["status"] == "Freigegeben"

    result = GoalToolGroup().execute_tool(
        tool_name="goal.list_versions",
        params={"lineage_id": str(goal.lineage_id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )
    assert result.success is True
    assert result.data["versions"][0]["status"] == "Freigegeben"
    json.dumps(result.data)


@pytest.mark.django_db
def test_main_goal_list_versions_uses_engine_status_not_frozen_column():
    from application.main_goal_service import MainGoalService
    from application.models import MainGoal
    from auth_tenancy.context import AuthContext, AuthMethod
    from mcp_server.tools.goals import MainGoalToolGroup
    from persistence.models import Artifact, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-main-goal-versions-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-main-goal-versions-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="MainGoal",
        preset="standard",
        workflow_json={"states": ["Entwurf", "Freigegeben"], "transitions": []},
    )
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="MainGoal"
    )
    main_goal = MainGoal.objects.create(
        artifact=artifact,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        sequence_number=1,
        content="c",
        source="manual",
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=main_goal.id,
        item_type="MainGoal",
        workspace_id=workspace.id,
        definition=definition,
        current_state="Freigegeben",
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )

    service_versions = MainGoalService().list_versions(workspace.id, ctx)
    assert service_versions[0]["status"] == "Freigegeben"

    result = MainGoalToolGroup().execute_tool(
        tool_name="main_goal.list_versions",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )
    assert result.success is True
    assert result.data["versions"][0]["status"] == "Freigegeben"
    json.dumps(result.data)


@pytest.mark.django_db
def test_interview_get_state_uses_engine_status_for_single_kind_session():
    """interview.get_state / interview.answer (and interview.start, which
    returns get_state()'s dict last in its merge) all go through
    InterviewService.get_state() -- fixing it there is the root-cause fix
    for all three MCP tools at once."""
    from application.interview_service import InterviewService
    from auth_tenancy.context import AuthContext, AuthMethod
    from mcp_server.tools.interview import InterviewToolGroup
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-interview-versions-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-interview-versions-seam")
    # A real WorkflowEngineDefinition so InterviewService.start()'s
    # initialize_workflow_states() actually seeds a WorkflowItemState row
    # (absent one, it is a documented silent no-op -- see GoalService.create_version).
    WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Interview",
        preset="standard",
        workflow_json={
            "states": ["in_progress", "completed", "abandoned"],
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

    from workflow import state_reader

    session = InterviewService().start(ctx, "Requirement", workspace.id)
    # Sanity: the fixture's WorkflowEngineDefinition let initialize_workflow_states()
    # seed a real WorkflowItemState (Task 12: the `status` column is dropped,
    # so this is the only place "in_progress" can live now).
    assert state_reader.current_state("Interview", session.id) == "in_progress"

    # Move the engine's state ahead of the mirror column without going
    # through a real transition -- proves get_state() reads the engine, not
    # the frozen column, independent of whatever wrote it there.
    state_row = WorkflowItemState.objects.get(item_id=session.id, item_type="Interview")
    state_row.current_state = "completed"
    state_row.save(update_fields=["current_state"])

    service_state = InterviewService().get_state(ctx, session.id)
    assert service_state["status"] == "completed"

    result = InterviewToolGroup().execute_tool(
        tool_name="interview.get_state",
        params={"session_id": str(session.id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )
    assert result.success is True
    assert result.data["status"] == "completed"
    json.dumps(result.data)
