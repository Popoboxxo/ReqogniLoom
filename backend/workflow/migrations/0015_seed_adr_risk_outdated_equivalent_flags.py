from django.db import migrations

# SYSTEMAUDIT P1-16: the ``adr_default`` and ``risk_default`` presets declared
# terminal dead-end states ("Rejected"/"Superseded", "Closed") without the
# ``is_outdated_equivalent`` marker every sibling preset already carries on its
# own dead-end (``need_default`` -> "deprecated", ``ccb_approval`` -> "rejected",
# ``issue_default`` -> "Wontfix", ``interview_default`` -> "abandoned"). Without
# the flag, the automatic policies that consult it -- ``review.approve``'s
# gate-target fallback and ``AiDerivationService._auto_approve`` -- could pick a
# dead-end as an "approval" target (e.g. approving an already-Approved ADR moved
# it straight to "Superseded").
#
# definition_store.PRESET_SCHEMAS now carries the flags, so new workspaces get
# them the first time create_workspace_default_workflow seeds a
# GlobalWorkflowDefinition for (tenant, item_type, preset). Rows created before
# this change need this one-time backfill -- same shape as
# 0011_seed_auto_approve_target_flags / 0013_seed_issue_resolved_auto_approve_target.
OUTDATED_EQUIVALENT_BY_PRESET = {
    "adr_default": {
        "Rejected": {"is_outdated_equivalent": True},
        "Superseded": {"is_outdated_equivalent": True},
    },
    "risk_default": {
        "Closed": {"is_outdated_equivalent": True},
    },
}


def _merge_state_meta(workflow_json: dict, additions: dict) -> bool:
    """Merge *additions* into ``workflow_json["state_meta"]`` in place.

    Returns True when something actually changed (keeps the migration
    idempotent and avoids pointless UPDATEs). Existing entries are preserved:
    a state that already carries ``auto_approve_target`` keeps it and only
    gains the new key.
    """
    state_meta = workflow_json.get("state_meta", {})
    changed = False
    for state_name, extra in additions.items():
        existing_entry = state_meta.get(state_name, {})
        if existing_entry.get("is_outdated_equivalent") is True:
            continue
        state_meta[state_name] = {**existing_entry, **extra}
        changed = True
    if changed:
        workflow_json["state_meta"] = state_meta
    return changed


def seed_outdated_equivalent_flags(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    for global_def in GlobalWorkflowDefinition.objects.all():
        additions = OUTDATED_EQUIVALENT_BY_PRESET.get(global_def.preset)
        if not additions:
            continue
        workflow_json = global_def.workflow_json
        if not _merge_state_meta(workflow_json, additions):
            continue
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
        preset__in=list(OUTDATED_EQUIVALENT_BY_PRESET.keys()), is_customized=False
    ):
        additions = OUTDATED_EQUIVALENT_BY_PRESET.get(record.preset)
        if not additions:
            continue
        workflow_json = record.workflow_json
        if not _merge_state_meta(workflow_json, additions):
            continue
        record.workflow_json = workflow_json
        record.save(update_fields=["workflow_json"])


def noop_reverse(apps, schema_editor):
    """No-op: the seeded metadata is additive and harmless on an older build
    (``get_state_meta`` merges unknown keys away behind defaults)."""


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0014_testcase_status_lowercase"),
    ]

    operations = [
        migrations.RunPython(seed_outdated_equivalent_flags, noop_reverse),
    ]
