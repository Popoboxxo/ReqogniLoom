"""Plan F F3-T2 — seed the tier-dependent WorkItem workflow definitions.

Every existing workspace gets the ``work_item_<tier>`` lifecycle that matches
its rigor tier (``WorkspacePresetConfig.active_tier``, falling back to the
``Workspace.preset`` JSON and then ``standard``), so a work item created after
the deploy reaches ``todo`` instead of having no ``WorkflowItemState`` row.
New workspaces get the same definition through
``application.workspace_provisioning`` (which now also carries a
``work_item_preset`` parameter).

The migration additionally seeds all three tenant-wide globals
(``work_item_minimal``/``work_item_standard``/``work_item_extended``) for every
tenant that owns a workspace, mirroring the Global Workflow Defaults tab's
"all tiers visible" rule (REQ-178). The graphs themselves live in
``workflow.definition_store.PRESET_SCHEMAS``.

Reverse: removes exactly the rows this seed creates, and refuses (rather than
silently deleting) as soon as a live ``WorkflowItemState`` or a customized
workspace definition shows the type is in use.
"""
from __future__ import annotations

import copy

from django.db import migrations

_ITEM_TYPE = "WorkItem"

#: Rigor tier -> WorkItem preset key. Frozen on purpose: a released data
#: migration must not follow a future change to the runtime registry.
_PRESET_BY_TIER = {
    "minimal": "work_item_minimal",
    "standard": "work_item_standard",
    "extended": "work_item_extended",
}
_DEFAULT_TIER = "standard"


def _resolve_tier(ws, WorkspacePresetConfig) -> str:
    """Return the WorkItem preset tier for *ws* (same rule as 0006)."""
    config = WorkspacePresetConfig.objects.filter(workspace_id=ws.id).first()
    if config is not None and config.active_tier in _PRESET_BY_TIER:
        return config.active_tier

    preset = getattr(ws, "preset", None)
    if isinstance(preset, dict):
        tier = preset.get("tier")
        if tier in _PRESET_BY_TIER:
            return tier

    return _DEFAULT_TIER


def seed_work_item_definitions(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    WorkspacePresetConfig = apps.get_model("presets", "WorkspacePresetConfig")
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    # Constant configuration data (not an ORM access) — safe to import from the
    # live module inside a data migration, same as 0004/0012/0024.
    from workflow.definition_store import PRESET_SCHEMAS

    workspaces = list(Workspace.objects.all())
    tenant_ids = {ws.tenant_id for ws in workspaces}

    # 1. All three tenant-wide globals per tenant, so the Global Workflow
    #    Defaults tab can browse every tier and a workspace definition always
    #    has a global to inherit from.
    for tenant_id in tenant_ids:
        for preset in _PRESET_BY_TIER.values():
            GlobalWorkflowDefinition.objects.get_or_create(
                tenant_id=tenant_id,
                item_type=_ITEM_TYPE,
                preset=preset,
                defaults={"workflow_json": copy.deepcopy(PRESET_SCHEMAS[preset])},
            )

    # 2. One workspace definition per workspace, on its own rigor tier.
    for ws in workspaces:
        preset = _PRESET_BY_TIER[_resolve_tier(ws, WorkspacePresetConfig)]
        global_def = GlobalWorkflowDefinition.objects.get(
            tenant_id=ws.tenant_id,
            item_type=_ITEM_TYPE,
            preset=preset,
        )
        WorkflowEngineDefinition.objects.get_or_create(
            workspace_id=str(ws.id),
            item_type=_ITEM_TYPE,
            defaults={
                "preset": preset,
                "workflow_json": copy.deepcopy(global_def.workflow_json),
                "is_custom": False,
                "is_customized": False,
                "tenant_id": ws.tenant_id,
                "source_global_id": global_def.id,
            },
        )


def unseed_work_item_definitions(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")
    WorkflowItemState = apps.get_model("workflow", "WorkflowItemState")

    if WorkflowItemState.objects.filter(item_type=_ITEM_TYPE).exists():
        raise RuntimeError(
            "Refusing to reverse workflow/0025: live WorkItem workflow item "
            "states exist. Archive or migrate those work items first."
        )

    definitions = WorkflowEngineDefinition.objects.filter(item_type=_ITEM_TYPE)
    if definitions.filter(is_customized=True).exists():
        raise RuntimeError(
            "Refusing to reverse workflow/0025: a customized WorkItem workflow "
            "definition exists (workspace-local changes would be lost)."
        )
    definitions.delete()
    GlobalWorkflowDefinition.objects.filter(item_type=_ITEM_TYPE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0024_seed_document_workflow_definitions"),
        # Reads WorkspacePresetConfig.active_tier at its latest schema.
        ("presets", "0002_alter_workspacepresetconfig_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_work_item_definitions, unseed_work_item_definitions
        ),
    ]
