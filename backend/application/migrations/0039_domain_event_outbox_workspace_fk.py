"""C5 / #1403 — DomainEventOutbox.workspace becomes a real FK.

The column already exists; this migration only adds the FK constraint (and
deletes the legacy orphan rows that would violate it). ``db_column`` keeps the
name ``workspace_id``, so every existing filter and ``workspace_id=...`` write
keeps working through the FK's attname.
"""
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


def _delete_orphans(apps, schema_editor):
    """Remove outbox rows whose workspace no longer exists (#1403)."""
    schema_editor.execute(
        """
        DELETE FROM as_domain_event_outbox o
        WHERE NOT EXISTS (
            SELECT 1 FROM pl_workspace w WHERE w.id = o.workspace_id
        )
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("application", "0038_alter_domaineventoutbox_event_type_work_items"),
        ("persistence", "0130_milestone_rls_policy"),
    ]

    operations = [
        migrations.RunPython(_delete_orphans, migrations.RunPython.noop),
        migrations.RenameField(
            model_name="domaineventoutbox",
            old_name="workspace_id",
            new_name="workspace",
        ),
        migrations.AlterField(
            model_name="domaineventoutbox",
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
            model_name="domaineventoutbox",
            name="idx_outbox_ws",
        ),
        migrations.AddIndex(
            model_name="domaineventoutbox",
            index=models.Index(
                fields=["workspace", "created_at"], name="idx_outbox_ws"
            ),
        ),
    ]
