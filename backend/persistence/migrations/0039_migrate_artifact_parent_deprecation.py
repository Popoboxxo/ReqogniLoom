"""Migrate the Artifact.parent deprecation help_text (REQ-152).

REQ-152 added a deprecation note to Artifact.parent's ``help_text`` in
persistence/models.py but never generated the accompanying migration, leaving
the model state and the migration graph out of sync (``makemigrations --check``
reported a pending change). This migration records that docs-only field change.

Schema-neutral: ``help_text`` is Python/state metadata only — no DDL is emitted
and no data is touched. Reversible by definition (the AlterField restores the
previous help_text on reverse).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0038_workspace_default_link_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='artifact',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Deprecated: use 'derives-from' TraceLink for hierarchy "
                    "instead. Populated only via the generic ArtifactService "
                    "write path; RequirementService/StakeholderNeedService/"
                    "AdrService/... leave this NULL and rely on TraceLinks. "
                    "Kept for backward compatibility only — do not add new "
                    "dependencies on it."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='children',
                to='persistence.artifact',
            ),
        ),
    ]
