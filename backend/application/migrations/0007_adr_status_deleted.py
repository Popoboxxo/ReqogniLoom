# Migration 0007: Extend Adr.status choices to include 'Deleted' (REQ-006).
#
# REQ-006: Soft-Delete-Statusmodell — the 'Deleted' status is used by
# AdrService.delete_adr() to soft-delete ADRs without physical removal.
#
# This migration updates the ORM-level choices metadata only; no SQL DDL is
# emitted (PostgreSQL does not store CHECK constraints for CharField choices
# by default). Reversible: AlterField restores original choices.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0006_adr_artifact_backing"),
    ]

    operations = [
        migrations.AlterField(
            model_name="adr",
            name="status",
            field=models.CharField(
                choices=[
                    ("Draft", "Draft"),
                    ("In Review", "In Review"),
                    ("Approved", "Approved"),
                    ("Rejected", "Rejected"),
                    ("Superseded", "Superseded"),
                    ("Deleted", "Deleted"),
                ],
                default="Draft",
                max_length=32,
            ),
        ),
    ]
