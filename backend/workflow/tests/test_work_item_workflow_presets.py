"""Plan F F3-T2 — the three tier-dependent WorkItem lifecycles.

Covers the contract fixed in ``docs/superpowers/specs/Archive/2026-11-02-f3-workitem-design.md``
§4/§5 and plan F §WP F3:

* ``work_item_minimal`` = ``todo -> in_progress -> done`` plus ``dropped``;
* ``work_item_standard`` adds ``blocked``;
* ``work_item_extended`` adds ``in_review`` and makes ``in_review -> done`` an
  ``approver``-only edge (the structural half of "done requires sign-off");
* a transition into ``blocked`` requires a non-empty ``blocked_reason``;
* G-1/G-2 (F2-T4) become reachable now that WorkItems exist, and G-2's
  ``informational`` exception is resolved as a rule (a ``Checkpoint`` marker),
  not a new column;
* the canonical registry treats ``WorkItem`` as tier-driven, like
  ``Requirement``;
* workspace provisioning seeds the tier-matched preset.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Document, WorkItem, Workspace
from persistence.tenancy import TenantContext
from presets.models import WorkspacePresetConfig
from workflow.definition_store import (
    PRESET_SCHEMAS,
    PROPOSED_STATE,
    SCHEMAS_WITHOUT_PROPOSED,
    get_state_meta,
)
from workflow.item_types import (
    KNOWN_WORKFLOW_ITEM_TYPES,
    WORK_ITEM_PRESET_BY_TIER,
    WORKFLOW_ITEM_TYPE_PRESETS,
    work_item_preset_key,
)
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition, WorkflowItemState
from workflow.precondition_rules import (
    EC_WORK_ITEM_BLOCKED_REASON_REQUIRED,
    check_document_gates,
    check_work_item_preconditions,
)
from workflow.services import create_default_workflow, initial_state_for
from workflow.state_reader import initial_state

pytestmark = pytest.mark.django_db

_RELEASE_STATE = "Freigegeben"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant(db):
    from persistence.models import Tenant

    return Tenant.objects.create(name="WI Workflow Tenant", slug="wi-wf-tenant")


def _make_workspace(tenant, name="WI Workflow WS", tier="standard") -> Workspace:
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"tier": tier}
        )
        WorkspacePresetConfig.objects.create(
            tenant=tenant,
            workspace=workspace,
            active_tier=tier,
        )
        return workspace


@pytest.fixture
def workspace(tenant):
    return _make_workspace(tenant)


def _seed_work_item_workflow(tenant, workspace, tier="standard") -> WorkflowEngineDefinition:
    with _tenant_scope(tenant.id):
        create_default_workflow(
            workspace_id=workspace.id,
            preset=work_item_preset_key(tier),
            item_type="WorkItem",
            tenant_id=tenant.id,
        )
        return WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace.id), item_type="WorkItem"
        )


def _seed_document_workflow(tenant, workspace) -> WorkflowEngineDefinition:
    with _tenant_scope(tenant.id):
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=tenant.id,
        )
        return WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace.id), item_type="Document"
        )


def _document(tenant, workspace, **overrides) -> Document:
    data = {
        "tenant": tenant,
        "title": "Plan F F3 — WorkItems",
        "kind": Document.Kind.PLAN,
        "body": "## Plan\n\nWork state.",
    }
    data.update(overrides)
    with _tenant_scope(tenant.id):
        data.setdefault(
            "artifact",
            Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Document"
            ),
        )
        return Document.objects.create(**data)


def _work_item(tenant, workspace, document, *, kind=None, **overrides) -> WorkItem:
    data = {
        "tenant": tenant,
        "document": document,
        "kind": kind or WorkItem.Kind.STEP,
        "ordinal": 1,
        "title": "Step 1",
    }
    data.update(overrides)
    with _tenant_scope(tenant.id):
        data.setdefault(
            "artifact",
            Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="WorkItem"
            ),
        )
        return WorkItem.objects.create(**data)


def _set_state(tenant, workspace, definition, item, state: str) -> None:
    with _tenant_scope(tenant.id):
        WorkflowItemState.objects.create(
            tenant=tenant,
            workspace=workspace,
            definition=definition,
            item_id=item.pk,
            item_type="WorkItem",
            current_state=state,
        )


def _transitions(preset: str) -> set[tuple[str, str]]:
    return {
        (t["from_state"], t["to_state"])
        for t in PRESET_SCHEMAS[preset]["transitions"]
    }


def _transition(preset: str, from_state: str, to_state: str) -> dict:
    return next(
        t
        for t in PRESET_SCHEMAS[preset]["transitions"]
        if (t["from_state"], t["to_state"]) == (from_state, to_state)
    )


# ---------------------------------------------------------------------------
# Schema shapes
# ---------------------------------------------------------------------------


def test_minimal_lifecycle_is_only_the_execution_state():
    assert PRESET_SCHEMAS["work_item_minimal"]["states"] == [
        "todo",
        "in_progress",
        "done",
        "dropped",
    ]
    assert _transitions("work_item_minimal") == {
        ("todo", "in_progress"),
        ("in_progress", "done"),
        ("todo", "dropped"),
        ("in_progress", "dropped"),
    }


def test_standard_adds_blocked_with_recovery_and_drop_edges():
    assert PRESET_SCHEMAS["work_item_standard"]["states"] == [
        "todo",
        "in_progress",
        "blocked",
        "done",
        "dropped",
    ]
    transitions = _transitions("work_item_standard")
    assert {("in_progress", "blocked"), ("blocked", "in_progress"), ("blocked", "dropped")} <= transitions
    # The minimal edges stay untouched.
    assert ("todo", "in_progress") in transitions
    assert ("in_progress", "done") in transitions
    assert ("in_review", "done") not in transitions


def test_extended_reaches_done_only_through_an_approver_review():
    schema = PRESET_SCHEMAS["work_item_extended"]
    assert schema["states"] == [
        "todo",
        "in_progress",
        "blocked",
        "in_review",
        "done",
        "dropped",
    ]
    transitions = _transitions("work_item_extended")

    # No direct completion edge: done is reachable only from in_review.
    assert ("in_progress", "done") not in transitions
    done_sources = {src for src, target in transitions if target == "done"}
    assert done_sources == {"in_review"}

    sign_off = _transition("work_item_extended", "in_review", "done")
    assert set(sign_off["allowed_roles"]) == {"approver", "admin"}

    # Rework goes back to in_progress for an editor; an approver is not needed.
    rework = _transition("work_item_extended", "in_review", "in_progress")
    assert set(rework["allowed_roles"]) <= {"editor", "admin"}


def test_extended_marks_done_as_requiring_approval():
    assert get_state_meta(PRESET_SCHEMAS["work_item_extended"], "done")[
        "requires_approval"
    ] is True
    # The lighter presets do not claim an approval has happened.
    for preset in ("work_item_minimal", "work_item_standard"):
        assert not get_state_meta(PRESET_SCHEMAS[preset], "done").get(
            "requires_approval", False
        )


@pytest.mark.parametrize(
    "preset",
    ["work_item_minimal", "work_item_standard", "work_item_extended"],
)
def test_dropped_is_the_terminal_dead_end_in_every_preset(preset):
    assert get_state_meta(PRESET_SCHEMAS[preset], "dropped")[
        "is_outdated_equivalent"
    ] is True


@pytest.mark.parametrize(
    "preset",
    ["work_item_minimal", "work_item_standard", "work_item_extended"],
)
def test_work_item_presets_carry_no_agent_proposal_state(preset):
    """The work item is the agent's own state store, not a reviewable proposal."""
    assert preset in SCHEMAS_WITHOUT_PROPOSED
    assert PROPOSED_STATE not in PRESET_SCHEMAS[preset]["states"]
    assert initial_state("WorkItem") == "todo"


def test_agent_created_work_item_starts_in_todo_not_proposed(tenant, workspace):
    _seed_work_item_workflow(tenant, workspace, tier="extended")
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        actor_type="agent",
        agent_label="test-agent",
    )
    with _tenant_scope(tenant.id):
        assert initial_state_for(ctx, "WorkItem", workspace.id) == "todo"


# ---------------------------------------------------------------------------
# Canonical registry (drift gate)
# ---------------------------------------------------------------------------


def test_work_item_is_registered_as_a_tier_driven_type():
    assert WORK_ITEM_PRESET_BY_TIER == {
        "minimal": "work_item_minimal",
        "standard": "work_item_standard",
        "extended": "work_item_extended",
    }
    assert "WorkItem" in KNOWN_WORKFLOW_ITEM_TYPES
    assert "WorkItem" not in WORKFLOW_ITEM_TYPE_PRESETS
    for preset in WORK_ITEM_PRESET_BY_TIER.values():
        assert preset in PRESET_SCHEMAS


# ---------------------------------------------------------------------------
# Rule 10 — blocked requires blocked_reason
# ---------------------------------------------------------------------------


def test_blocked_transition_requires_a_blocked_reason(tenant, workspace):
    document = _document(tenant, workspace)
    item = _work_item(tenant, workspace, document)

    with _tenant_scope(tenant.id):
        violation = check_work_item_preconditions(
            workspace_id=str(workspace.id),
            item_type="WorkItem",
            item_id=item.pk,
            target_state="blocked",
        )

    assert violation is not None
    assert violation[0] == EC_WORK_ITEM_BLOCKED_REASON_REQUIRED


def test_blocked_transition_passes_with_a_reason(tenant, workspace):
    document = _document(tenant, workspace)
    item = _work_item(
        tenant, workspace, document, blocked_reason="Waiting for the API contract"
    )

    with _tenant_scope(tenant.id):
        assert (
            check_work_item_preconditions(
                workspace_id=str(workspace.id),
                item_type="WorkItem",
                item_id=item.pk,
                target_state="blocked",
            )
            is None
        )


def test_work_item_preconditions_ignore_other_types_and_targets(tenant, workspace):
    document = _document(tenant, workspace)
    item = _work_item(tenant, workspace, document)

    with _tenant_scope(tenant.id):
        # Other item type, same target state.
        assert (
            check_work_item_preconditions(
                workspace_id=str(workspace.id),
                item_type="Requirement",
                item_id=item.pk,
                target_state="blocked",
            )
            is None
        )
        # WorkItem, other target state.
        assert (
            check_work_item_preconditions(
                workspace_id=str(workspace.id),
                item_type="WorkItem",
                item_id=item.pk,
                target_state="in_progress",
            )
            is None
        )


# ---------------------------------------------------------------------------
# G-1 / G-2 — the F2 document gates become reachable
# ---------------------------------------------------------------------------


def _gate_details(tenant, workspace, document):
    with _tenant_scope(tenant.id):
        violation = check_document_gates(
            workspace_id=str(workspace.id),
            item_type="Document",
            item_id=document.pk,
            target_state=_RELEASE_STATE,
        )
    if violation is None:
        return []
    return violation[2]


def test_g1_blocks_release_while_a_work_item_is_in_progress(tenant, workspace):
    _seed_document_workflow(tenant, workspace)
    document = _document(tenant, workspace)
    item = _work_item(tenant, workspace, document, kind=WorkItem.Kind.CHECKPOINT)

    definition = _seed_work_item_workflow(tenant, workspace)
    _set_state(tenant, workspace, definition, item, "in_progress")

    gates = {entry["gate"] for entry in _gate_details(tenant, workspace, document)}
    assert "G-1" in gates
    # Checkpoint is informational, so G-2 must not also fire.
    assert "G-2" not in gates


def test_g2_blocks_release_for_an_unlinked_non_informational_item(tenant, workspace):
    _seed_document_workflow(tenant, workspace)
    document = _document(tenant, workspace)
    item = _work_item(tenant, workspace, document, kind=WorkItem.Kind.STEP)

    definition = _seed_work_item_workflow(tenant, workspace)
    _set_state(tenant, workspace, definition, item, "todo")

    gates = {entry["gate"] for entry in _gate_details(tenant, workspace, document)}
    assert "G-2" in gates
    assert "G-1" not in gates


def test_g2_accepts_an_informational_checkpoint_without_a_link(tenant, workspace):
    _seed_document_workflow(tenant, workspace)
    document = _document(tenant, workspace)
    item = _work_item(tenant, workspace, document, kind=WorkItem.Kind.CHECKPOINT)
    assert item.informational is True

    definition = _seed_work_item_workflow(tenant, workspace)
    _set_state(tenant, workspace, definition, item, "todo")

    assert _gate_details(tenant, workspace, document) == []


def test_work_item_with_a_trace_link_satisfies_g2(tenant, workspace):
    _seed_document_workflow(tenant, workspace)
    document = _document(tenant, workspace)
    item = _work_item(tenant, workspace, document, kind=WorkItem.Kind.STEP)

    definition = _seed_work_item_workflow(tenant, workspace)
    _set_state(tenant, workspace, definition, item, "todo")

    from persistence.models import TraceLink

    related = _document(tenant, workspace, title="Related document")
    with _tenant_scope(tenant.id):
        TraceLink.objects.create(
            tenant=tenant,
            source=item.artifact,
            target=related.artifact,
            link_type="references",
        )

    assert _gate_details(tenant, workspace, document) == []


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------


def test_provisioning_seeds_the_tier_matched_work_item_workflow(tenant, workspace):
    from application.workspace_provisioning import provision_workspace_defaults

    with _tenant_scope(tenant.id):
        provision_workspace_defaults(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            requirement_preset="standard",
        )

    with _tenant_scope(tenant.id):
        definition = WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace.id), item_type="WorkItem"
        )
        globals_ = set(
            GlobalWorkflowDefinition.objects.filter(
                tenant_id=tenant.id, item_type="WorkItem"
            ).values_list("preset", flat=True)
        )

    assert definition.preset == "work_item_standard"
    assert definition.workflow_json["states"][0] == "todo"
    assert definition.source_global_id is not None
    assert globals_ == {
        "work_item_minimal",
        "work_item_standard",
        "work_item_extended",
    }


def test_provisioning_work_item_preset_can_override_the_workspace_tier(
    tenant, workspace
):
    from application.workspace_provisioning import provision_workspace_defaults

    with _tenant_scope(tenant.id):
        provision_workspace_defaults(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            requirement_preset="minimal",
            work_item_preset="extended",
        )
        definition = WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace.id), item_type="WorkItem"
        )

    assert definition.preset == "work_item_extended"
