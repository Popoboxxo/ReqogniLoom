"""auth_tenancy — global / workspace tree-display configuration (Issue #1257).

Creates ``at_tree_display_config``: the two administrative levels of the
navigation tree's field configuration, with precedence ``user > workspace >
global`` (the personal level lives on
``at_user_display_preference.tree_display_fields``, migration 0024).

* ``scope="global"`` — exactly one row per tenant (unique constraint).
* ``scope="workspace"`` — exactly one row per (tenant, workspace).

``fields_json`` is a JSON map ``{item_type: [{"key": …, "width": …}, …]}``. A
missing row means "inherit", never "empty", so readers must not create one.

The table is a ``TenantScopedModel`` and is therefore closed by the RLS policy
in ``0025_treedisplayconfig_rls`` (REQ-L2-PL-010).

Authored manually for human review (mirrors ``0019_userdisplaypreference``); no
``makemigrations``/``migrate`` run.
"""

import uuid

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0024_userdisplaypreference_tree_display_fields"),
        ("persistence", "0114_alter_suggestion_kind"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TreeDisplayConfig",
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
                    "scope",
                    models.CharField(
                        max_length=16,
                        choices=[
                            ("global", "Global"),
                            ("workspace", "Workspace"),
                        ],
                    ),
                ),
                ("fields_json", models.JSONField(blank=True, default=dict)),
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
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tree_display_config",
                        to="persistence.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "at_tree_display_config",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant",),
                        condition=models.Q(("scope", "global")),
                        name="uq_tree_display_config_global",
                    ),
                    models.UniqueConstraint(
                        fields=("tenant", "workspace"),
                        condition=models.Q(("scope", "workspace")),
                        name="uq_tree_display_config_workspace",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(("scope", "global"), ("workspace__isnull", True))
                            | models.Q(
                                ("scope", "workspace"), ("workspace__isnull", False)
                            )
                        ),
                        name="ck_tree_display_config_workspace_matches_scope",
                    ),
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
    ]
