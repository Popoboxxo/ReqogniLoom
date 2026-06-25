"""
ARCH-L1-012 AuditLog — Initial schema for audit_entry table.

COMP-AL-001 (AuditLogWriter): append-only AuditEntry entity.
COMP-AL-002 (AuditLogQuery): indexes for query performance.

Requirements:
- REQ-L2-AL-001 (all write operation fields: actor, op, entity_type, entity_id, ...)
- REQ-L2-AL-002 (MCP fields: source, client_name, api_key_hash)
- REQ-L2-AL-006 (tenant_id FK from TenantScopedModel)
- REQ-L2-AL-007 (indexes: entity_id, tenant+timestamp, actor+op)
- REQ-L2-AL-008 (timestamp as partition key — NOTE: PostgreSQL RANGE partitioning
  requires DDL outside Django migration; this migration creates the base table.
  Production partitioning setup via database DBA / separate DDL script.)
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEntry",
            fields=[
                # TenantScopedModel base fields
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                # Tenant FK (REQ-L2-AL-006)
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="auditentry_set",
                        to="persistence.tenant",
                    ),
                ),
                # Audit fields (REQ-L2-AL-001)
                ("actor", models.CharField(max_length=255)),
                (
                    "actor_type",
                    models.CharField(
                        choices=[("user", "User"), ("agent", "Agent")],
                        max_length=16,
                    ),
                ),
                (
                    "op",
                    models.CharField(
                        choices=[
                            ("create", "Create"),
                            ("update", "Update"),
                            ("delete", "Delete"),
                            ("transition", "Transition"),
                        ],
                        max_length=32,
                    ),
                ),
                ("entity_type", models.CharField(max_length=128)),
                ("entity_id", models.UUIDField()),
                ("entity_version", models.IntegerField(blank=True, null=True)),
                ("change_reason", models.TextField(blank=True, null=True)),
                # Partition key (REQ-L2-AL-008)
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                # MCP enrichment (REQ-L2-AL-002)
                (
                    "source",
                    models.CharField(
                        choices=[("rest", "REST"), ("mcp", "MCP")],
                        default="rest",
                        max_length=8,
                    ),
                ),
                ("client_name", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "api_key_hash",
                    models.CharField(
                        blank=True,
                        help_text="SHA-256 hash with 'sha256:' prefix. Never raw key.",
                        max_length=71,
                        null=True,
                    ),
                ),
                # FKs for created_by / modified_by (AuditableModel base)
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
                "db_table": "audit_entry",
                "base_manager_name": "unscoped",
            },
        ),
        # REQ-L2-AL-007: Indexes for query performance
        migrations.AddIndex(
            model_name="AuditEntry",
            index=models.Index(
                fields=["entity_id"],
                name="idx_auditentry_entity_id",
            ),
        ),
        migrations.AddIndex(
            model_name="AuditEntry",
            index=models.Index(
                fields=["tenant", "timestamp"],
                name="idx_audit_tenant_ts",
            ),
        ),
        migrations.AddIndex(
            model_name="AuditEntry",
            index=models.Index(
                fields=["actor", "op"],
                name="idx_auditentry_actor_op",
            ),
        ),
    ]
