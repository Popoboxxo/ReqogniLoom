"""
ARCH-L1-005 WorkflowEngine — Initial migration.

leaf_id : ARCH-L1-005
req_id  : REQ-L2-WE-002, REQ-L2-WE-003, REQ-L2-WE-005, REQ-L2-WE-006

Creates:
  - we_engine_definition  (COMP-WE-001 WorkflowDefinitionStore)
  - we_item_state         (COMP-WE-003 StateLifecycleManager)
  - we_history_entry      (COMP-WE-003 StateLifecycleManager, append-only)
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Initial schema for the workflow app (ARCH-L1-005)."""

    initial = True

    dependencies = [
        ("persistence", "0001_initial"),
    ]

    operations = [
        # -- WorkflowEngineDefinition (COMP-WE-001) ---------------------------
        migrations.CreateModel(
            name="WorkflowEngineDefinition",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("item_type", models.CharField(max_length=128)),
                (
                    "preset",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("minimal", "Minimal"),
                            ("standard", "Standard"),
                            ("extended", "Extended"),
                        ],
                    ),
                ),
                ("workflow_json", models.JSONField(default=dict)),
                ("is_custom", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="workflowenginedefinition_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
            ],
            options={
                "db_table": "we_engine_definition",
                "base_manager_name": "unscoped",
            },
        ),
        migrations.AddConstraint(
            model_name="workflowenginedefinition",
            constraint=models.UniqueConstraint(
                fields=["tenant", "workspace_id", "item_type"],
                name="uq_wedef_tenant_ws_type",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowenginedefinition",
            index=models.Index(
                fields=["workspace_id", "item_type"],
                name="idx_we_def_workspace_type",
            ),
        ),
        # -- WorkflowItemState (COMP-WE-003) ----------------------------------
        migrations.CreateModel(
            name="WorkflowItemState",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("item_id", models.UUIDField(db_index=True)),
                ("item_type", models.CharField(max_length=128)),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("current_state", models.CharField(max_length=128)),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="item_states",
                        to="workflow.workflowenginedefinition",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="workflowitemstate_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
            ],
            options={
                "db_table": "we_item_state",
                "base_manager_name": "unscoped",
            },
        ),
        migrations.AddConstraint(
            model_name="workflowitemstate",
            constraint=models.UniqueConstraint(
                fields=["tenant", "item_id", "item_type"],
                name="uq_we_state_tenant_item",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowitemstate",
            index=models.Index(
                fields=["workspace_id", "current_state"],
                name="idx_we_state_workspace_state",
            ),
        ),
        # -- WorkflowHistoryEntry (COMP-WE-003) append-only -------------------
        migrations.CreateModel(
            name="WorkflowHistoryEntry",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("from_state", models.CharField(max_length=128)),
                ("to_state", models.CharField(max_length=128)),
                ("transitioned_by", models.CharField(max_length=255)),
                ("transitioned_at", models.DateTimeField()),
                ("change_reason", models.TextField(blank=True, default="")),
                (
                    "signature_seal",
                    models.CharField(max_length=255, blank=True, default=""),
                ),
                ("workspace_id", models.UUIDField(db_index=True)),
                (
                    "item_state",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="workflow.workflowitemstate",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="workflowhistoryentry_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
            ],
            options={
                "db_table": "we_history_entry",
                "base_manager_name": "unscoped",
            },
        ),
        migrations.AddIndex(
            model_name="workflowhistoryentry",
            index=models.Index(
                fields=["item_state", "transitioned_at"],
                name="idx_we_history_item_time",
            ),
        ),
    ]
