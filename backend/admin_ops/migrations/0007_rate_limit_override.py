"""
admin_ops — runtime-configurable rate limits (GitHub #944).

Adds two tables:

* ``admin_ops_system_rate_limit_override`` — the deployment-wide default
  (singleton, JSON scope -> rate map). Not tenant-scoped: it is the one
  override the pre-authentication MCP transport can honour.
* ``admin_ops_rate_limit_override`` — the per-tenant override, one row per
  ``(tenant, scope)``.

The tenant-scoped table is closed with the same RLS policy shape as
``admin_ops/migrations/0006_theme_tables_rls.py`` (ENABLE + FORCE, policy
keyed on ``app.current_tenant``) so a tenant's limits never leak into
another tenant's resolution path.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models

_TABLE = "admin_ops_rate_limit_override"


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
        ("admin_ops", "0006_theme_tables_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemRateLimitOverride",
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
                    "scopes",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Throttle scope -> DRF rate string, e.g. "
                            "{'user': '600/min'}. An empty string disables that "
                            "scope deployment-wide."
                        ),
                    ),
                ),
            ],
            options={
                "db_table": "admin_ops_system_rate_limit_override",
            },
        ),
        migrations.CreateModel(
            name="RateLimitOverride",
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
                        help_text="Throttle scope name, e.g. 'user', 'mcp_key'.",
                        max_length=32,
                    ),
                ),
                (
                    "rate",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "DRF rate string ('600/min'). Empty = unlimited for "
                            "this tenant. Absent row = fall through to the global "
                            "override / settings."
                        ),
                        max_length=32,
                    ),
                ),
            ],
            options={
                "db_table": "admin_ops_rate_limit_override",
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name="ratelimitoverride",
            constraint=models.UniqueConstraint(
                fields=("tenant", "scope"),
                name="uq_rate_limit_override_tenant_scope",
            ),
        ),
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
