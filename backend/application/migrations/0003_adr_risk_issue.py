"""
Migration 0003: Adr, Risk, Issue tables.

COMP-AS-013 AdrService, COMP-AS-014 RiskService, COMP-AS-015 IssueService.
leaf_id : COMP-AS-013, COMP-AS-014, COMP-AS-015
req_id  : REQ-L1-029
"""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0002_webhook_models"),
    ]

    operations = [
        # ------------------------------------------------------------------ Adr
        migrations.CreateModel(
            name="Adr",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(max_length=10000)),
                ("context", models.TextField(max_length=5000, blank=True)),
                ("consequences", models.TextField(max_length=5000, blank=True)),
                (
                    "status",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("Draft", "Draft"),
                            ("In Review", "In Review"),
                            ("Approved", "Approved"),
                            ("Rejected", "Rejected"),
                            ("Superseded", "Superseded"),
                        ],
                        default="Draft",
                    ),
                ),
                ("version", models.IntegerField(default=1)),
                ("created_by", models.CharField(max_length=255, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "as_adr"},
        ),
        migrations.AddIndex(
            model_name="adr",
            index=models.Index(
                fields=["workspace_id", "status"], name="idx_adr_ws_status"
            ),
        ),
        migrations.AddIndex(
            model_name="adr",
            index=models.Index(
                fields=["tenant_id", "workspace_id"], name="idx_adr_tenant_ws"
            ),
        ),
        # ------------------------------------------------------------------ Risk
        migrations.CreateModel(
            name="Risk",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "category",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("technical", "Technical"),
                            ("operational", "Operational"),
                            ("organizational", "Organizational"),
                            ("business", "Business"),
                        ],
                        default="technical",
                    ),
                ),
                (
                    "probability",
                    models.CharField(
                        max_length=16,
                        choices=[
                            ("low", "Low (1)"),
                            ("medium", "Medium (2)"),
                            ("high", "High (3)"),
                        ],
                        default="low",
                    ),
                ),
                (
                    "impact",
                    models.CharField(
                        max_length=16,
                        choices=[
                            ("low", "Low (1)"),
                            ("medium", "Medium (2)"),
                            ("high", "High (3)"),
                        ],
                        default="low",
                    ),
                ),
                ("risk_score", models.IntegerField(default=1)),
                (
                    "severity",
                    models.CharField(
                        max_length=16,
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                        ],
                        default="low",
                    ),
                ),
                ("owner", models.CharField(max_length=255, blank=True)),
                ("mitigation_strategy", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("Identified", "Identified"),
                            ("Monitored", "Monitored"),
                            ("Mitigated", "Mitigated"),
                            ("Accepted", "Accepted"),
                            ("Closed", "Closed"),
                        ],
                        default="Identified",
                    ),
                ),
                ("version", models.IntegerField(default=1)),
                ("created_by", models.CharField(max_length=255, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "as_risk"},
        ),
        migrations.AddIndex(
            model_name="risk",
            index=models.Index(
                fields=["workspace_id", "status"], name="idx_risk_ws_status"
            ),
        ),
        migrations.AddIndex(
            model_name="risk",
            index=models.Index(
                fields=["tenant_id", "workspace_id"], name="idx_risk_tenant_ws"
            ),
        ),
        migrations.AddIndex(
            model_name="risk",
            index=models.Index(
                fields=["workspace_id", "severity"], name="idx_risk_ws_severity"
            ),
        ),
        migrations.AddIndex(
            model_name="risk",
            index=models.Index(
                fields=["workspace_id", "risk_score"], name="idx_risk_ws_score"
            ),
        ),
        # ---------------------------------------------------------------- Issue
        migrations.CreateModel(
            name="Issue",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "severity",
                    models.CharField(
                        max_length=16,
                        choices=[
                            ("critical", "Critical"),
                            ("high", "High"),
                            ("medium", "Medium"),
                            ("low", "Low"),
                        ],
                        default="medium",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("defect", "Defect"),
                            ("improvement", "Improvement"),
                            ("documentation", "Documentation"),
                            ("question", "Question"),
                        ],
                        default="defect",
                    ),
                ),
                ("assignee_id", models.UUIDField(null=True, blank=True)),
                ("assignee_changed_date", models.DateTimeField(null=True, blank=True)),
                ("due_date", models.DateTimeField(null=True, blank=True)),
                ("tags", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("Open", "Open"),
                            ("In Progress", "In Progress"),
                            ("Resolved", "Resolved"),
                            ("Closed", "Closed"),
                            ("Wontfix", "Wontfix"),
                        ],
                        default="Open",
                    ),
                ),
                ("version", models.IntegerField(default=1)),
                ("created_by", models.CharField(max_length=255, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "as_issue"},
        ),
        migrations.AddIndex(
            model_name="issue",
            index=models.Index(
                fields=["workspace_id", "status"], name="idx_issue_ws_status"
            ),
        ),
        migrations.AddIndex(
            model_name="issue",
            index=models.Index(
                fields=["workspace_id", "severity"], name="idx_issue_ws_severity"
            ),
        ),
        migrations.AddIndex(
            model_name="issue",
            index=models.Index(
                fields=["tenant_id", "workspace_id"], name="idx_issue_tenant_ws"
            ),
        ),
        migrations.AddIndex(
            model_name="issue",
            index=models.Index(
                fields=["workspace_id", "assignee_id"], name="idx_issue_ws_assignee"
            ),
        ),
    ]
