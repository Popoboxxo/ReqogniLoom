"""
COMP-PL-004 SchemaMigrationEngine — initial schema for all 13 entities.

Requirements:
- REQ-L2-PL-006 / REQ-L3-PL004-001 (complete, gapless migration history)
- REQ-L3-PL004-002 (reverse path — provided automatically by CreateModel/AddIndex)
- REQ-L2-PL-004 (all 13 entities), REQ-L2-PL-009 (FK on_delete), REQ-L2-PL-005 (audit)

Hand-authored to match persistence/models.py. ``makemigrations --check`` must
report no changes against this migration.
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"db_table": "pl_tenant"},
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("username", models.CharField(max_length=150, unique=True)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="users", to="persistence.tenant")),
            ],
            options={"db_table": "pl_user"},
        ),
        migrations.AddField(
            model_name="tenant",
            name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="modified_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user"),
        ),
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("name", models.CharField(max_length=150)),
                ("permissions", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="role_set", to="persistence.tenant")),
            ],
            options={"db_table": "pl_role", "base_manager_name": "unscoped"},
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.UniqueConstraint(fields=("tenant", "name"), name="uq_role_tenant_name"),
        ),
        migrations.CreateModel(
            name="Workspace",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("name", models.CharField(max_length=255)),
                ("preset", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="workspace_set", to="persistence.tenant")),
            ],
            options={"db_table": "pl_workspace", "base_manager_name": "unscoped"},
        ),
        migrations.CreateModel(
            name="Artifact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("artifact_type", models.CharField(max_length=64)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="artifact_set", to="persistence.tenant")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="persistence.artifact")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="artifacts", to="persistence.workspace")),
            ],
            options={"db_table": "pl_artifact", "base_manager_name": "unscoped"},
        ),
        migrations.AddIndex(
            model_name="artifact",
            index=models.Index(fields=["parent"], name="idx_artifact_parent_btree"),
        ),
        migrations.CreateModel(
            name="Requirement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("title", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True)),
                ("category", models.CharField(blank=True, max_length=64)),
                ("status", models.CharField(default="draft", max_length=64)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="requirement_set", to="persistence.tenant")),
                ("artifact", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="requirement", to="persistence.artifact")),
            ],
            options={"db_table": "pl_requirement", "base_manager_name": "unscoped"},
        ),
        migrations.CreateModel(
            name="ArchitectureElement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("title", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True)),
                ("element_type", models.CharField(blank=True, max_length=64)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="architectureelement_set", to="persistence.tenant")),
                ("artifact", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="architecture_element", to="persistence.artifact")),
            ],
            options={"db_table": "pl_architecture_element", "base_manager_name": "unscoped"},
        ),
        migrations.CreateModel(
            name="TraceLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("link_type", models.CharField(max_length=64)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="tracelink_set", to="persistence.tenant")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_links", to="persistence.artifact")),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_links", to="persistence.artifact")),
            ],
            options={"db_table": "pl_tracelink", "base_manager_name": "unscoped"},
        ),
        migrations.AddIndex(
            model_name="tracelink",
            index=models.Index(fields=["source", "target"], name="idx_tracelink_graph"),
        ),
        migrations.CreateModel(
            name="TestCase",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("title", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True)),
                ("steps", models.JSONField(blank=True, default=list)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="testcase_set", to="persistence.tenant")),
                ("artifact", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="test_case", to="persistence.artifact")),
            ],
            options={"db_table": "pl_testcase", "base_manager_name": "unscoped"},
        ),
        migrations.CreateModel(
            name="Baseline",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("scope", models.CharField(max_length=64)),
                ("definition", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="baseline_set", to="persistence.tenant")),
                ("artifact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="baselines", to="persistence.artifact")),
            ],
            options={"db_table": "pl_baseline", "base_manager_name": "unscoped"},
        ),
        migrations.CreateModel(
            name="WorkflowDefinition",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("name", models.CharField(max_length=255)),
                ("workflow_json", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="workflowdefinition_set", to="persistence.tenant")),
                ("artifact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workflow_definitions", to="persistence.artifact")),
            ],
            options={"db_table": "pl_workflow_definition", "base_manager_name": "unscoped"},
        ),
        migrations.CreateModel(
            name="WorkflowState",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("current_state", models.CharField(max_length=128)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="workflowstate_set", to="persistence.tenant")),
                ("requirement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workflow_states", to="persistence.requirement")),
                ("definition", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="states", to="persistence.workflowdefinition")),
            ],
            options={"db_table": "pl_workflow_state", "base_manager_name": "unscoped"},
        ),
        migrations.CreateModel(
            name="AuditLogEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("action", models.CharField(max_length=64)),
                ("object_type", models.CharField(max_length=128)),
                ("object_id", models.UUIDField(blank=True, null=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="auditlogentry_set", to="persistence.tenant")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to="persistence.user")),
            ],
            options={"db_table": "pl_audit_log_entry", "base_manager_name": "unscoped"},
        ),
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(fields=["object_type", "object_id"], name="idx_audit_object"),
        ),
    ]
