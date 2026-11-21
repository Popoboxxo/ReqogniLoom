"""
admin_ops — async ZIP snapshot export metadata (R1/P5, D14b).

Adds one tenant-scoped table:

* ``admin_ops_export_snapshot_metadata`` — bookkeeping for a versioned
  artifact-transfer ZIP (status, file path, byte size, SHA-256, owning user,
  tenant and an ``expires_at`` TTL).

The table is closed with the same RLS shape as
``admin_ops/migrations/0007_rate_limit_override.py`` (ENABLE + FORCE, policy
keyed on ``app.current_tenant``) so one tenant can never poll or download
another tenant's snapshot. The background TTL cleanup uses the explicit
``unscoped`` manager to see all tenants (system maintenance, ADR-03).

Requirements:
- D14b — EXPORT_DIR + ExportSnapshotMetadata + TTL cleanup
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models

_TABLE = "admin_ops_export_snapshot_metadata"


def _enable_sql() -> str:
    policy = f"{_TABLE}_tenant_isolation"
    return (
        f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {policy} ON {_TABLE}\n"
        f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )


def _disable_sql() -> str:
    policy = f"{_TABLE}_tenant_isolation"
    return (
        f"DROP POLICY IF EXISTS {policy} ON {_TABLE};\n"
        f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("admin_ops", "0007_rate_limit_override"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExportSnapshotMetadata",
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
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                        ],
                        default="pending",
                        help_text="Lifecycle state. Only 'completed' rows are downloadable.",
                        max_length=16,
                    ),
                ),
                (
                    "source_workspace_id",
                    models.UUIDField(
                        help_text=(
                            "Workspace the snapshot was taken from "
                            "(scope of the export)."
                        ),
                    ),
                ),
                (
                    "file_path",
                    models.CharField(
                        blank=True,
                        help_text="Relative path under EXPORT_DIR to the generated ZIP.",
                        max_length=512,
                        null=True,
                    ),
                ),
                (
                    "size_bytes",
                    models.BigIntegerField(
                        blank=True,
                        help_text="Size of the stored ZIP in bytes; NULL until completed.",
                        null=True,
                    ),
                ),
                (
                    "checksum_sha256",
                    models.CharField(
                        blank=True,
                        help_text="SHA-256 hex digest of the final ZIP file.",
                        max_length=64,
                        null=True,
                    ),
                ),
                (
                    "content_checksum_sha256",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "SHA-256 of the canonical snapshot contents "
                            "(stored in the ZIP)."
                        ),
                        max_length=64,
                        null=True,
                    ),
                ),
                (
                    "format_version",
                    models.CharField(
                        default="artifact-transfer/v1",
                        help_text="Versioned snapshot contract the ZIP was written against.",
                        max_length=64,
                    ),
                ),
                (
                    "task_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Celery task id that produced this export.",
                        max_length=255,
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="TTL deadline; expired rows and their files are purged.",
                        null=True,
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Wall-clock time the ZIP finished writing.",
                        null=True,
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Populated when status='failed'.",
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Free-form provenance: 'source_tenant_id', "
                            "'target_workspace_id', 'target_tenant_id', "
                            "'entity_counts', 'format_version'."
                        ),
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        help_text=(
                            "User who started the export (independent of created_by)."
                        ),
                    ),
                ),
            ],
            options={
                "db_table": "admin_ops_export_snapshot_metadata",
                "indexes": [
                    models.Index(
                        fields=["status", "created_at"],
                        name="idx_export_status_created",
                    ),
                    models.Index(
                        fields=["expires_at"],
                        name="idx_export_expires_at",
                    ),
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
