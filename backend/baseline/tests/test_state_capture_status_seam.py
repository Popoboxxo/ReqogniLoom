"""Baseline snapshots capture the engine state, not a mirror column.

Datenmodell-Konsolidierung Phase 1. A missed reader here silently freezes a
stale status into an immutable baseline, so this is asserted structurally as
well as behaviourally.
"""
from __future__ import annotations

import inspect
import uuid
from collections import Counter
from unittest.mock import MagicMock, patch

import pytest

from baseline import state_capture
from baseline.types import DeltaIndexTuple
from workflow import state_reader


def test_no_entity_status_attribute_read_remains():
    source = inspect.getsource(state_capture)
    for expr in (
        '"status": req.status',
        '"status": sn.status',
        '"status": tc.status',
        '"status": adr.status',
        '"status": risk.status',
        '"status": issue.status',
        '"status": goal.status',
        '"status": mg.status',
    ):
        assert expr not in source, f"{expr} still reads the dropped column"


def test_test_run_status_is_untouched():
    source = inspect.getsource(state_capture)
    assert '"status": tr.status' in source
    assert '"status": trr.status' in source


@pytest.fixture
def capture_fixture(db):
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-capture-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-capture-seam")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    # Task 12: `status` column dropped -- the WorkflowItemState created below
    # is what actually determines this Requirement's captured status.
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="REQ",
        description="d",
    )
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        preset="standard",
        workflow_json={"states": ["draft", "approved"], "transitions": []},
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=req.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        definition=definition,
        current_state="approved",
    )
    return tenant.id, artifact.id, req.id


@pytest.mark.django_db
def test_requirement_snapshot_carries_the_engine_state(capture_fixture):
    tenant_id, artifact_id, req_id = capture_fixture

    states = state_capture.capture_states(
        [DeltaIndexTuple(item_id=str(artifact_id), version=1)], tenant_id=tenant_id
    )

    assert states[str(artifact_id)]["status"] == "approved"


@pytest.mark.django_db
def test_untracked_requirement_falls_back_to_the_initial_state(db):
    """No WorkflowItemState row for the item -> the type's initial state wins.

    Task 12: the ``status`` column this used to fall back to is dropped, so
    an untracked row can no longer report a frozen legacy value -- it is
    captured at ``state_reader.initial_state("Requirement")`` ("draft")
    instead. Explicit, reviewed data-loss tradeoff (Task 12 report,
    Finding 2), not a bug -- recording nothing/"" would be the actual
    regression this test guards against (lesson from Tasks 3-7).
    """
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-capture-fallback")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-capture-fallback")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="REQ untracked",
        description="d",
    )
    # Deliberately no WorkflowEngineDefinition / WorkflowItemState created.

    states = state_capture.capture_states(
        [DeltaIndexTuple(item_id=str(artifact.id), version=1)], tenant_id=tenant.id
    )

    assert states[str(artifact.id)]["status"] == "draft"


@pytest.mark.django_db
def test_multi_item_capture_resolves_status_in_one_batched_call(capture_fixture):
    """N+1 avoidance: many Requirements in one capture -> one engine query.

    ``workflow.state_reader.current_states`` must be called exactly once for
    the "Requirement" item_type, regardless of how many requirements are in
    the delta index (lesson from Tasks 3-7 — batching is the whole point of
    ``_engine_status``).
    """
    from persistence.models import Artifact, Requirement, Tenant, Workspace

    tenant_id, artifact_id, req_id = capture_fixture
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)
    tenant = Tenant.objects.get(id=tenant_id)
    workspace = Workspace.objects.get(tenant=tenant)

    extra_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    Requirement.objects.create(
        tenant=tenant,
        artifact=extra_artifact,
        workspace=workspace,
        title="REQ 2",
        description="d",
    )

    delta_index = [
        DeltaIndexTuple(item_id=str(artifact_id), version=1),
        DeltaIndexTuple(item_id=str(extra_artifact.id), version=1),
    ]

    with patch.object(
        state_reader, "current_states", wraps=state_reader.current_states
    ) as spy:
        states = state_capture.capture_states(delta_index, tenant_id=tenant_id)

    # Every one of the 8 status-owning types is resolved at most once per
    # capture -- not just Requirement. A regression in any single block
    # (moving _engine_status inside its row loop) must fail this too.
    per_type = Counter(call.args[0] for call in spy.call_args_list)
    assert all(n == 1 for n in per_type.values()), per_type
    assert states[str(artifact_id)]["status"] == "approved"
    assert states[str(extra_artifact.id)]["status"] == "draft"


def test_engine_status_uses_the_correct_item_type_for_all_eight_types():
    """Regression guard for a wrong ``item_type`` string (e.g. "ADR" vs "Adr").

    A typo here would silently and permanently fall back to the column for
    that whole entity type, forever, once Phase 1 drops it -- and every other
    test in this module would still pass, because
    ``test_no_entity_status_attribute_read_remains`` only proves the direct
    column read is gone, not that the *correct* engine item_type replaced it.
    All eight domain queries are mocked to return no rows, so this exercises
    only the item_type strings each block passes to ``_engine_status`` /
    ``state_reader.current_states`` -- not their DB behaviour (covered by the
    other tests in this module and the pre-existing baseline suite).
    """
    art_id = str(uuid.uuid4())
    tuples = [DeltaIndexTuple(item_id=art_id, version=1)]

    mock_adr, mock_risk, mock_issue, mock_goal, mock_main_goal = (
        MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
    )
    with patch("persistence.models.Artifact") as mock_art, patch(
        "persistence.models.Requirement"
    ) as mock_req, patch("persistence.models.ArchitectureElement") as mock_ae, patch(
        "persistence.models.StakeholderNeed"
    ) as mock_sn, patch("persistence.models.TestCase") as mock_tc, patch.dict(
        "persistence.domain_model_registry._registry",
        {
            "Adr": mock_adr,
            "Risk": mock_risk,
            "Issue": mock_issue,
            "Goal": mock_goal,
            "MainGoal": mock_main_goal,
        },
    ), patch.object(
        state_reader, "current_states", wraps=state_reader.current_states
    ) as spy:
        mock_art.unscoped.filter.return_value.values_list.return_value = []
        mock_req.unscoped.filter.return_value = []
        mock_ae.unscoped.filter.return_value = []
        mock_sn.unscoped.filter.return_value = []
        mock_tc.unscoped.filter.return_value = []
        for mock_model in (mock_adr, mock_risk, mock_issue, mock_goal, mock_main_goal):
            mock_model.objects.filter.return_value = []

        state_capture.capture_states(tuples, tenant_id=uuid.uuid4())

    item_types = {call.args[0] for call in spy.call_args_list}
    assert item_types == {
        "Requirement",
        "StakeholderNeed",
        "TestCase",
        "Adr",
        "Risk",
        "Issue",
        "Goal",
        "MainGoal",
    }
