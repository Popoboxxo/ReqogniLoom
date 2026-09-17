from django.db import migrations

STATE_META_BY_PRESET = {
    "standard": {"deprecated": {"is_outdated_equivalent": True}},
    "extended": {"deprecated": {"is_outdated_equivalent": True}},
    "ccb_approval": {"rejected": {"is_outdated_equivalent": True}},
    "need_default": {"deprecated": {"is_outdated_equivalent": True}},
    "architecture_default": {"deprecated": {"is_outdated_equivalent": True}},
    "testcase_default": {"Deprecated": {"is_outdated_equivalent": True}},
    "issue_default": {"Wontfix": {"is_outdated_equivalent": True}},
    "diagram_default": {"deprecated": {"is_outdated_equivalent": True}},
    "glossary_term_default": {"deprecated": {"is_outdated_equivalent": True}},
    "icd_default": {"deprecated": {"is_outdated_equivalent": True}},
}


def seed_state_meta(apps, schema_editor):
    GlobalWorkflowDefinition = apps.get_model("workflow", "GlobalWorkflowDefinition")
    WorkflowEngineDefinition = apps.get_model("workflow", "WorkflowEngineDefinition")

    for global_def in GlobalWorkflowDefinition.objects.all():
        state_meta = STATE_META_BY_PRESET.get(global_def.preset)
        if not state_meta:
            continue
        workflow_json = global_def.workflow_json
        workflow_json["state_meta"] = state_meta
        global_def.workflow_json = workflow_json
        global_def.save(update_fields=["workflow_json"])

        # Propagate to every non-customized derived definition, same as
        # GlobalWorkflowDefinitionStore._propagate does at runtime.
        WorkflowEngineDefinition.objects.filter(
            source_global_id=global_def.id, is_customized=False
        ).update(workflow_json=workflow_json)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0009_backfill_global_workflow_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_state_meta, noop_reverse),
    ]
