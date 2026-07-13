"""
admin_ops — initial schema for the Disaster Recovery foundation (REQ-L1-046).

Adds the ``admin_ops_backup_metadata`` table. The table is
**instance-level** (no ``tenant_id`` FK, no TenantScopedModel
inheritance) — a backup is a system artefact, not a tenant record, and
it must be queryable across tenants.

Depends on the latest persistence migration that ships to production
(``0009_workspace_lifecycle_fields``) and the latest auth_tenancy
migration (``0003_item_permission``) so the user/tenant tables the
``created_by`` / ``modified_by`` FKs point at already exist.

Hand-authored to match ``admin_ops/models.py``. ``makemigrations
--check`` must report no further changes against this migration.
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("persistence", "0009_workspace_lifecycle_fields"),
        ("auth_tenancy", "0003_item_permission"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackupMetadata",
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
                # Inherited from AuditableModel
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
                # BackupMetadata-specific fields
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        help_text=(
                            "Lifecycle state. Only 'completed' rows are "
                            "restorable."
                        ),
                        max_length=16,
                    ),
                ),
                (
                    "backup_type",
                    models.CharField(
                        choices=[("full", "Full"), ("partial", "Partial")],
                        default="full",
                        help_text="Scope of the backup ('full' or 'partial').",
                        max_length=16,
                    ),
                ),
                (
                    "file_path",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Relative path under MEDIA_ROOT to the "
                            "dumpdata JSON file."
                        ),
                        max_length=512,
                        null=True,
                    ),
                ),
                (
                    "file_size_bytes",
                    models.BigIntegerField(
                        blank=True,
                        help_text=(
                            "Size of the backup file in bytes; NULL for "
                            "pending/failed rows."
                        ),
                        null=True,
                    ),
                ),
                (
                    "checksum_sha256",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "SHA-256 hex digest of the backup file "
                            "(64 chars)."
                        ),
                        max_length=64,
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
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text=(
                            "Wall-clock time the backup finished writing. "
                            "NULL until status is 'completed' or 'failed'."
                        ),
                        null=True,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Free-form summary payload — keys used by the "
                            "foundation: 'tenant_count', 'artifact_count', "
                            "'app_counts', 'last_restore_status', "
                            "'last_restore_error'."
                        ),
                    ),
                ),
            ],
            options={
                "db_table": "admin_ops_backup_metadata",
                "indexes": [
                    models.Index(
                        fields=["status", "created_at"],
                        name="idx_backup_status_created",
                    ),
                ],
            },
        ),
    ]
