from django.db import migrations

# GH-370: review.approve() on an Issue was falling back to the first
# approval-gated transition it found from the current state, which for the
# issue_default preset's "Open" state is "Open" -> "Wontfix" (the only
# approver/admin-gated hop out of "Open") -- a rejection endpoint, not an
# approval endpoint. definition_store.py now marks "Resolved" as the
# issue_default preset's auto_approve_target (same pattern as 0011's
# adr_default -> "Approved" / risk_default -> "Mitigated"). New workspaces
# pick this up automatically via PRESET_SCHEMAS the first time a
# GlobalWorkflowDefinition is seeded for (tenant, "Issue", "issue_default");
# existing rows created before this change need this one-time backfill,
# following the exact same pattern as 0011_seed_auto_approve_target_flags.
AUTO_APPROVE_TARGET_BY_PRESET = {
    "issue_default": {"Resolved": {"auto_approve_target": True}},
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
        ("workflow", "0012_backfill_goal_workflow_definitions"),
    ]

    operations = [
        migrations.RunPython(seed_auto_approve_targets, noop_reverse),
    ]
