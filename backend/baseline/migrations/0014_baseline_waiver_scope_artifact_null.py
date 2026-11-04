"""C5 / #1412 — normalise BaselineGateWaiver.scope_artifact_id to NULL.

``""`` and ``NULL`` both meant "not bound to a document" and were counted as
two different states. Convert the legacy empty strings first, then make the
column nullable and forbid a new empty string at the DB level.
"""
from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


def _normalise_empty_to_null(apps, schema_editor):
    schema_editor.execute(
        """
        UPDATE bl_baseline_gate_waiver
        SET scope_artifact_id = NULL
        WHERE scope_artifact_id = ''
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("baseline", "0013_baseline_tag_rls_policy"),
        ("persistence", "0130_milestone_rls_policy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(_normalise_empty_to_null, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="baselinegatewaiver",
            name="scope_artifact_id",
            field=models.CharField(
                blank=True, default=None, max_length=64, null=True
            ),
        ),
        migrations.AddConstraint(
            model_name="baselinegatewaiver",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(scope_artifact_id__isnull=True)
                    | ~models.Q(scope_artifact_id="")
                ),
                name="ck_baseline_waiver_scope_artifact_not_empty",
            ),
        ),
    ]
