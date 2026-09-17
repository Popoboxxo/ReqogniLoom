"""Spec §7.3 — add the "proposed" state to existing workflow definitions.

Same shape as 0016_seed_adr_risk_outdated_equivalent_flags: update every
GlobalWorkflowDefinition, propagate into its ``is_customized=False`` derived
rows, then sweep the workspace rows that have no linked global (pre-REQ-178
data). ``is_customized=True`` rows are deliberately left alone — that workspace
diverged on purpose and an admin can re-add the state via the Workflow Editor
(spec §7.3).

Plan deviation: the plan's own text names this "0018_add_proposed_state.py"
depending on 0017_backfill_lifecycle_status_mirror — both were true when the
plan was written (2026-09-04). The datenmodell-konsolidierung plan (merged
since) added 0018_restore_states_hijacked_by_outdate on that same slot, so
this migration is renumbered 0019 and depends on that instead.
"""
from django.db import migrations

from workflow.migrations._proposed_backfill import backfill_definition


def add_proposed_state(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    for global_def in GlobalWorkflowDefinition.objects.all():
        workflow_json = global_def.workflow_json
        if not backfill_definition(workflow_json, global_def.preset):
            continue
        global_def.workflow_json = workflow_json
        global_def.save(update_fields=["workflow_json"])
        WorkflowEngineDefinition.objects.filter(
            source_global_id=global_def.id, is_customized=False
        ).update(workflow_json=workflow_json)

    for record in WorkflowEngineDefinition.objects.filter(is_customized=False):
        workflow_json = record.workflow_json
        if not backfill_definition(workflow_json, record.preset):
            continue
        record.workflow_json = workflow_json
        record.save(update_fields=["workflow_json"])


def remove_proposed_state(apps, schema_editor):
    """Reverse: drop the proposal state and its two transitions.

    Items currently sitting in "proposed" would become orphaned, so this
    refuses rather than silently corrupting them.
    """
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")
    if WorkflowItemState.objects.filter(current_state="proposed").exists():
        raise RuntimeError(
            "Cannot reverse 0019: items still sit in the 'proposed' state. "
            "Confirm or discard them first."
        )

    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    for model in (GlobalWorkflowDefinition, WorkflowEngineDefinition):
        for row in model.objects.all():
            graph = row.workflow_json
            states = [s for s in graph.get("states", []) if s != "proposed"]
            transitions = [
                t
                for t in graph.get("transitions", [])
                if t.get("from_state") != "proposed"
            ]
            if states == graph.get("states") and transitions == graph.get(
                "transitions"
            ):
                continue
            graph["states"] = states
            graph["transitions"] = transitions
            row.workflow_json = graph
            row.save(update_fields=["workflow_json"])


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0018_restore_states_hijacked_by_outdate"),
    ]

    operations = [
        migrations.RunPython(add_proposed_state, remove_proposed_state),
    ]
