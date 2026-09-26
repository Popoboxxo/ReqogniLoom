"""CR-10 — ``provision_workflow_definitions`` inheritance-link repair.

A pre-REQ-178 workspace row carries ``source_global_id=None``. Such a row made
the command ``continue`` (it exists) AND made
``create_workspace_default_workflow`` a no-op (its ``get_or_create`` discards
``defaults`` on the Existing branch), so the row stayed unlinked forever — and
because ``_propagate`` selects on ``source_global_id``, it never received
another global edit. A silent, permanent inheritance gap.

The command now repairs exactly ``is_customized=False`` + ``source_global_id
is None``, leaves individualized (``is_customized=True``) rows untouched, and
reports both.
"""
from __future__ import annotations

from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command

from persistence.models import Tenant, Workspace
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    # Tenant is the root model and carries no ``unscoped`` manager; everything
    # below it is written through ``unscoped``.
    return Tenant.objects.create(
        name="provision-repair-tenant", slug=f"provrepair-{uuid4().hex[:8]}"
    )


@pytest.fixture
def workspace(tenant):
    return Workspace.unscoped.create(tenant_id=tenant.id, name="repair-ws")


def _legacy_row(tenant, workspace, item_type, preset, *, is_customized):
    """A pre-REQ-178 row: preset graph copied straight in, no global link.

    Written through ``unscoped`` (as a real pre-REQ-178 row would be, from a
    migration/backup) so the fixture needs no ambient tenant context — the
    command arms its own per workspace.
    """
    from workflow.definition_store import PRESET_SCHEMAS

    return WorkflowEngineDefinition.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=str(workspace.id),
        item_type=item_type,
        preset=preset,
        workflow_json={
            "states": list(PRESET_SCHEMAS[preset]["states"]),
            "transitions": [],
        },
        source_global=None,
        is_customized=is_customized,
    )


def _run(workspace) -> str:
    out = StringIO()
    call_command(
        "provision_workflow_definitions",
        workspace_id=str(workspace.id),
        stdout=out,
        stderr=out,
    )
    return out.getvalue()


def test_legacy_unlinked_row_is_repaired_and_reported(tenant, workspace) -> None:
    row = _legacy_row(tenant, workspace, "Issue", "issue_default", is_customized=False)

    output = _run(workspace)

    reloaded = WorkflowEngineDefinition.unscoped.get(pk=row.pk)
    assert reloaded.source_global_id is not None, (
        "the legacy row must be linked to a tenant global"
    )
    assert reloaded.is_customized is False
    global_def = GlobalWorkflowDefinition.unscoped.get(pk=reloaded.source_global_id)
    assert (global_def.tenant_id, global_def.item_type, global_def.preset) == (
        tenant.id,
        "Issue",
        "issue_default",
    )
    # The on-default invariant is re-asserted: the row now really does mirror
    # its source_global's graph, so a later global edit propagates cleanly.
    assert reloaded.workflow_json == global_def.workflow_json
    assert "repaired 1 unlinked definition(s)" in output
    assert "repaired Issue (issue_default)" in output


def test_customized_row_is_never_touched_and_is_named_in_the_report(
    tenant, workspace
) -> None:
    """An individualized workspace is left exactly as found, and the report
    names it (the audit needs the negative space, not just a count)."""
    row = _legacy_row(tenant, workspace, "Risk", "risk_default", is_customized=True)
    before = (row.source_global_id, row.workflow_json, row.is_customized)

    output = _run(workspace)

    reloaded = WorkflowEngineDefinition.unscoped.get(pk=row.pk)
    assert (
        reloaded.source_global_id,
        reloaded.workflow_json,
        reloaded.is_customized,
    ) == before, "a customized row must not be modified"
    assert "repaired 0 unlinked definition(s)" in output
    assert "Not repaired" in output
    assert "[customized] Risk (risk_default)" in output
    assert str(workspace.id) in output


def test_repair_is_idempotent(tenant, workspace) -> None:
    """A second run repairs nothing and creates nothing new."""
    row = _legacy_row(tenant, workspace, "Issue", "issue_default", is_customized=False)
    _legacy_row(tenant, workspace, "Risk", "risk_default", is_customized=True)

    first = _run(workspace)
    after_first = WorkflowEngineDefinition.unscoped.get(pk=row.pk)
    counts_after_first = WorkflowEngineDefinition.unscoped.filter(
        workspace_id=str(workspace.id)
    ).count()

    second = _run(workspace)
    after_second = WorkflowEngineDefinition.unscoped.get(pk=row.pk)

    assert "repaired 1 unlinked definition(s)" in first
    assert "repaired 0 unlinked definition(s)" in second
    assert after_second.source_global_id == after_first.source_global_id
    assert after_second.workflow_json == after_first.workflow_json
    assert (
        WorkflowEngineDefinition.unscoped.filter(
            workspace_id=str(workspace.id)
        ).count()
        == counts_after_first
    ), "the second run created a duplicate"
    # The customized row is reported as skipped on every run, not just the first.
    assert "[customized] Risk (risk_default)" in second


def test_already_linked_row_is_left_alone(tenant, workspace) -> None:
    """A healthy on-default row is neither repaired nor reported as skipped."""
    global_def = GlobalWorkflowDefinition.unscoped.create(
        tenant_id=tenant.id,
        item_type="Adr",
        preset="adr_default",
        workflow_json={"states": ["draft", "accepted"], "transitions": []},
    )
    row = WorkflowEngineDefinition.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=str(workspace.id),
        item_type="Adr",
        preset="adr_default",
        workflow_json={"states": ["draft", "accepted"], "transitions": []},
        source_global=global_def,
        is_customized=False,
    )

    output = _run(workspace)

    reloaded = WorkflowEngineDefinition.unscoped.get(pk=row.pk)
    assert reloaded.source_global_id == global_def.id
    assert "[customized] Adr" not in output
    assert "repaired 0 unlinked definition(s)" in output


def test_repaired_row_receives_a_later_global_propagation(tenant, workspace) -> None:
    """The point of the repair: after linking, a global edit reaches the row.

    Without the repair this assertion fails — ``_propagate`` filters on
    ``source_global_id``, so an unlinked row is invisible to every global edit.
    """
    from workflow.global_definition_store import GlobalWorkflowDefinitionStore

    row = _legacy_row(tenant, workspace, "Issue", "issue_default", is_customized=False)
    _run(workspace)
    assert WorkflowEngineDefinition.unscoped.get(pk=row.pk).source_global_id is not None

    _obj, propagated = GlobalWorkflowDefinitionStore().add_state(
        tenant.id, "Issue", "issue_default", "In Review"
    )

    assert propagated == 1
    assert "In Review" in WorkflowEngineDefinition.unscoped.get(
        pk=row.pk
    ).workflow_json["states"]


# ---------------------------------------------------------------------------
# B1 — the re-sync must not strand a live item
# ---------------------------------------------------------------------------


def _edited_legacy_row(tenant, workspace, item_type, preset, *, extra_state):
    """A legacy row whose graph was EDITED: it declares a state the tenant
    global never had.

    ``is_customized=False`` here does NOT mean "mirrors the global" — the flag
    was introduced *after* legacy rows existed, so on such a row it only means
    "never set". That is the whole premise of B1: the repair must not trust it.
    """
    from workflow.definition_store import PRESET_SCHEMAS

    states = list(PRESET_SCHEMAS[preset]["states"]) + [extra_state]
    return WorkflowEngineDefinition.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=str(workspace.id),
        item_type=item_type,
        preset=preset,
        workflow_json={"states": states, "transitions": []},
        source_global=None,
        is_customized=False,
    )


def _live_item(tenant, workspace, definition, state) -> None:
    from workflow.models import WorkflowItemState

    WorkflowItemState.unscoped.create(
        tenant_id=tenant.id,
        item_id=uuid4(),
        item_type=definition.item_type,
        workspace_id=str(workspace.id),
        definition=definition,
        current_state=state,
    )


def test_repair_is_refused_when_it_would_strand_a_live_item(tenant, workspace) -> None:
    """B1: an edited legacy row with a live item in an undeclared state is left
    exactly as found, and the report names it.

    Pre-fix the command unconditionally ran
    ``.update(workflow_json=<global graph>, is_customized=False)``. The item in
    the edited-only state would have been left pointing at a state its own
    definition no longer declares — a state it can never transition out of —
    and the row would then be LINKED as non-customized, so every future global
    edit propagated into it as well. This is the CR-09b stranding reintroduced
    one layer down, without a gate.
    """
    extra_state = "Site Specific Legacy State"
    row = _edited_legacy_row(
        tenant, workspace, "Risk", "risk_default", extra_state=extra_state
    )
    _live_item(tenant, workspace, row, extra_state)
    before = (row.source_global_id, row.workflow_json, row.is_customized)

    output = _run(workspace)

    reloaded = WorkflowEngineDefinition.unscoped.get(pk=row.pk)
    assert (
        reloaded.source_global_id,
        reloaded.workflow_json,
        reloaded.is_customized,
    ) == before, "a row whose repair would strand a live item must not be touched"
    assert reloaded.source_global_id is None, (
        "linking the row is the dangerous half too: as is_customized=False it "
        "would then receive every future global edit"
    )
    assert extra_state in reloaded.workflow_json["states"]
    assert "repaired 0 unlinked definition(s)" in output
    assert "[would-orphan-live-item] Risk (risk_default)" in output
    assert str(workspace.id) in output


def test_repair_proceeds_when_the_edited_states_hold_no_live_item(tenant, workspace) -> None:
    """Counter-case for B1: the gate keys on a LIVE ITEM, not on divergence.

    A legacy row with extra state names that no item occupies is safe to
    re-sync — stranding requires an item, so refusing here would make the
    command refuse repairs it can perform without risk.
    """
    extra_state = "Site Specific Legacy State"
    row = _edited_legacy_row(
        tenant, workspace, "Risk", "risk_default", extra_state=extra_state
    )

    output = _run(workspace)

    reloaded = WorkflowEngineDefinition.unscoped.get(pk=row.pk)
    assert reloaded.source_global_id is not None, "a safe repair must still happen"
    assert extra_state not in reloaded.workflow_json["states"]
    assert "repaired 1 unlinked definition(s)" in output
    assert "[would-orphan-live-item]" not in output


def test_repair_is_refused_when_a_live_item_sits_in_a_declared_state(
    tenant, workspace
) -> None:
    """B1 precision: only states the global does NOT declare count as orphaned.

    An item sitting in a state the global also declares is not stranded by the
    re-sync — it survives. Gating on ``existing_states - global_states`` rather
    than on "any live item" keeps the command from refusing harmless repairs in
    a workspace that has live items (which is every healthy workspace).
    """
    from workflow.definition_store import PRESET_SCHEMAS

    row = _edited_legacy_row(
        tenant, workspace, "Issue", "issue_default", extra_state="Unused Extra"
    )
    shared_state = PRESET_SCHEMAS["issue_default"]["states"][0]
    _live_item(tenant, workspace, row, shared_state)

    output = _run(workspace)

    assert WorkflowEngineDefinition.unscoped.get(pk=row.pk).source_global_id is not None
    assert "repaired 1 unlinked definition(s)" in output


# ---------------------------------------------------------------------------
# m8 — the empty-global fail-safe
# ---------------------------------------------------------------------------


def test_empty_global_is_reported_instead_of_resyncing_to_an_empty_graph(
    tenant, workspace
) -> None:
    """m8: the only new branch that guards live state had no test.

    The tenant global is seeded EMPTY (which ``get_or_seed_from_preset``
    legitimately produces for an unknown preset key). Linking would re-sync the
    row to that empty graph and destroy every live state name in the workspace
    — a strictly worse failure than the B1 one, because here the states are lost
    from the DEFINITION too, so nothing downstream can even name what was lost.
    """
    global_def = GlobalWorkflowDefinition.unscoped.create(
        tenant_id=tenant.id,
        item_type="Goal",
        preset="goal_default",
        workflow_json={"states": [], "transitions": []},
    )
    row = _legacy_row(tenant, workspace, "Goal", "goal_default", is_customized=False)
    before = (row.source_global_id, row.workflow_json, row.is_customized)

    output = _run(workspace)

    reloaded = WorkflowEngineDefinition.unscoped.get(pk=row.pk)
    assert (reloaded.source_global_id, reloaded.workflow_json, reloaded.is_customized) == before
    assert reloaded.workflow_json["states"], "the live state names must survive"
    assert "repaired 0 unlinked definition(s)" in output
    assert "[empty-global] Goal (goal_default)" in output
    assert str(workspace.id) in output
    # The pre-seeded global is left as found, too.
    assert GlobalWorkflowDefinition.unscoped.get(pk=global_def.pk).workflow_json == {
        "states": [],
        "transitions": [],
    }


# ---------------------------------------------------------------------------
# m7 — the report names the ROW's preset, not the loop variable's
# ---------------------------------------------------------------------------


def test_report_names_the_presets_of_the_rows_it_skipped(tenant, workspace) -> None:
    """m7: the report must name the ROW's preset, not the loop variable's.

    The skip/repair lookup is keyed on ``(workspace_id, item_type)`` only — the
    preset is not part of it — so the loop's ``preset_key`` is not guaranteed to
    be the preset the found row actually carries. Reporting the loop variable
    therefore produces an audit line naming a preset the row does not have, in a
    report whose whole purpose is to name rows precisely.

    Reachability note: the review finding framed this as ">1 row per pair".
    That variant is NOT reachable — ``uq_wedef_tenant_ws_type`` already makes
    ``(tenant, workspace, item_type)`` unique, so ``.first()`` can only ever see
    one row. The reachable variant, exercised here, is a row whose ``preset``
    differs from the loop's ``preset_key`` for that item type (a workspace whose
    stored definition was written under a different rigor preset). Same defect,
    same fix, and a real shape rather than a hypothetical one.
    """
    from workflow.definition_store import PRESET_SCHEMAS

    # The loop's preset_key for item_type "Issue" is "issue_default"; this row
    # carries "goal_default" instead.
    row = WorkflowEngineDefinition.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=str(workspace.id),
        item_type="Issue",
        preset="goal_default",
        workflow_json={
            "states": list(PRESET_SCHEMAS["goal_default"]["states"]),
            "transitions": [],
        },
        source_global=None,
        is_customized=True,
    )
    assert row.preset != "issue_default"

    output = _run(workspace)

    assert "[customized] Issue (goal_default)" in output, (
        "the report must name the preset the row actually carries, not the "
        "loop's canonical preset_key for that item type"
    )
    assert "[customized] Issue (issue_default)" not in output, (
        "the report named the loop's preset_key, which belongs to no row here"
    )
