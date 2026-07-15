"""REQ-143 — Reconcile the persistence `status` mirror with the WorkflowEngine.

Data migration that establishes the WorkflowEngine as the single source of truth
for the lifecycle state of Requirement and StakeholderNeed (see
docs/architecture/ADR-status-single-source.md).

For every Requirement / StakeholderNeed:

  1. Has a WorkflowItemState  → the engine wins: ``status`` := ``current_state``.
  2. No WorkflowItemState but a WorkflowEngineDefinition exists for its
     workspace/item_type → create the state row (mapping the current free-text
     ``status`` to a valid state per the ADR: known state kept, else the
     definition's initial state) and mirror ``status`` onto it.
  3. No definition at all → cannot create a state row (the FK is PROTECT and
     requires a definition). Only normalise ``status`` (unknown → "draft").

The reverse operation is a no-op: reconciled values remain valid and the previous
free-text values are neither recoverable nor desirable to restore.
"""
from __future__ import annotations

from django.db import migrations

# Union of all preset states (definition_store.PRESET_SCHEMAS). Used only for the
# "no definition" normalisation path, where there is no per-workspace state list.
_GLOBAL_KNOWN_STATES = frozenset(
    {"draft", "in_review", "approved", "deprecated", "done"}
)
_FALLBACK_STATE = "draft"


def _map_status(current: str, valid_states) -> str:
    """Map a free-text status onto a valid workflow state (ADR value mapping).

    ``valid_states`` is the definition's state list, or None when no definition
    exists (then the global known-states set is used).
    """
    if valid_states is None:
        return current if current in _GLOBAL_KNOWN_STATES else _FALLBACK_STATE
    if current in valid_states:
        return current
    return valid_states[0] if valid_states else _FALLBACK_STATE


def reconcile_status_mirror(apps, schema_editor):
    Requirement = apps.get_model("persistence", "Requirement")
    StakeholderNeed = apps.get_model("persistence", "StakeholderNeed")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")

    # Historical models use a plain (unscoped) default manager, so no tenant
    # context is required here.
    for model, item_type in (
        (Requirement, "Requirement"),
        (StakeholderNeed, "StakeholderNeed"),
    ):
        for obj in model.objects.select_related("artifact").all():
            state_row = WorkflowItemState.objects.filter(
                item_id=obj.id, item_type=item_type
            ).first()

            # Case 1: engine state exists → it is authoritative.
            if state_row is not None:
                if obj.status != state_row.current_state:
                    obj.status = state_row.current_state
                    obj.save(update_fields=["status"])
                continue

            workspace_id = obj.artifact.workspace_id
            definition = WorkflowEngineDefinition.objects.filter(
                workspace_id=str(workspace_id), item_type=item_type
            ).first()

            # Case 3: no definition → normalise status only, no state row.
            if definition is None:
                normalised = _map_status(obj.status, None)
                if obj.status != normalised:
                    obj.status = normalised
                    obj.save(update_fields=["status"])
                continue

            # Case 2: definition exists → create the missing state row and mirror.
            valid_states = list((definition.workflow_json or {}).get("states", []))
            mapped = _map_status(obj.status, valid_states)
            WorkflowItemState.objects.create(
                item_id=obj.id,
                item_type=item_type,
                workspace_id=workspace_id,
                definition=definition,
                current_state=mapped,
                tenant_id=obj.tenant_id,
            )
            if obj.status != mapped:
                obj.status = mapped
                obj.save(update_fields=["status"])


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0002_alter_workflowenginedefinition_options_and_more"),
        # Reads Requirement/StakeholderNeed at their latest schema.
        ("persistence", "0036_workspace_language"),
    ]

    operations = [
        migrations.RunPython(
            reconcile_status_mirror, migrations.RunPython.noop
        ),
    ]
