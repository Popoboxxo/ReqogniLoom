# Phase 4 — PromptTemplate versioning (REQ-L2-PT-001 follow-up, docs/superpowers/
# plans/2026-07-24-phase4-prompt-templates.md, Task 1), part 1/3: schema-add.
#
# Adds the new columns as nullable (existing singleton rows only have the 3
# old slot TextFields, so both shapes must be valid to coexist momentarily)
# and drops the old tenant-only singleton constraint so the data migration in
# 0044 can create more than one row per tenant.
#
# Split into 3 migrations (schema-add / data / schema-cleanup) rather than one
# combined migration because Postgres raises "cannot ALTER TABLE ... because
# it has pending trigger events" when a RunPython DELETE and a later
# RemoveField/AlterField on the same table share one transaction — each
# Django migration is its own transaction, so splitting sidesteps it.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0042_testcase_workflow_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="prompttemplate",
            name="name",
            field=models.CharField(
                max_length=100,
                null=True,
                blank=True,
                help_text="Template identifier, e.g. 'need_to_sysreq' (open-ended, not an enum).",
            ),
        ),
        migrations.AddField(
            model_name="prompttemplate",
            name="content",
            field=models.TextField(
                null=True, blank=True, help_text="Prompt template body."
            ),
        ),
        migrations.AddField(
            model_name="prompttemplate",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Whether this version is the active one for its (tenant, workspace_id, name) scope.",
            ),
        ),
        migrations.AddField(
            model_name="prompttemplate",
            name="workspace_id",
            field=models.UUIDField(
                null=True,
                blank=True,
                help_text="Workspace override scope. NULL means tenant-wide default.",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="prompttemplate",
            name="uq_prompt_template_tenant",
        ),
    ]
