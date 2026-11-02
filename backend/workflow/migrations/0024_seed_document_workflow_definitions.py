"""Plan F F2-T2 — seed the Document lifecycle workflow definitions.

Adds ``Document`` to every existing workspace (and to the tenant-wide global
defaults it inherits from), so a document created after the deploy reaches
"Entwurf" instead of having no ``WorkflowItemState`` row at all. New
workspaces get the same definition through
``application.workspace_provisioning`` (the canonical registry now carries
``("Document", "document_default")``).

The graph itself lives in ``workflow.definition_store.PRESET_SCHEMAS``
(``document_default``), the same source the runtime and every other seed
migration use.

Reverse: removes exactly the rows this seed creates, and refuses (rather than
silently deleting) as soon as a live ``WorkflowItemState`` or a customized
workspace definition shows the type is in use.
"""
from __future__ import annotations

import copy

from django.db import migrations

_ITEM_TYPE = "Document"
_PRESET = "document_default"


def seed_document_definitions(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    # Constant configuration data (not an ORM access) — safe to import from the
    # live module inside a data migration, same as 0004/0012.
    from workflow.definition_store import PRESET_SCHEMAS

    schema = PRESET_SCHEMAS[_PRESET]

    for ws in Workspace.objects.all():
        global_def, _ = GlobalWorkflowDefinition.objects.get_or_create(
            tenant_id=ws.tenant_id,
            item_type=_ITEM_TYPE,
            preset=_PRESET,
            defaults={"workflow_json": copy.deepcopy(schema)},
        )
        WorkflowEngineDefinition.objects.get_or_create(
            workspace_id=str(ws.id),
            item_type=_ITEM_TYPE,
            defaults={
                "preset": _PRESET,
                "workflow_json": copy.deepcopy(global_def.workflow_json),
                "is_custom": False,
                "is_customized": False,
                "tenant_id": ws.tenant_id,
                "source_global_id": global_def.id,
            },
        )


def unseed_document_definitions(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")

    if WorkflowItemState.objects.filter(item_type=_ITEM_TYPE).exists():
        raise RuntimeError(
            "Refusing to reverse workflow/0024: live Document workflow item "
            "states exist. Archive or migrate those documents first."
        )

    definitions = WorkflowEngineDefinition.objects.filter(item_type=_ITEM_TYPE)
    if definitions.filter(is_customized=True).exists():
        raise RuntimeError(
            "Refusing to reverse workflow/0024: a customized Document workflow "
            "definition exists (workspace-local changes would be lost)."
        )
    definitions.delete()
    GlobalWorkflowDefinition.objects.filter(
        item_type=_ITEM_TYPE, preset=_PRESET
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0023_we_item_state_workspace_fk_cascade"),
    ]

    operations = [
        migrations.RunPython(
            seed_document_definitions, unseed_document_definitions
        ),
    ]
