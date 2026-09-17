"""Extend the AuditEntry ``op`` vocabulary for the multi-user management
tools (Fix Round 1, C-1).

``UsersToolGroup``'s ``user.activate``/``.suspend_role``/``.reactivate_role``/
``.assign_tenant_admin``/``.revoke_tenant_admin`` handlers (multi-user
management Task 9) all called ``write_mcp_audit(operation=...)`` with these
five operation strings without ever adding them to ``OP_CHOICES`` — the same
silent-drop failure mode as #539 (``full_clean()`` rejects the undeclared
value, ``write_mcp_audit`` swallows the resulting ``ValidationError`` and
only logs it, so all five tools reported ``success=True`` while writing zero
audit rows, including granting/revoking tenant-admin, the highest-privilege
operation on this whole surface).

``choices`` is not a database-level constraint, so this AlterField is a no-op
against the partitioned ``AuditEntry`` table — it only realigns the migration
state with the model.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0010_alter_auditentry_op"),
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
                    ("events.replay", "Events Replay"),
                ],
                help_text="Performed operation: create, update, delete, transition.",
                max_length=32,
            ),
        ),
    ]
