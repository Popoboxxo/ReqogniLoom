"""
Initial migration for ARCH-L1-014 IcdManagement.

Creates:
  icd_icd      — Icd (logical ICD identity, mutable header)
  icd_version  — IcdVersion (immutable append-only version record)

DB-level immutability (mirroring ADR-L3-BL003-01 from baseline):
  BEFORE UPDATE / BEFORE DELETE triggers on icd_version raise PostgreSQL
  exceptions, preventing any modification outside the append-only INSERT path.

req_id:  REQ-L2-ICD-001 (CRUD + immutable versioning), REQ-L2-ICD-002 (DbC fields)
leaf_id: COMP-ICD-001
IF:      IF-L1-040 (PersistenceLayer)
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Initial IcdManagement migration."""

    initial = True

    dependencies = [
        # IcdVersion and Icd both inherit TenantScopedModel which needs pl_tenant + pl_user
        ("persistence", "0001_initial"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # Icd — logical identity header (without current_version FK first,
        # to avoid forward-reference to IcdVersion which doesn't exist yet)
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Icd",
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
                        related_name="icd_set",
                        to="persistence.tenant",
                    ),
                ),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("source_element_id", models.UUIDField(db_index=True)),
                ("target_element_id", models.UUIDField(db_index=True)),
                ("name", models.CharField(max_length=500)),
            ],
            options={
                "db_table": "icd_icd",
            },
        ),
        migrations.AddIndex(
            model_name="icd",
            index=models.Index(fields=["workspace_id"], name="idx_icd_workspace"),
        ),
        migrations.AddIndex(
            model_name="icd",
            index=models.Index(
                fields=["source_element_id", "target_element_id"],
                name="idx_icd_source_target",
            ),
        ),
        # ------------------------------------------------------------------
        # IcdVersion — immutable append-only version record
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="IcdVersion",
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
                        related_name="icdversion_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "icd",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="icd.icd",
                    ),
                ),
                ("version_number", models.PositiveIntegerField()),
                (
                    "direction",
                    models.CharField(
                        choices=[
                            ("unidirectional", "Unidirectional"),
                            ("bidirectional", "Bidirectional"),
                        ],
                        default="unidirectional",
                        max_length=32,
                    ),
                ),
                ("interface_type", models.CharField(blank=True, default="", max_length=128)),
                ("semantic_description", models.TextField(blank=True, default="")),
                ("preconditions", models.JSONField(blank=True, default=list)),
                ("postconditions", models.JSONField(blank=True, default=list)),
                ("invariants", models.JSONField(blank=True, default=list)),
            ],
            options={
                "db_table": "icd_version",
            },
        ),
        migrations.AddConstraint(
            model_name="icdversion",
            constraint=models.UniqueConstraint(
                fields=["icd", "version_number"],
                name="uq_icd_version_number",
            ),
        ),
        migrations.AddIndex(
            model_name="icdversion",
            index=models.Index(
                fields=["icd", "version_number"],
                name="idx_icd_version_icd_num",
            ),
        ),
        migrations.AddIndex(
            model_name="icdversion",
            index=models.Index(
                fields=["icd", "-created_at"],
                name="idx_icd_version_icd_cat",
            ),
        ),
        # ------------------------------------------------------------------
        # DB-level immutability trigger on icd_version (REQ-L2-ICD-001)
        # Mirrors baseline trigger pattern (ADR-L3-BL003-01).
        # ------------------------------------------------------------------
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION icd_raise_version_immutable()
            RETURNS TRIGGER AS $$
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    RAISE EXCEPTION 'IcdVersion records are immutable';
                ELSIF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'IcdVersion records are immutable';
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_icd_version_immutable
            BEFORE UPDATE OR DELETE ON icd_version
            FOR EACH ROW EXECUTE FUNCTION icd_raise_version_immutable();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_icd_version_immutable ON icd_version;
            DROP FUNCTION IF EXISTS icd_raise_version_immutable();
            """,
        ),
        # ------------------------------------------------------------------
        # Add current_version FK on Icd after IcdVersion table exists
        # (circular reference resolved by splitting CreateModel + AddField)
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="icd",
            name="current_version",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="current_for_icd",
                to="icd.icdversion",
            ),
        ),
    ]
