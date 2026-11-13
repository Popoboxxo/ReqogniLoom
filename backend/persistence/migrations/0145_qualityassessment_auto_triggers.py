"""Issue #1578: the automatic quality-assessment triggers.

Choices-only change: ``pl_quality_assessment.trigger`` is a loose CharField,
so no data rewrite is needed and no row becomes invalid. The migration exists
so ``makemigrations --check`` stays green and the documented choices match the
column.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0144_normalize_testcase_steps"),
    ]

    operations = [
        migrations.AlterField(
            model_name="qualityassessment",
            name="trigger",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("mcp", "MCP"),
                    ("auto_transition", "Auto (transition)"),
                    ("auto_create", "Auto (create)"),
                    ("auto_periodic", "Auto (periodic)"),
                ],
                max_length=16,
            ),
        ),
    ]
