"""Give back the workflow states that the old ``outdate()`` overwrote.

Datenmodell-Konsolidierung Phase 4, Decision D-3.

Before Phase 4, ``workflow.services.outdate()`` forced
``WorkflowItemState.current_state = "outdated"`` — soft-delete was a state
hijack. ``reactivate()`` undid it by walking ``WorkflowHistoryEntry`` back to
the state the item held before. Phase 4 makes soft-delete an orthogonal flag
(``Artifact.lifecycle_status``, added by ``persistence/0074``) and stops both
functions from touching ``current_state`` at all.

That leaves every *legacy* row stranded at ``current_state = "outdated"``:

1. ``"outdated"`` is not a member of any preset's declared state list, so the
   transitions API can offer no move out of it — the row is permanently stuck.
2. Decision D-1 makes the wire ``status`` field a projection of
   ``current_state``, so such a row would keep reporting ``"outdated"`` even
   after :func:`workflow.services.reactivate` clears its flag.

Nothing re-derives these states later, so this is the one chance to restore
them — the same "no second chance" property ``persistence/0074`` documents for
its own backfill. This migration therefore runs the history walk **once**, as
data, instead of leaving it in the runtime path.

**Ordering matters.** This migration depends on ``persistence/0074``, which
copies ``current_state == "outdated"`` onto ``Artifact.lifecycle_status``. The
flag must be written *before* the states are cleared here, or the soft-deletes
would be lost outright.

**Fallback when no history exists** (a row that was already ``"outdated"`` with
no ``WorkflowHistoryEntry`` transitioning it there — e.g. hand-edited data, or
an entry whose ``from_state`` was itself ``"outdated"``): the definition's
**initial state** (``workflow_json["states"][0]``, the ``states[0]`` convention
noted in ``definition_store``). Leaving ``"outdated"`` in place was rejected: it
is not a declared state, so the row would stay stuck forever — exactly the
condition this migration exists to clear. The initial state is always declared
and always has outgoing transitions, and it is the same fallback
``RequirementService.list_requirements`` already applies to rows with no
resolvable state (Task 12 report, Finding 2). The item's soft-delete flag is
unaffected either way, so nothing becomes visible that was not visible before.
"""
from django.db import migrations

OUTDATED = "outdated"


def _require_full_row_visibility(schema_editor):
    """Fail loudly instead of silently migrating nothing under RLS.

    ``we_item_state`` and ``we_history_entry`` carry ``FORCE ROW LEVEL
    SECURITY`` (``workflow/0015``), which applies to the table owner too. Without
    this, every query below would return zero rows and the migration would
    report success while restoring nothing.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def restore_hijacked_states(apps_registry, schema_editor):
    """Replace each stranded ``"outdated"`` state with the item's real one."""
    _require_full_row_visibility(schema_editor)

    WorkflowItemState = apps_registry.get_model("workflow", "WorkflowItemState")
    WorkflowHistoryEntry = apps_registry.get_model("workflow", "WorkflowHistoryEntry")

    stranded = list(
        WorkflowItemState.objects.filter(current_state=OUTDATED).select_related(
            "definition"
        )
    )
    if not stranded:
        return

    # One query for the whole history, oldest first, so the dict ends up
    # holding the *most recent* usable pre-outdate state per item.
    restore_by_state_id: dict = {}
    for entry in (
        WorkflowHistoryEntry.objects.filter(
            item_state_id__in=[row.id for row in stranded], to_state=OUTDATED
        )
        .exclude(from_state=OUTDATED)
        .order_by("transitioned_at")
        .values_list("item_state_id", "from_state")
    ):
        item_state_id, from_state = entry
        if from_state:
            restore_by_state_id[item_state_id] = from_state

    for row in stranded:
        target = restore_by_state_id.get(row.id)
        if target is None:
            states = (row.definition.workflow_json or {}).get("states") or []
            if not states:
                # A definition with no declared states cannot yield a valid
                # target; leaving the row untouched is strictly better than
                # writing an invented one. The verify step below reports it.
                continue
            target = states[0]
        WorkflowItemState.objects.filter(pk=row.id).update(current_state=target)


def verify_no_state_left_outdated(apps_registry, schema_editor):
    """Hard-fail if any row is still parked on the retired pseudo-state."""
    _require_full_row_visibility(schema_editor)

    WorkflowItemState = apps_registry.get_model("workflow", "WorkflowItemState")
    remaining = WorkflowItemState.objects.filter(current_state=OUTDATED).count()
    if remaining:
        raise RuntimeError(
            f"{remaining} WorkflowItemState row(s) still have "
            f'current_state="{OUTDATED}" after the Phase 4 restore. '
            '"outdated" is no longer a workflow state (Decision D-3); these '
            "rows would be permanently stuck. Most likely their "
            "WorkflowEngineDefinition has an empty workflow_json['states'] "
            "list, so no valid target could be derived. Fix those definitions "
            "and re-run this migration."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0017_backfill_lifecycle_status_mirror"),
        # Must run AFTER the flag is backfilled from these very states.
        ("persistence", "0074_artifact_lifecycle_status"),
    ]

    operations = [
        # Irreversible on purpose: the pre-migration value was a destroyed
        # state, so there is nothing meaningful to roll back to.
        migrations.RunPython(restore_hijacked_states, migrations.RunPython.noop),
        migrations.RunPython(
            verify_no_state_left_outdated, migrations.RunPython.noop
        ),
    ]
