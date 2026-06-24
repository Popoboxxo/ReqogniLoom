"""
ARCH-L1-013 DiagramService — Initial schema migration.

leaf_id: COMP-DS-001 (DiagramManager)
req_id: REQ-L1-027, REQ-L2-DS-001 (IF-L1-035 PersistenceLayer)

Creates:
  diagram_diagram        — Diagram header entity (mutable)
  diagram_diagramversion — DiagramVersion entity (immutable, append-only)

Dependencies: persistence 0001_initial (provides Tenant, User tables
that TenantScopedModel / AuditableModel reference).
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("persistence", "0001_initial"),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # diagram_diagram — mutable header
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="Diagram",
            fields=[
                # AuditableModel fields
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                # TenantScopedModel FK
                ("tenant", models.ForeignKey(
                    db_index=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="diagram_set",
                    to="persistence.tenant",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="persistence.user",
                )),
                ("modified_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="persistence.user",
                )),
                # Diagram-specific fields
                ("name", models.CharField(max_length=500)),
                ("diagram_type", models.CharField(
                    choices=[("block", "Block Diagram"), ("flow", "Flow Diagram"), ("context", "Context Diagram")],
                    db_index=True,
                    max_length=32,
                )),
                ("description", models.TextField(blank=True, default="")),
                # current_version FK is added after DiagramVersion is created
            ],
            options={
                "db_table": "diagram_diagram",
                "base_manager_name": "unscoped",
            },
        ),
        # ------------------------------------------------------------------ #
        # diagram_diagramversion — immutable append-only snapshots
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="DiagramVersion",
            fields=[
                # AuditableModel fields
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                # TenantScopedModel FK
                ("tenant", models.ForeignKey(
                    db_index=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="diagramversion_set",
                    to="persistence.tenant",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="persistence.user",
                )),
                ("modified_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="persistence.user",
                )),
                # DiagramVersion-specific fields
                ("diagram", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="versions",
                    to="diagram.diagram",
                )),
                ("version_number", models.PositiveIntegerField()),
                ("payload_format", models.CharField(
                    choices=[("mermaid", "Mermaid"), ("plantuml", "PlantUML"), ("json", "Structured JSON")],
                    max_length=16,
                )),
                ("payload", models.TextField()),
            ],
            options={
                "db_table": "diagram_diagramversion",
                "base_manager_name": "unscoped",
            },
        ),
        # ------------------------------------------------------------------ #
        # Unique constraint on (diagram, version_number)
        # ------------------------------------------------------------------ #
        migrations.AddConstraint(
            model_name="diagramversion",
            constraint=models.UniqueConstraint(
                fields=["diagram", "version_number"],
                name="uq_diagram_version_number",
            ),
        ),
        # ------------------------------------------------------------------ #
        # Index on version history lookup
        # ------------------------------------------------------------------ #
        migrations.AddIndex(
            model_name="diagramversion",
            index=models.Index(
                fields=["diagram", "version_number"],
                name="idx_diagramversion_history",
            ),
        ),
        # ------------------------------------------------------------------ #
        # current_version FK on Diagram (after DiagramVersion exists)
        # ------------------------------------------------------------------ #
        migrations.AddField(
            model_name="diagram",
            name="current_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="diagram.diagramversion",
            ),
        ),
    ]
