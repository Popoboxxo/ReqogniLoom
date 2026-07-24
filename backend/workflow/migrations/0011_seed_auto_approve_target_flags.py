from django.db import migrations

# Phase 3: entity-aware auto_approve_target metadata, additive on top of the
# state_meta entries already seeded by 0010 (is_outdated_equivalent). New
# workspaces get this automatically via PRESET_SCHEMAS (definition_store.py)
# the first time create_workspace_default_workflow seeds a
# GlobalWorkflowDefinition for a (tenant, item_type, preset); existing rows
# created before this change need this one-time backfill, same pattern as
# 0010_seed_state_meta_outdated_flags.
AUTO_APPROVE_TARGET_BY_PRESET = {
    "adr_default": {"Approved": {"auto_approve_target": True}},
    "risk_default": {"Mitigated": {"auto_approve_target": True}},
}


def seed_auto_approve_targets(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    for global_def in GlobalWorkflowDefinition.objects.all():
        additions = AUTO_APPROVE_TARGET_BY_PRESET.get(global_def.preset)
        if not additions:
            continue
        workflow_json = global_def.workflow_json
        state_meta = workflow_json.get("state_meta", {})
        changed = False
        for state_name, extra in additions.items():
            existing_entry = state_meta.get(state_name, {})
            if existing_entry.get("auto_approve_target") is True:
                continue
            state_meta[state_name] = {**existing_entry, **extra}
            changed = True
        if not changed:
            continue
        workflow_json["state_meta"] = state_meta
        global_def.workflow_json = workflow_json
        global_def.save(update_fields=["workflow_json"])

        # Propagate to every non-customized derived definition, same as
        # GlobalWorkflowDefinitionStore._propagate does at runtime.
        WorkflowEngineDefinition.objects.filter(
            source_global_id=global_def.id, is_customized=False
        ).update(workflow_json=workflow_json)

    # Workspace rows with no linked global (pre-REQ-178 data, or is_customized
    # rows that diverged before this change) still use the same preset
    # defaults and are not considered "customized" away from this metadata,
    # so backfill them directly by preset name too.
    for record in WorkflowEngineDefinition.objects.filter(
        preset__in=list(AUTO_APPROVE_TARGET_BY_PRESET.keys()), is_customized=False
    ):
        additions = AUTO_APPROVE_TARGET_BY_PRESET.get(record.preset)
        if not additions:
            continue
        workflow_json = record.workflow_json
        state_meta = workflow_json.get("state_meta", {})
        changed = False
        for state_name, extra in additions.items():
            existing_entry = state_meta.get(state_name, {})
            if existing_entry.get("auto_approve_target") is True:
                continue
            state_meta[state_name] = {**existing_entry, **extra}
            changed = True
        if not changed:
            continue
        workflow_json["state_meta"] = state_meta
        record.workflow_json = workflow_json
        record.save(update_fields=["workflow_json"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0010_seed_state_meta_outdated_flags"),
    ]

    operations = [
        migrations.RunPython(seed_auto_approve_targets, noop_reverse),
    ]
