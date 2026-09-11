"""Security review M3 — take the proposal state back out of interview workflows.

0019 injected ``proposed`` into every non-``minimal`` preset, ``interview_default``
included. That froze the primary MCP path: an agent-started InterviewSession is
seeded into ``proposed`` by ``workflow.services.initial_state_for``, whose only
exits are ``in_progress`` and ``rejected`` — and Rule 0 forbids the agent itself
from taking either, while no review surface exists to let a human unblock it. The
session could therefore never reach ``completed``.

``interview_default`` is now listed in ``SCHEMAS_WITHOUT_PROPOSED``, which fixes
new definitions. This migration repairs the rows 0019 already wrote, and moves
any session parked in ``proposed`` back to the definition's real initial state so
nothing is left pointing at a state that no longer exists.

Only the ``interview_default`` preset is touched; every other preset keeps its
proposal state. ``is_customized=True`` rows are left alone for the same reason
0019 leaves them alone: that workspace diverged on purpose.
"""
from django.db import migrations

_PRESET = "interview_default"
_PROPOSED = "proposed"
# Injected by inject_proposed_state alongside "proposed" as the discard target;
# it is not an InterviewSession status either, so it goes back out with it.
_INJECTED_REJECT = "rejected"


def _strip(graph: dict) -> bool:
    """Remove the injected states/transitions from *graph* in place.

    Returns True when the graph actually changed (keeps this idempotent).
    """
    states = [s for s in graph.get("states") or [] if s not in (_PROPOSED, _INJECTED_REJECT)]
    transitions = [
        t
        for t in graph.get("transitions") or []
        if t.get("from_state") not in (_PROPOSED, _INJECTED_REJECT)
        and t.get("to_state") not in (_PROPOSED, _INJECTED_REJECT)
    ]
    state_meta = {
        name: meta
        for name, meta in (graph.get("state_meta") or {}).items()
        if name not in (_PROPOSED, _INJECTED_REJECT)
    }
    changed = (
        states != (graph.get("states") or [])
        or transitions != (graph.get("transitions") or [])
        or state_meta != (graph.get("state_meta") or {})
    )
    if not changed:
        return False
    graph["states"] = states
    graph["transitions"] = transitions
    if graph.get("state_meta") is not None:
        graph["state_meta"] = state_meta
    return True


def unpropose_interview_definitions(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")

    for global_def in GlobalWorkflowDefinition.objects.filter(preset=_PRESET):
        graph = global_def.workflow_json
        if not _strip(graph):
            continue
        global_def.workflow_json = graph
        global_def.save(update_fields=["workflow_json"])
        WorkflowEngineDefinition.objects.filter(
            source_global_id=global_def.id, is_customized=False
        ).update(workflow_json=graph)

    for record in WorkflowEngineDefinition.objects.filter(
        preset=_PRESET, is_customized=False
    ):
        graph = record.workflow_json
        if not _strip(graph):
            continue
        record.workflow_json = graph
        record.save(update_fields=["workflow_json"])

    # Rescue the sessions 0019 stranded. "in_progress" is interview_default's
    # initial_state (states[0]) and the confirm target the proposal graph
    # itself pointed at, so this is the move a human would have made.
    WorkflowItemState.objects.filter(
        item_type="Interview", current_state__in=(_PROPOSED, _INJECTED_REJECT)
    ).update(current_state="in_progress")


def noop_reverse(apps, schema_editor):
    """Reversing re-runs 0019's injection, which is what this undid."""


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0019_add_proposed_state"),
    ]

    operations = [
        migrations.RunPython(unpropose_interview_definitions, noop_reverse),
    ]
