"""Add dynamic custom_fields (JSONB) + GIN index to Artifact.

REQ-L2-AS-037: User-defined custom attributes on artifacts. custom_fields is a
flat key-value map stored as JSONB on the shared Artifact identity node, so a
single field/migration covers every domain entity (Requirement,
ArchitectureElement, StakeholderNeed, TestCase, ...).

The GIN index (pl_artifact_custom_fields_gin) is authored as RunSQL — mirroring
the full-text GIN indexes in 0002 — because it is not declared in Meta.indexes
(PostgreSQL-only, ADR-09). ``IF NOT EXISTS`` / ``IF EXISTS`` keep the migration
idempotent.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0022_add_uid_to_testcase_testrun'),
    ]

    operations = [
        migrations.AddField(
            model_name='artifact',
            name='custom_fields',
            field=models.JSONField(
                null=True,
                default=dict,
                blank=True,
                help_text=(
                    'REQ-L2-AS-037: User-defined custom attributes as a flat '
                    'key-value map. Keys: strings. Values: str, int, float, '
                    'bool, or null. A GIN index '
                    '(pl_artifact_custom_fields_gin) backs JSONB queries.'
                ),
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS pl_artifact_custom_fields_gin "
                "ON pl_artifact USING GIN (custom_fields);"
            ),
            reverse_sql=(
                "DROP INDEX IF EXISTS pl_artifact_custom_fields_gin;"
            ),
        ),
    ]
