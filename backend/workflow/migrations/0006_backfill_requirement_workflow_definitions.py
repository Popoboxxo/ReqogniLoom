"""REQ-170 — Backfill the Requirement WorkflowEngineDefinition.

Migration 0004 provisioned every non-Requirement entity type but intentionally
skipped ``Requirement``, on the assumption it was always provisioned at workspace
creation. That assumption does not hold for workspaces created before the
Requirement auto-provisioning was added: they own no
``WorkflowEngineDefinition`` row for ``item_type="Requirement"``. Without it,
``get_available_transitions`` degrades to a read-only, empty transition list and
``Requirement.status`` stays stuck at "draft" forever — the lazy state-init on the
read path cannot help because it needs an existing definition to initialise
against.

For every existing Workspace this migration provisions the Requirement workflow
using the workspace's own rigor tier. Unlike the fixed per-entity presets, the
Requirement preset is tier-dependent (minimal / standard / extended), matching
what ``WorkspaceService.create_workspace`` provisions at creation time. The tier
is resolved from the workspace's ``WorkspacePresetConfig.active_tier``, falling
back to the ``Workspace.preset`` JSON, then to "standard".

Idempotent via ``get_or_create`` on (workspace_id, item_type): a workspace that
already owns a Requirement definition (e.g. a customised one) is left untouched.

The reverse operation is a no-op: removing an auto-provisioned definition could
strand WorkflowItemState rows (definition FK is PROTECT) and is never desirable.
"""
from __future__ import annotations

from django.db import migrations

# Valid tier keys in workflow.definition_store.PRESET_SCHEMAS.
_VALID_TIERS = ("minimal", "standard", "extended")
_DEFAULT_TIER = "standard"


def _resolve_tier(ws, WorkspacePresetConfig) -> str:
    """Return the Requirement preset tier for *ws*.

    Prefers the authoritative ``WorkspacePresetConfig.active_tier``; falls back
    to the denormalised ``Workspace.preset`` JSON, then to a safe default.
    """
    config = WorkspacePresetConfig.objects.filter(workspace_id=ws.id).first()
    if config is not None and config.active_tier in _VALID_TIERS:
        return config.active_tier

    preset = getattr(ws, "preset", None)
    if isinstance(preset, dict):
        tier = preset.get("tier")
        if tier in _VALID_TIERS:
            return tier

    return _DEFAULT_TIER


def backfill_requirement_definitions(apps, schema_editor):
    Workspace = apps.get_model("persistence", "Workspace")
    WorkspacePresetConfig = apps.get_model("presets", "WorkspacePresetConfig")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    # PRESET_SCHEMAS is constant configuration data (not an ORM access), so it is
    # safe to import from the live module inside a data migration.
    from workflow.definition_store import PRESET_SCHEMAS

    # Historical models expose plain (unscoped) managers, so no tenant context is
    # required and tenant_id must be supplied explicitly on create.
    for ws in Workspace.objects.all():
        tier = _resolve_tier(ws, WorkspacePresetConfig)
        WorkflowEngineDefinition.objects.get_or_create(
            workspace_id=str(ws.id),
            item_type="Requirement",
            defaults={
                "preset": tier,
                "workflow_json": PRESET_SCHEMAS[tier],
                "is_custom": False,
                "tenant_id": ws.tenant_id,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0005_backfill_entity_item_states"),
        # Reads WorkspacePresetConfig.active_tier at its latest schema.
        ("presets", "0002_alter_workspacepresetconfig_options_and_more"),
        # Reads Workspace at its latest schema.
        ("persistence", "0042_testcase_workflow_status"),
    ]

    operations = [
        migrations.RunPython(
            backfill_requirement_definitions, migrations.RunPython.noop
        ),
    ]
