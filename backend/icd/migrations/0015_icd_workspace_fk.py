"""C5 / #1403 — Icd.workspace becomes a real FK.

The column already exists; this migration only adds the FK constraint (and
deletes the legacy orphan rows that would violate it). ``db_column`` keeps the
name ``workspace_id``.
"""
from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _delete_orphans(apps, schema_editor):
    """Remove ICDs whose workspace no longer exists (#1403)."""
    schema_editor.execute(
        """
        DELETE FROM icd_icd i
        WHERE NOT EXISTS (
            SELECT 1 FROM pl_workspace w WHERE w.id = i.workspace_id
        )
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("icd", "0014_icd_embedding_model"),
        ("persistence", "0130_milestone_rls_policy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(_delete_orphans, migrations.RunPython.noop),
        migrations.RenameField(
            model_name="icd",
            old_name="workspace_id",
            new_name="workspace",
        ),
        migrations.AlterField(
            model_name="icd",
            name="workspace",
            field=models.ForeignKey(
                db_column="workspace_id",
                db_index=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="persistence.workspace",
            ),
        ),
        migrations.RemoveIndex(
            model_name="icd",
            name="idx_icd_workspace",
        ),
        migrations.AddIndex(
            model_name="icd",
            index=models.Index(fields=["workspace"], name="idx_icd_workspace"),
        ),
    ]
