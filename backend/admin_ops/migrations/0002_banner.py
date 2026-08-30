"""
admin_ops — adds the ``admin_ops_banner`` table (System & Workspace Banners).

Depends on the latest ``persistence`` migration that ships to production
(``0065_alter_interviewsession_status``, for the ``Workspace``/``Tenant``/
``User`` FK targets) and this app's own initial migration.

Hand-authored to match ``admin_ops/models.py``. ``makemigrations --check``
must report no further changes against this migration.
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
        ("admin_ops", "0001_initial"),
        ("persistence", "0065_alter_interviewsession_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="Banner",
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
                    "scope",
                    models.CharField(
                        choices=[("global", "Global"), ("workspace", "Workspace")],
                        max_length=16,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="banner",
                        to="persistence.workspace",
                    ),
                ),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("neutral", "Neutral"),
                            ("info", "Info"),
                            ("warning", "Warning"),
                            ("critical", "Critical"),
                        ],
                        default="neutral",
                        max_length=16,
                    ),
                ),
                (
                    "message",
                    models.TextField(blank=True, default="", help_text="Markdown source."),
                ),
                ("enabled", models.BooleanField(default=False)),
                (
                    "dismissible",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Whether end users may close the banner (until next "
                            "login). A real, independently-editable field — "
                            "never hardcoded by level."
                        ),
                    ),
                ),
                (
                    "show_on_login_page",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Ignored unless scope == 'global' — the login page "
                            "has no workspace context."
                        ),
                    ),
                ),
            ],
            options={
                "db_table": "admin_ops_banner",
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name="banner",
            constraint=models.UniqueConstraint(
                condition=models.Q(scope="global"),
                fields=("tenant",),
                name="uq_banner_one_global_per_tenant",
            ),
        ),
        migrations.AddConstraint(
            model_name="banner",
            constraint=models.UniqueConstraint(
                condition=models.Q(scope="workspace"),
                fields=("workspace",),
                name="uq_banner_one_per_workspace",
            ),
        ),
        migrations.AddConstraint(
            model_name="banner",
            # ``condition=`` (not ``check=``): renamed in Django 5.1, the old
            # spelling warns under 5.2 and is removed in 6.0. Behaviour-neutral
            # for this historical migration — since 5.1 both kwargs populate the
            # same ``condition`` attribute and deconstruct identically, so the
            # recorded state and the generated CHECK SQL are unchanged.
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("scope", "global"), ("workspace__isnull", True))
                    | models.Q(("scope", "workspace"), ("workspace__isnull", False))
                ),
                name="ck_banner_workspace_matches_scope",
            ),
        ),
    ]
