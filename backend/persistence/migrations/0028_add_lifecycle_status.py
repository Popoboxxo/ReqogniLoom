# Migration 0028: Add lifecycle_status field to ArchitectureElement and GlossaryTerm.
#
# REQ-006: Soft-Delete-Statusmodell — replaces hard-delete for end-user operations.
# Elements with lifecycle_status='deleted' are excluded from normal list queries
# but remain in the database for audit trail purposes.
#
# This migration only adds columns with a safe default ('active'); no data is modified.
# Reversible: RemoveField restores original schema.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0027_add_prompt_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="architectureelement",
            name="lifecycle_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("outdated", "Outdated"),
                    ("deprecated", "Deprecated"),
                    ("deleted", "Deleted"),
                ],
                default="active",
                help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides element from normal views; hard-delete via admin only.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="glossaryterm",
            name="lifecycle_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("outdated", "Outdated"),
                    ("deprecated", "Deprecated"),
                    ("deleted", "Deleted"),
                ],
                default="active",
                help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides term from normal views; hard-delete via admin only.",
                max_length=16,
            ),
        ),
    ]
