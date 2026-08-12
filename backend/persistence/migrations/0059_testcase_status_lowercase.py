"""GH-453 — lowercase the ``TestCase.status`` choices and default.

Schema-only companion to ``workflow/0014_testcase_status_lowercase``, which
rewrites the *data* (this app's ``pl_testcase.status`` column plus the
WorkflowEngine tables that feed it). Django stores ``choices``/``default`` in
the migration state only — neither is enforced by PostgreSQL — so this
operation is a no-op against the database and is safe to apply before the data
migration runs.

Split out rather than folded into the data migration because the ordering
matters for readability, not for correctness: ``makemigrations`` must not
report a pending model change once GH-453 has landed.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0058_workspace_description"),
    ]

    operations = [
        migrations.AlterField(
            model_name="testcase",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("ready", "Ready"),
                    ("approved", "Approved"),
                    ("deprecated", "Deprecated"),
                ],
                default="draft",
                max_length=32,
            ),
        ),
    ]
