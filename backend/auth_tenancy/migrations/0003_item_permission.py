"""
ARCH-L1-011 AuthAndTenancy — ItemPermission table (COMP-AT-005, REQ-L1-039).

Adds the ``at_item_permission`` table for item-level RBAC rules (defense-in-
depth over the coarse role matrix in COMP-AT-002). The table is tenant-
scoped and carries a workspace FK plus an optional artifact FK (NULL =
workspace-wide default rule for the user).

Hand-authored to match ``auth_tenancy/models.py`` and to keep the filename
deterministic (``0003_item_permission.py``). ``makemigrations --check`` must
report no further changes against this migration.

Depends on the latest persistence migration (Welle A baseline,
``0009_workspace_lifecycle_fields``) and the latest auth_tenancy migration.
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("persistence", "0009_workspace_lifecycle_fields"),
        ("auth_tenancy", "0002_alter_apikey_managers_alter_userrole_managers"),
    ]

    operations = [
        migrations.CreateModel(
            name="ItemPermission",
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
                    "permission_level",
                    models.CharField(
                        choices=[
                            ("read", "Read"),
                            ("write", "Write"),
                            ("none", "None (explicit deny)"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "artifact",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="item_permissions",
                        to="persistence.artifact",
                    ),
                ),
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
                    "granted_by",
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
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="item_permissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="item_permissions",
                        to="persistence.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "at_item_permission",
                "indexes": [
                    models.Index(
                        fields=["user", "workspace"],
                        name="idx_itempermission_user_ws",
                    ),
                    models.Index(
                        fields=["workspace", "artifact"],
                        name="idx_itempermission_ws_artifact",
                    ),
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name="itempermission",
            constraint=models.UniqueConstraint(
                fields=("tenant", "user", "workspace", "artifact"),
                name="uq_itempermission_user_ws_artifact",
            ),
        ),
    ]
