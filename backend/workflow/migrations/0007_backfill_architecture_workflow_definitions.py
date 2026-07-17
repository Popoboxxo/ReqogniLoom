"""REQ-171 — Backfill the ArchitectureElement WorkflowEngineDefinition.

ArchitectureElement was never registered for the universal workflow engine
(REQ-165/166): no ``architecture_default`` preset existed and no
WorkflowEngineDefinition was provisioned, so the ArchitectureForm had no
lifecycle editor. This migration provisions the fixed-preset
``architecture_default`` workflow for every existing Workspace, matching what
``WorkspaceService.create_workspace`` now provisions at creation time for new
workspaces.

ArchitectureElement has no denormalized ``status`` mirror column and is not
wired into ``_STATUS_MIRROR_MODELS``; the workflow state lives solely in
WorkflowItemState, lazily initialised on the first transitions read once this
definition exists.

Idempotent via ``get_or_create`` on (workspace_id, item_type): a workspace that
already owns an ArchitectureElement definition is left untouched.

The reverse operation is a no-op: removing an auto-provisioned definition could
strand WorkflowItemState rows (definition FK is PROTECT) and is never desirable.
"""
from __future__ import annotations

from django.db import migrations

_ITEM_TYPE = "ArchitectureElement"
_PRESET_KEY = "architecture_default"


def backfill_architecture_definitions(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    # PRESET_SCHEMAS is constant configuration data (not an ORM access), so it is
    # safe to import from the live module inside a data migration.
    from workflow.definition_store import PRESET_SCHEMAS

    # Historical models expose plain (unscoped) managers, so no tenant context is
    # required and tenant_id must be supplied explicitly on create.
    for ws in Workspace.objects.all():
        WorkflowEngineDefinition.objects.get_or_create(
            workspace_id=str(ws.id),
            item_type=_ITEM_TYPE,
            defaults={
                "preset": _PRESET_KEY,
                "workflow_json": PRESET_SCHEMAS[_PRESET_KEY],
                "is_custom": False,
                "tenant_id": ws.tenant_id,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0006_backfill_requirement_workflow_definitions"),
        ("persistence", "0042_testcase_workflow_status"),
    ]

    operations = [
        migrations.RunPython(
            backfill_architecture_definitions, migrations.RunPython.noop
        ),
    ]
