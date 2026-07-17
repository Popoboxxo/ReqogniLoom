"""Add ``test_type`` to TestCase and backfill it from artifact_type (B6a/B6b).

B6a: promotes the test type from an ``Artifact.artifact_type`` string prefix
(e.g. "TestCase:System") to a first-class, nullable TestCase column. Additive
and backward-compatible — existing rows default to ``test_type = NULL`` before
the data migration runs.

B6b: extends ``Requirement.verification_method`` choices with "Demonstration".
Choices are Python-level state metadata; Django records them via AlterField but
no DDL is emitted (the column definition is unchanged), so this is schema-neutral.

Backfill strategy: map the legacy ``artifact_type`` prefix onto ``test_type``
with set-based UPDATEs (one statement per type, no per-row loop). Artifacts whose
``artifact_type`` does not start with "TestCase:" keep ``test_type = NULL``.

Reversibility:
- The data migration reverse sets ``test_type = NULL`` for all rows, restoring
  the pre-backfill state.
- The AddField reverse drops the column; the AlterField reverse restores the
  previous choice set. No data loss (the legacy ``artifact_type`` prefix remains
  the source of truth and is never modified by this migration).
"""

from django.db import migrations, models


# Legacy artifact_type prefix -> canonical test_type value.
_ARTIFACT_TYPE_TO_TEST_TYPE = {
    'TestCase:System': 'system',
    'TestCase:Integration': 'integration',
    'TestCase:Unit': 'unit',
    'TestCase:Inspection': 'inspection',
    'TestCase:Analysis': 'analysis',
    'TestCase:Demonstration': 'demonstration',
}


def backfill_test_type(apps, schema_editor):
    """Set test_type from the legacy artifact_type prefix (set-based)."""
    TestCase = apps.get_model('persistence', 'TestCase')
    for artifact_type, test_type in _ARTIFACT_TYPE_TO_TEST_TYPE.items():
        TestCase.objects.filter(
            artifact__artifact_type=artifact_type
        ).update(test_type=test_type)


def clear_test_type(apps, schema_editor):
    """Reverse: restore the pre-backfill state (all test_type = NULL)."""
    TestCase = apps.get_model('persistence', 'TestCase')
    TestCase.objects.update(test_type=None)


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0040_add_requirement_level'),
    ]

    operations = [
        migrations.AddField(
            model_name='testcase',
            name='test_type',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=20,
                choices=[
                    ('system', 'System'),
                    ('integration', 'Integration'),
                    ('unit', 'Unit'),
                    ('inspection', 'Inspection'),
                    ('analysis', 'Analysis'),
                    ('demonstration', 'Demonstration'),
                ],
                help_text=(
                    "B6a: Test type (system/integration/unit/inspection/"
                    "analysis/demonstration). Replaces the deprecated "
                    "'TestCase:<Type>' artifact_type prefix. NULL when not "
                    "derivable."
                ),
            ),
        ),
        migrations.AlterField(
            model_name='requirement',
            name='verification_method',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=128,
                choices=[
                    ('Test', 'Test'),
                    ('Review', 'Review'),
                    ('Analysis', 'Analysis'),
                    ('Inspection', 'Inspection'),
                    ('Demonstration', 'Demonstration'),
                ],
                help_text='Verification method (visible only for SyReq)',
            ),
        ),
        migrations.RunPython(backfill_test_type, clear_test_type),
    ]
