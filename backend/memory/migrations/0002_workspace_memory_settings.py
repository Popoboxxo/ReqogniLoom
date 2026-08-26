# AI Long-Term Memory — WorkspaceMemorySettings (Spec 2026-08-24, Task 11).
#
# A third, independent tenant-scoped table: the per-workspace enable/disable
# toggle for the memory feature. This is a NEW migration, not an append to
# 0001_initial.py — 0001 has already been applied and is in active use by
# Tasks 3/5/6/7/9/10 (WorkspaceMemory/UserTenantMemory), so amending it would
# desync the applied migration from the real DB schema (Global Constraint).
#
# Operation order mirrors 0001_initial.py / context_graph/migrations/0001_initial.py:
#   1. CreateModel + its OneToOne unique constraint (implicit via OneToOneField).
#   2. Enable + FORCE RLS on the new table in the SAME migration (Global
#      Constraints: "New tenant-scoped tables require RLS in the same
#      migration that creates them").
#
# FORCE (not just ENABLE) matters here for the same reason as 0001: DDL runs
# under the DB-owner role, which bypasses a plain ENABLE-only policy: without
# FORCE, RLS would silently not apply to any connection using the owner role.
import uuid

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


_WORKSPACE_MEMORY_SETTINGS_TABLE = "mem_workspace_memory_settings"


def _rls_sql(table: str) -> tuple[str, str]:
    policy = f"{table}_tenant_isolation"
    enable_sql = (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {policy} ON {table}\n"
        f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )
    disable_sql = (
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    )
    return enable_sql, disable_sql


_WORKSPACE_MEMORY_SETTINGS_ENABLE_SQL, _WORKSPACE_MEMORY_SETTINGS_DISABLE_SQL = _rls_sql(
    _WORKSPACE_MEMORY_SETTINGS_TABLE
)


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0001_initial"),
        ("persistence", "0066_interview_multi_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceMemorySettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("enabled", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
                ("workspace", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="persistence.workspace")),
            ],
            options={"db_table": "mem_workspace_memory_settings"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.RunSQL(
            sql=_WORKSPACE_MEMORY_SETTINGS_ENABLE_SQL,
            reverse_sql=_WORKSPACE_MEMORY_SETTINGS_DISABLE_SQL,
        ),
    ]
