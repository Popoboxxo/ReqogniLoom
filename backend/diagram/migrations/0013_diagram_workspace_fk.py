"""C5 / #1403 — Diagram.workspace becomes a real FK.

Legacy rows with ``workspace_id IS NULL`` stay NULL; non-null orphan rows are
deleted before the constraint is added. ``db_column`` keeps the name
``workspace_id``.
"""
from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _delete_orphans(apps, schema_editor):
    """Remove Diagrams whose workspace no longer exists (#1403)."""
    schema_editor.execute(
        """
        DELETE FROM diagram_diagram d
        WHERE d.workspace_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM pl_workspace w WHERE w.id = d.workspace_id
          )
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("diagram", "0012_drop_diagram_version"),
        ("persistence", "0130_milestone_rls_policy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(_delete_orphans, migrations.RunPython.noop),
        migrations.RenameField(
            model_name="diagram",
            old_name="workspace_id",
            new_name="workspace",
        ),
        migrations.AlterField(
            model_name="diagram",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                db_column="workspace_id",
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="persistence.workspace",
            ),
        ),
        migrations.RemoveIndex(
            model_name="diagram",
            name="idx_diagram_workspace",
        ),
        migrations.AddIndex(
            model_name="diagram",
            index=models.Index(fields=["workspace"], name="idx_diagram_workspace"),
        ),
    ]
