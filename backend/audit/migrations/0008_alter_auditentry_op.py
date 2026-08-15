"""Extend the AuditEntry ``op`` vocabulary for MCP admin/user/permissions tools (#539).

``write_mcp_audit`` (mcp_server/tools/base.py) passed tool names such as
``"user.create"``, ``"admin.restore"``, ``"permissions.set_rule"`` straight
through as ``AuditEntry.op``. ``op`` is a closed ``choices`` enum validated by
``full_clean()`` inside ``AuditLogWriter.write``; a value outside the enum
raises ``ValidationError`` there. Unlike ``ServiceBase._audit`` (which
re-raises), ``write_mcp_audit`` only logs that exception at ERROR level and
swallows it — so the MCP tool call still reported ``success=True`` while
writing zero audit rows for these sensitive admin/user/permissions
operations.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0007_alter_auditentry_op"),
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
                ],
                help_text="Performed operation: create, update, delete, transition.",
                max_length=32,
            ),
        ),
    ]
