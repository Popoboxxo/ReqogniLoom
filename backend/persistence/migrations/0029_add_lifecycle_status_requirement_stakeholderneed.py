# Migration 0029: Add lifecycle_status field to Requirement and StakeholderNeed.
#
# REQ-006: Soft-Delete-Statusmodell — extends soft-delete to Requirement and
# StakeholderNeed entities. Entities with lifecycle_status='deleted' are excluded
# from normal list queries but remain in the database for audit trail purposes.
#
# This migration only adds columns with a safe default ('active'); no data is modified.
# Reversible: RemoveField restores original schema.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0028_add_lifecycle_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="requirement",
            name="lifecycle_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("outdated", "Outdated"),
                    ("deprecated", "Deprecated"),
                    ("deleted", "Deleted"),
                ],
                default="active",
                help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides requirement from normal views; hard-delete via admin only.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="stakeholderneed",
            name="lifecycle_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("outdated", "Outdated"),
                    ("deprecated", "Deprecated"),
                    ("deleted", "Deleted"),
                ],
                default="active",
                help_text="REQ-006: Soft-delete lifecycle. 'deleted' hides need from normal views; hard-delete via admin only.",
                max_length=16,
            ),
        ),
    ]
