"""Extend the AuditEntry ``op`` vocabulary (GitHub #265).

``workspace.delete``, ``clone`` and ``assign`` are emitted by
``ServiceBase._audit`` but were missing from ``OP_CHOICES``; ``full_clean``
in ``AuditLogWriter.write`` rejected them, which surfaced as a 500 on
``POST /api/v1/workspaces/{id}/delete/``.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0006_alter_auditentry_op"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditentry",
            name="op",
            field=models.CharField(
                choices=[
                    ("create", "Create"),
                    ("update", "Update"),
                    ("delete", "Delete"),
                    ("transition", "Transition"),
                    ("baseline.create", "Baseline Create"),
                    ("workspace.close", "Workspace Close"),
                    ("workspace.reactivate", "Workspace Reactivate"),
                    ("workspace.delete", "Workspace Delete"),
                    ("clone", "Clone"),
                    ("assign", "Assign"),
                ],
                help_text="Performed operation: create, update, delete, transition.",
                max_length=32,
            ),
        ),
    ]
