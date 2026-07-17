"""REQ-165/REQ-166 — Backfill WorkflowItemState for existing entity rows.

After 0004 provisions per-entity WorkflowEngineDefinitions, existing entity rows
still lack a WorkflowItemState, so the transitions API would expose no moves.
This migration seeds one WorkflowItemState per existing Adr / Risk / Issue /
ChangeRequest / TestCase row at its current ``status`` value (mapping onto the
definition's valid states; unknown values fall back to the initial state).

TestCase rows have just received a ``status`` column (default "Draft") in
persistence.0042, so they are seeded at "Draft".

Idempotent and race-safe: rows that already have a WorkflowItemState are skipped,
and item_id is a globally unique UUID so the (item_id, item_type) lookup is
sufficient. Reverse is a no-op — seeded states are valid and must not be dropped.
"""
from __future__ import annotations

from django.db import migrations


def _ensure_state(DefModel, StateModel, *, item_id, item_type, workspace_id, tenant_id, current):
    """Create a WorkflowItemState for one row if it is missing (idempotent)."""
    if StateModel.objects.filter(item_id=item_id, item_type=item_type).exists():
        return
    definition = DefModel.objects.filter(
        workspace_id=str(workspace_id), item_type=item_type
    ).first()
    if definition is None:
        # No definition (0004 did not provision this workspace/type) — cannot
        # create a state row because the FK is PROTECT and requires one.
        return
    valid_states = list((definition.workflow_json or {}).get("states", []))
    state = current if current in valid_states else (
        valid_states[0] if valid_states else current
    )
    StateModel.objects.create(
        item_id=item_id,
        item_type=item_type,
        workspace_id=workspace_id,
        definition=definition,
        current_state=state,
        tenant_id=tenant_id,
    )


def backfill_item_states(apps, schema_editor):
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")
    Adr = apps.get_model("application", "Adr")
    Risk = apps.get_model("application", "Risk")
    Issue = apps.get_model("application", "Issue")
    ChangeRequest = apps.get_model("application", "ChangeRequest")
    TestCase = apps.get_model("persistence", "TestCase")

    # Application models carry workspace_id + tenant_id + status columns directly.
    for model, item_type in (
        (Adr, "Adr"),
        (Risk, "Risk"),
        (Issue, "Issue"),
        (ChangeRequest, "ChangeRequest"),
    ):
        for row in model.objects.all():
            _ensure_state(
                WorkflowEngineDefinition,
                WorkflowItemState,
                item_id=row.id,
                item_type=item_type,
                workspace_id=row.workspace_id,
                tenant_id=row.tenant_id,
                current=row.status,
            )

    # TestCase is scoped via its backing artifact's workspace (no local
    # workspace_id column); tenant_id comes from the TenantScopedModel FK.
    for tc in TestCase.objects.select_related("artifact").all():
        _ensure_state(
            WorkflowEngineDefinition,
            WorkflowItemState,
            item_id=tc.id,
            item_type="TestCase",
            workspace_id=tc.artifact.workspace_id,
            tenant_id=tc.tenant_id,
            current=tc.status,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0004_backfill_entity_workflow_definitions"),
        # Reads Adr/Risk/Issue/ChangeRequest and TestCase.status at latest schema.
        ("application", "0011_add_change_request"),
        ("persistence", "0042_testcase_workflow_status"),
    ]

    operations = [
        migrations.RunPython(backfill_item_states, migrations.RunPython.noop),
    ]
