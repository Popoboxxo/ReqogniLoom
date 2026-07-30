"""Backfill WorkflowEngineDefinitions for the new Goal/MainGoal entity types.

Mirrors 0004_backfill_entity_workflow_definitions.py: every existing
Workspace must own a WorkflowEngineDefinition for Goal and MainGoal,
otherwise initialize_workflow_states is a silent no-op for them.

Idempotent via get_or_create on (workspace_id, item_type).
"""
from __future__ import annotations

from django.db import migrations

_ENTITY_PRESETS = (
    ("Goal", "goal_default"),
    ("MainGoal", "main_goal_default"),
)


def backfill_definitions(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    from workflow.definition_store import PRESET_SCHEMAS

    for ws in Workspace.objects.all():
        for item_type, preset_key in _ENTITY_PRESETS:
            WorkflowEngineDefinition.objects.get_or_create(
                workspace_id=str(ws.id),
                item_type=item_type,
                defaults={
                    "preset": preset_key,
                    "workflow_json": PRESET_SCHEMAS[preset_key],
                    "is_custom": False,
                    "tenant_id": ws.tenant_id,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0011_seed_auto_approve_target_flags"),
        # NOTE: brief's original placeholder was "0043_workspace_goals_toggles"
        # (explicitly flagged as needing adjustment). Verified against the
        # actual Task 2 migration on this branch (commit f419a23):
        ("persistence", "0052_workspace_goals_toggles"),
    ]

    operations = [
        migrations.RunPython(backfill_definitions, migrations.RunPython.noop),
    ]
