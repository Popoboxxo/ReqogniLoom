"""
Initial migration for ARCH-L1-006 BaselineService.

Creates:
  bl_baseline_snapshot  — BaselineSnapshot (immutable Baseline header)
  bl_delta_index_entry  — BaselineDeltaIndexEntry (item_id/version tuples)

DB-level immutability (ADR-L3-BL003-01):
  BEFORE UPDATE / BEFORE DELETE triggers on both tables raise PostgreSQL
  exceptions, preventing any modification outside of the application's
  atomic INSERT path.

req_id: REQ-L2-BL-002 (Immutability), REQ-L2-BL-005 (Unique name per workspace)
leaf_id: COMP-BL-003
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Initial migration for baseline app."""

    initial = True

    dependencies = [
        # BaselineSnapshot inherits TenantScopedModel which needs pl_tenant + pl_user
        ("persistence", "0001_initial"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # BaselineSnapshot
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="BaselineSnapshot",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
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
                ("modified_at", models.DateTimeField(auto_now=True)),
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
                ("version", models.IntegerField(default=1)),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="baselinesnapshot_set",
                        to="persistence.tenant",
                    ),
                ),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("scope", models.CharField(max_length=32)),
                ("name", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True, default="")),
                ("created_by_ref", models.CharField(blank=True, default="", max_length=255)),
            ],
            options={
                "db_table": "bl_baseline_snapshot",
            },
        ),
        migrations.AddConstraint(
            model_name="baselinesnapshot",
            constraint=models.UniqueConstraint(
                fields=["workspace_id", "name"],
                name="uq_baseline_snapshot_workspace_name",
            ),
        ),
        migrations.AddIndex(
            model_name="baselinesnapshot",
            index=models.Index(
                fields=["workspace_id", "-created_at"],
                name="idx_baseline_snapshot_ws_cat",
            ),
        ),
        migrations.AddIndex(
            model_name="baselinesnapshot",
            index=models.Index(
                fields=["workspace_id", "scope"],
                name="idx_baseline_snapshot_ws_scope",
            ),
        ),
        # ------------------------------------------------------------------
        # BaselineDeltaIndexEntry
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="BaselineDeltaIndexEntry",
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
                (
                    "baseline",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delta_entries",
                        to="baseline.baselinesnapshot",
                    ),
                ),
                ("item_id", models.CharField(db_index=True, max_length=64)),
                ("version", models.IntegerField()),
                ("entity_type", models.CharField(default="item", max_length=32)),
            ],
            options={
                "db_table": "bl_delta_index_entry",
            },
        ),
        migrations.AddConstraint(
            model_name="baselinedeltaindexentry",
            constraint=models.UniqueConstraint(
                fields=["baseline", "item_id"],
                name="uq_delta_entry_baseline_item",
            ),
        ),
        migrations.AddIndex(
            model_name="baselinedeltaindexentry",
            index=models.Index(
                fields=["baseline", "item_id"],
                name="idx_delta_entry_baseline_item",
            ),
        ),
        # ------------------------------------------------------------------
        # DB-level immutability triggers (ADR-L3-BL003-01, REQ-L2-BL-002)
        # These triggers prevent UPDATE/DELETE on both tables at the DB level.
        # ------------------------------------------------------------------
        migrations.RunSQL(
            sql="""
            -- Function shared by both immutability triggers
            CREATE OR REPLACE FUNCTION bl_raise_immutable()
            RETURNS TRIGGER AS $$
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    RAISE EXCEPTION 'Baselines are immutable';
                ELSIF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Baselines are immutable';
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;

            -- Trigger on BaselineSnapshot
            CREATE TRIGGER trg_baseline_snapshot_immutable
            BEFORE UPDATE OR DELETE ON bl_baseline_snapshot
            FOR EACH ROW EXECUTE FUNCTION bl_raise_immutable();

            -- Trigger on BaselineDeltaIndexEntry
            CREATE TRIGGER trg_delta_entry_immutable
            BEFORE UPDATE OR DELETE ON bl_delta_index_entry
            FOR EACH ROW EXECUTE FUNCTION bl_raise_immutable();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_baseline_snapshot_immutable ON bl_baseline_snapshot;
            DROP TRIGGER IF EXISTS trg_delta_entry_immutable ON bl_delta_index_entry;
            DROP FUNCTION IF EXISTS bl_raise_immutable();
            """,
        ),
    ]
