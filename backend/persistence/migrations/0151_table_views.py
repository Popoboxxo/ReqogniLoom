"""Saved table views and per-user table state (Tabellenansicht slice 3, Task 3.1).

Two plain tenant-scoped tables, no ``Artifact`` behind either of them:

* ``pl_user_table_view_state`` — one row per ``(user, workspace, item_type)``,
  "where I was last" (overwritten in place).
* ``pl_saved_view`` — a named view, private or workspace-wide, unique per
  ``(workspace, item_type, owner, name)``.

Both carry the standard tenant column and get their RLS policy in the
following migration (``0152_table_views_rls_policy``), per the house pattern
(``0147``/``0148`` and ``persistence/tests/test_rls_coverage.py``).
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0150_workspace_ai_language"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserTableViewState",
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
                    "item_type",
                    models.CharField(
                        help_text="Artifact type the table shows, e.g. 'Requirement'.",
                        max_length=128,
                    ),
                ),
                (
                    "columns",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text=(
                            "Ordered column descriptors "
                            "[{'field': ..., 'order': ...}]."
                        ),
                    ),
                ),
                (
                    "filters",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Filter DSL document: {'<field>': <constraint> | "
                            "[<constraint>]}."
                        ),
                    ),
                ),
                (
                    "sort",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text=(
                            "Sort document: "
                            "[{'field': ..., 'dir': 'asc' | 'desc'}]."
                        ),
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
                        help_text="Owner of this layout state; deletes with the user.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="table_view_states",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        help_text=(
                            "Tenant anchor for the state; deletes with the workspace."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="table_view_states",
                        to="persistence.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "pl_user_table_view_state",
                "indexes": [
                    models.Index(
                        fields=["workspace", "item_type"], name="idx_utvs_ws_type"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "workspace", "item_type"),
                        name="uq_utvs_user_ws_type",
                    )
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="SavedView",
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
                    "item_type",
                    models.CharField(
                        help_text="Artifact type the view shows, e.g. 'Requirement'.",
                        max_length=128,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text=(
                            "Display name, unique per owner and item type in a "
                            "workspace."
                        ),
                        max_length=255,
                    ),
                ),
                (
                    "columns",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text=(
                            "Ordered column descriptors "
                            "[{'field': ..., 'order': ...}]."
                        ),
                    ),
                ),
                (
                    "filters",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Filter DSL document: {'<field>': <constraint> | "
                            "[<constraint>]}."
                        ),
                    ),
                ),
                (
                    "sort",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text=(
                            "Sort document: "
                            "[{'field': ..., 'dir': 'asc' | 'desc'}]."
                        ),
                    ),
                ),
                (
                    "visibility",
                    models.CharField(
                        choices=[
                            ("private", "Private"),
                            ("workspace", "Workspace"),
                        ],
                        default="private",
                        help_text=(
                            "'private' (owner only) or 'workspace' (every member "
                            "reads)."
                        ),
                        max_length=16,
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
                    "owner",
                    models.ForeignKey(
                        help_text=(
                            "Creator of the view; only they (or an admin) may "
                            "change it."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_views",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        help_text="Tenant anchor for the view; deletes with the workspace.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_views",
                        to="persistence.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "pl_saved_view",
                "indexes": [
                    models.Index(
                        fields=["workspace", "item_type"], name="idx_sview_ws_type"
                    ),
                    models.Index(
                        fields=["workspace", "visibility"],
                        name="idx_sview_ws_visibility",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("workspace", "item_type", "owner", "name"),
                        name="uq_saved_view_ws_type_owner_name",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(visibility__in=["private", "workspace"]),
                        name="ck_saved_view_visibility",
                    ),
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
    ]
