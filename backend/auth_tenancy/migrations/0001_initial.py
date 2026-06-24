"""
ARCH-L1-011 AuthAndTenancy — initial schema (ApiKey, UserRole).

Requirements:
- REQ-L3-AT001-002 / REQ-L3-AT001-003 (hashed API-key storage + lifecycle)
- REQ-L3-AT002-002 / REQ-L3-AT002-003 (role assignment, suspension, audit)
- REQ-L2-AT-006 (workspace-scoped role CRUD)

Hand-authored to match auth_tenancy/models.py. ``makemigrations --check`` must
report no changes against this migration. Depends on the PersistenceLayer initial
migration (User, Tenant, Workspace).
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
        migrations.CreateModel(
            name="ApiKey",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("name", models.CharField(max_length=255)),
                ("key_hash", models.CharField(db_index=True, max_length=80, unique=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user"),
                ),
                (
                    "modified_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user"),
                ),
                (
                    "tenant",
                    models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_keys", to="persistence.user"),
                ),
            ],
            options={"db_table": "at_api_key"},
        ),
        migrations.CreateModel(
            name="UserRole",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("admin", "Admin"),
                            ("editor", "Editor"),
                            ("viewer", "Viewer"),
                            ("approver", "Approver"),
                        ],
                        max_length=32,
                    ),
                ),
                ("suspended_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assigned_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user"),
                ),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user"),
                ),
                (
                    "modified_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="persistence.user"),
                ),
                (
                    "tenant",
                    models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_assignments", to="persistence.user"),
                ),
                (
                    "workspace",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_assignments", to="persistence.workspace"),
                ),
            ],
            options={"db_table": "at_user_role"},
        ),
        migrations.AddIndex(
            model_name="apikey",
            index=models.Index(fields=["user", "revoked_at"], name="idx_apikey_user_active"),
        ),
        migrations.AddIndex(
            model_name="userrole",
            index=models.Index(fields=["user", "workspace"], name="idx_userrole_user_ws"),
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(
                fields=["workspace", "user", "role"],
                name="uq_userrole_workspace_user_role",
            ),
        ),
    ]
