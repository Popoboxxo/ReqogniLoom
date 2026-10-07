"""audit — declare the ``baseline.purge`` operation (GH-1199).

``AuditLogWriter.write`` validates ``AuditEntry.op`` against ``OP_CHOICES`` via
``full_clean``, and ``ServiceBase._audit`` re-raises the resulting
``ValidationError`` — an undeclared operation aborts the whole transaction with
a 500 *after* the business mutation (see the NOTE in ``audit/models.py``, #265).

GH-1199 adds the admin-only, audited baseline purge: the one sanctioned removal
path for an append-only baseline. It is its own governed act, so it gets its own
op instead of riding along under the generic ``delete`` — "who removed this
governance artifact" must be answerable without reconstructing the intent from
the details blob.

Choices-only change: ``op`` stays ``varchar(32)``, so this alters no column and
no existing row. The ratchet ``audit/tests/test_op_vocabulary.py`` fails if the
literal ever leaves ``OP_CHOICES`` again.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0014_auditentry_details"),
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
                    ("admin.backup_create", "Admin Backup Create"),
                    ("admin.restore", "Admin Restore"),
                    ("permissions.set_rule", "Permissions Set Rule"),
                    ("permissions.revoke", "Permissions Revoke"),
                    ("user.create", "User Create"),
                    ("user.assign_role", "User Assign Role"),
                    ("user.deactivate", "User Deactivate"),
                    ("user.activate", "User Activate"),
                    ("user.suspend_role", "User Suspend Role"),
                    ("user.reactivate_role", "User Reactivate Role"),
                    ("user.assign_tenant_admin", "User Assign Tenant Admin"),
                    ("user.revoke_tenant_admin", "User Revoke Tenant Admin"),
                    ("ai.decompose", "AI Decompose"),
                    ("ai.validate", "AI Validate"),
                    ("ai.check_consistency", "AI Consistency Check"),
                    ("attribute_migration.apply", "Attribute Migration Apply"),
                    ("attribute_migration.rollback", "Attribute Migration Rollback"),
                    ("events.replay", "Events Replay"),
                    ("baseline.waiver_create", "Baseline Waiver Create"),
                    ("baseline.purge", "Baseline Purge"),
                ],
                help_text="Performed operation: create, update, delete, transition.",
                max_length=32,
            ),
        ),
    ]
