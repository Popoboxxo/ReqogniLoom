"""REQ-165/REQ-166 — Backfill per-entity WorkflowEngineDefinitions.

Universal configurable workflow engine per entity type: every existing
Workspace must own a WorkflowEngineDefinition for each workflow-tracked entity
type, otherwise ``initialize_workflow_states`` is a silent no-op and the entity's
``status`` mirror never moves off its default.

For every existing Workspace this migration provisions the fixed per-entity
preset defaults (StakeholderNeed, Adr, Risk, Issue, TestCase, ChangeRequest).
``Requirement`` is intentionally skipped — it is already provisioned with the
tier-dependent preset (minimal/standard/extended) at workspace creation.

Idempotent via ``get_or_create`` on (workspace_id, item_type) — ``workspace_id``
is a globally unique UUID, so this pair is unique across tenants. A workspace
that already has a definition (e.g. a customised one) is left untouched.

The reverse operation is a no-op: removing auto-provisioned definitions could
strand WorkflowItemState rows (definition FK is PROTECT) and is never desirable.
"""
from __future__ import annotations

from django.db import migrations

# (item_type, preset key in workflow.definition_store.PRESET_SCHEMAS).
# ChangeRequest reuses the pre-existing ccb_approval preset.
_ENTITY_PRESETS = (
    ("StakeholderNeed", "need_default"),
    ("Adr", "adr_default"),
    ("Risk", "risk_default"),
    ("Issue", "issue_default"),
    ("TestCase", "testcase_default"),
    ("ChangeRequest", "ccb_approval"),
)


def backfill_definitions(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    # PRESET_SCHEMAS is constant configuration data (not an ORM access), so it is
    # safe to import from the live module inside a data migration.
    from workflow.definition_store import PRESET_SCHEMAS

    # Historical models expose plain (unscoped) managers, so no tenant context is
    # required and tenant_id must be supplied explicitly on create.
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
        ("workflow", "0003_reconcile_status_mirror"),
        # Reads Workspace at its latest schema.
        ("persistence", "0042_testcase_workflow_status"),
    ]

    operations = [
        migrations.RunPython(backfill_definitions, migrations.RunPython.noop),
    ]
