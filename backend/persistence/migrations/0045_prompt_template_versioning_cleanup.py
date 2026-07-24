# Phase 4 — PromptTemplate versioning, part 3/3: schema cleanup.
#
# Now that 0044's data migration has left no old-shape rows and no NULLs in
# the new columns, tighten name/content to NOT NULL, drop the 3 obsolete slot
# fields, switch ``version`` to PositiveIntegerField, and add the
# (tenant, workspace_id, name) lookup index.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0044_prompt_template_versioning_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="prompttemplate",
            name="need_to_sysreq",
        ),
        migrations.RemoveField(
            model_name="prompttemplate",
            name="sysreq_to_arch_assign",
        ),
        migrations.RemoveField(
            model_name="prompttemplate",
            name="sysreq_decompose_next_level",
        ),
        migrations.AlterField(
            model_name="prompttemplate",
            name="name",
            field=models.CharField(
                max_length=100,
                help_text="Template identifier, e.g. 'need_to_sysreq' (open-ended, not an enum).",
            ),
        ),
        migrations.AlterField(
            model_name="prompttemplate",
            name="content",
            field=models.TextField(help_text="Prompt template body."),
        ),
        migrations.AlterField(
            model_name="prompttemplate",
            name="version",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Version number within the (tenant, workspace_id, name) scope; starts at 1.",
            ),
        ),
        migrations.AddIndex(
            model_name="prompttemplate",
            index=models.Index(
                fields=["tenant", "workspace_id", "name"],
                name="ix_prompt_template_scope",
            ),
        ),
    ]
