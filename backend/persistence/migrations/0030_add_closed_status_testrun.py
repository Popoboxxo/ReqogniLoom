# Migration 0030: Add 'closed' status choice to TestRun.status.
#
# REQ-012: Closing a TestRun with zero recorded results previously left
# status at 'in_progress' (the vacuous "no results" fallback used by
# _compute_aggregate_status), so the "Close Run" action appeared to do
# nothing — the run reopened still showed 'in_progress' and the Close
# button reappeared. 'closed' gives close_test_run() a terminal status to
# fall back to when there are no TestRunResult rows.
#
# Choices-only change; no data migration needed, no existing rows affected.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0029_add_lifecycle_status_requirement_stakeholderneed"),
    ]

    operations = [
        migrations.AlterField(
            model_name="testrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("in_progress", "In Progress"),
                    ("passed", "Passed"),
                    ("failed", "Failed"),
                    ("partial", "Partial"),
                    ("closed", "Closed"),
                ],
                default="in_progress",
                max_length=32,
            ),
        ),
    ]
