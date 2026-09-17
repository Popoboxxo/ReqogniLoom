"""Extend the AuditEntry ``op`` vocabulary for the remaining MCP tools (#626).

Follow-up to #573 (migration 0009): that fix left 17 further call-sites open
(``ai_derivation.py``'s 6 derive/suggest tools, ``review.py``'s
approve/reject/request_changes, ``tests.py``'s
outdate/reactivate/derive_from_requirement, ``architecture.py``'s
outdate/reactivate, ``diagram.py``'s outdate/reactivate, ``audit.py``'s
replay) passing ``operation=`` values outside the closed ``OP_CHOICES`` enum
to ``write_mcp_audit`` — ``full_clean()`` rejected them, the resulting
``ValidationError`` was swallowed, and the tool returned 200 while writing
zero audit rows.

16 of the 17 reuse an existing choice (same "reuse the REST pendant" remedy
as #573): the 6 ``ai_derivation.py`` tools and ``tests.py``'s
``derive_from_requirement`` each write exactly one audit entry for the ONE
entity they just created -> ``create``; ``outdate``/``reactivate`` on
``architecture.py``/``diagram.py``/``tests.py`` -> ``delete``/``transition``;
``review.py``'s ``approve``/``request_changes`` (``WorkflowFacade.transition()``)
-> ``transition``; ``review.py``'s ``reject`` (the ``outdate()`` escape
hatch) -> ``delete``. Only ``audit.py``'s DLQ replay has no REST pendant
(admin/ops machinery, not a CRUD op on a business entity) and gets the new
``events.replay`` choice below.

``choices`` is not a database-level constraint, so this AlterField is a no-op
against the partitioned ``AuditEntry`` table — it only realigns the migration
state with the model.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0009_alter_auditentry_op"),
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
                    ("events.replay", "Events Replay"),
                ],
                help_text="Performed operation: create, update, delete, transition.",
                max_length=32,
            ),
        ),
    ]
