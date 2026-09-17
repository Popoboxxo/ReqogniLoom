"""
admin_ops — PostgreSQL Row-Level Security for the Theme Presets tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

Background:
    ``ThemePalette`` (0004), ``UserThemePreference`` and
    ``TenantThemeDefault`` (0005) are ``TenantScopedModel`` tables. This
    migration closes them with the identical policy shape used by
    ``admin_ops/migrations/0003_banner_rls.py`` (which itself mirrors
    ``persistence/0003_rls_policies.py``): ENABLE + FORCE RLS, policy keyed
    on ``app.current_tenant``.

Policy semantics:
    An unset/empty ``app.current_tenant`` matches no rows — direct DB access
    without tenant context yields an empty result, satisfying REQ-L2-PL-010.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLES = (
    "admin_ops_theme_palette",
    "admin_ops_user_theme_preference",
    "admin_ops_tenant_theme_default",
)


def _enable_sql() -> str:
    statements = []
    for table in _TABLES:
        policy = f"{table}_tenant_isolation"
        statements.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(statements)


def _disable_sql() -> str:
    statements = []
    for table in _TABLES:
        policy = f"{table}_tenant_isolation"
        statements.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(statements)


class Migration(migrations.Migration):

    dependencies = [
        ("admin_ops", "0005_theme_preference_and_default"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
