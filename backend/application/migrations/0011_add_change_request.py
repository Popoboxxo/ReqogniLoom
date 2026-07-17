"""
Migration 0011: Add ChangeRequest entity (REQ-157).

Adds the ChangeRequest model to the application app so that proposed
changes can be tracked through a formal CCB (Configuration Control Board)
approval workflow powered by the WorkflowEngine (ccb_approval preset).

Strategy (additive, no destructive changes):
  - CreateModel ``ChangeRequest`` with CCB lifecycle fields.
  - No data migration required — new table, no existing rows.
  - Backward-compatible: no changes to existing models.

COMP-AS-017 ChangeRequestService.
leaf_id : COMP-AS-017
req_id  : REQ-157
"""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0010_risk_fmea_detection_owner_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChangeRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                    ),
                ),
                (
                    "workspace_id",
                    models.UUIDField(db_index=True),
                ),
                (
                    "tenant_id",
                    models.UUIDField(db_index=True),
                ),
                (
                    "title",
                    models.CharField(max_length=255),
                ),
                (
                    "description",
                    models.TextField(blank=True),
                ),
                (
                    "impact_assessment",
                    models.TextField(
                        blank=True,
                        help_text="Assessment of the impact this change will have on the system.",
                    ),
                ),
                (
                    "change_reason",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Reason for the change request "
                            "(required for submit and reject transitions)."
                        ),
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("draft", "Draft"),
                            ("submitted", "Submitted"),
                            ("under_review", "Under Review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("implemented", "Implemented"),
                        ],
                        default="draft",
                    ),
                ),
                (
                    "requestor_id",
                    models.UUIDField(
                        null=True,
                        blank=True,
                        help_text="UUID of the user who created this change request.",
                    ),
                ),
                (
                    "assigned_reviewer_id",
                    models.UUIDField(
                        null=True,
                        blank=True,
                        help_text="UUID of the user assigned as CCB reviewer.",
                    ),
                ),
                (
                    "version",
                    models.IntegerField(default=1),
                ),
                (
                    "created_by",
                    models.CharField(max_length=255, blank=True),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
            options={
                "db_table": "as_change_request",
            },
        ),
        migrations.AddIndex(
            model_name="changerequest",
            index=models.Index(
                fields=["workspace_id", "status"],
                name="idx_cr_ws_status",
            ),
        ),
        migrations.AddIndex(
            model_name="changerequest",
            index=models.Index(
                fields=["tenant_id", "workspace_id"],
                name="idx_cr_tenant_ws",
            ),
        ),
        migrations.AddIndex(
            model_name="changerequest",
            index=models.Index(
                fields=["workspace_id", "requestor_id"],
                name="idx_cr_ws_requestor",
            ),
        ),
    ]
