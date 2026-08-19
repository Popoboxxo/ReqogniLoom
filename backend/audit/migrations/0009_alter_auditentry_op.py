"""Extend the AuditEntry ``op`` vocabulary for the AI tool ops (GitHub #573).

``requirement.decompose`` / ``requirement.validate`` /
``requirement.check_consistency`` passed ``"decompose"`` / ``"validate"`` /
``"check_consistency"`` to ``write_mcp_audit``. None of those were declared
choices, so ``full_clean`` in ``AuditLogWriter.write`` rejected them — and
unlike ``ServiceBase._audit`` (#265) ``write_mcp_audit`` swallows that
``ValidationError``, so the tool returned 200 while writing zero audit rows.

The three LLM analyses get declared ``ai.*`` choices here. The lifecycle
tools (``requirement.outdate|reactivate``, ``needs.outdate|reactivate``) are
fixed without a vocabulary change: they now emit the op their REST pendant
already writes (``delete`` / ``transition``).

``choices`` is not a database-level constraint, so this AlterField is a no-op
against the partitioned ``AuditEntry`` table — it only realigns the migration
state with the model.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0008_alter_auditentry_op"),
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
                    ("ai.decompose", "AI Decompose"),
                    ("ai.validate", "AI Validate"),
                    ("ai.check_consistency", "AI Consistency Check"),
                ],
                help_text="Performed operation: create, update, delete, transition.",
                max_length=32,
            ),
        ),
    ]
