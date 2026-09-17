"""Agent-created artifacts start in "proposed" (spec §4.2)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from workflow.definition_store import WorkflowDefinitionDTO
from workflow.services import initial_state_for

WS = UUID("11111111-1111-1111-1111-111111111111")


def _ctx(actor_type: str) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
    )


def _dto(states: tuple[str, ...]) -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        states=states,
        transitions=(),
        workspace_id=WS,
        item_type="Requirement",
        preset="standard",
    )


def test_human_gets_the_definitions_initial_state():
    store = MagicMock()
    store.get_definition.return_value = _dto(("draft", "proposed", "approved"))
    with patch("workflow.services._get_store", return_value=store):
        assert initial_state_for(_ctx("user"), "Requirement", WS) == "draft"


def test_agent_gets_proposed_when_the_graph_has_it():
    store = MagicMock()
    store.get_definition.return_value = _dto(("draft", "proposed", "approved"))
    with patch("workflow.services._get_store", return_value=store):
        assert initial_state_for(_ctx("agent"), "Requirement", WS) == "proposed"


def test_agent_falls_back_when_the_graph_lacks_proposed():
    store = MagicMock()
    store.get_definition.return_value = _dto(("draft", "done"))
    with patch("workflow.services._get_store", return_value=store):
        assert initial_state_for(_ctx("agent"), "Requirement", WS) == "draft"


def test_definition_lookup_failure_never_raises():
    from workflow.definition_store import WorkflowDefinitionError

    store = MagicMock()
    store.get_definition.side_effect = WorkflowDefinitionError("nope")
    with patch("workflow.services._get_store", return_value=store):
        # The create_X() paths swallow workflow-init exceptions, so a raise here
        # would silently leave the artifact with no workflow state at all.
        assert initial_state_for(_ctx("agent"), "Requirement", WS) == "draft"


@pytest.mark.django_db
def test_lifecycle_honours_an_explicit_initial_state(
    requirement_with_workflow, auth_ctx
):
    # Deviation from plan text: `requirement_with_workflow` clears the tenant
    # context in its own `finally` before returning (see conftest.py), so a
    # direct lifecycle-manager call here needs to re-set it — the same
    # pattern test_backfill_outdated_command.py already uses with this same
    # fixture pair.
    from persistence.tenancy import TenantContext
    from workflow.lifecycle_manager import StateLifecycleManager

    item_id, workspace_id = requirement_with_workflow
    other_id = uuid4()
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        states = StateLifecycleManager().initialize_workflow_states(
            item_ids=[other_id],
            item_type="Requirement",
            workspace_id=workspace_id,
            initial_state="proposed",
        )
    finally:
        TenantContext.clear_tenant()
    assert states[0].current_state == "proposed"


@pytest.mark.django_db
def test_proposed_init_writes_a_history_entry(requirement_with_workflow, auth_ctx):
    from persistence.tenancy import TenantContext
    from workflow.lifecycle_manager import StateLifecycleManager
    from workflow.models import WorkflowHistoryEntry

    _item_id, workspace_id = requirement_with_workflow
    new_id = uuid4()
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        states = StateLifecycleManager().initialize_workflow_states(
            item_ids=[new_id],
            item_type="Requirement",
            workspace_id=workspace_id,
            initial_state="proposed",
            proposed_by="Claude Code",
        )
        entry = WorkflowHistoryEntry.unscoped.get(item_state=states[0])
    finally:
        TenantContext.clear_tenant()
    assert entry.from_state == ""
    assert entry.to_state == "proposed"
    assert entry.transitioned_by == "Claude Code"


@pytest.mark.django_db
def test_normal_init_writes_no_history(requirement_with_workflow, auth_ctx):
    from persistence.tenancy import TenantContext
    from workflow.lifecycle_manager import StateLifecycleManager
    from workflow.models import WorkflowHistoryEntry

    _item_id, workspace_id = requirement_with_workflow
    new_id = uuid4()
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        states = StateLifecycleManager().initialize_workflow_states(
            item_ids=[new_id], item_type="Requirement", workspace_id=workspace_id
        )
        exists = WorkflowHistoryEntry.unscoped.filter(item_state=states[0]).exists()
    finally:
        TenantContext.clear_tenant()
    assert not exists


# NOTE: the plan's own test_proposed_init_syncs_the_status_mirror is
# deliberately not implemented. Datenmodell-Konsolidierung Phase 1/Task 24
# (merged into main since this plan was written) removed the per-entity
# status mirror columns (Requirement.status included) entirely --
# WorkflowItemState.current_state is the sole store now, so "syncing the
# mirror" has no target to sync. See the comment in
# StateLifecycleManager.initialize_workflow_states for the full reasoning.
