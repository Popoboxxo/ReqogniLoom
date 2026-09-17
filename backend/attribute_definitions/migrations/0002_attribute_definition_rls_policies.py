"""COMP-PL-006 RLSPolicyEnforcer — RLS for the ``ad_*`` AttributeDefinition tables.

Both tables are ``TenantScopedModel`` subclasses and must not ship without a
policy (Systemaudit 2026-08-27, P0 finding #2). Policy semantics are
byte-identical to ``persistence/0003_rls_policies.py`` and
``workflow/0015_workflow_rls_policies.py``: ENABLE + FORCE ROW LEVEL SECURITY
plus one ``ALL`` policy keyed on the session variable ``app.current_tenant``.
An unset/empty setting matches no rows.

``GlobalAttributeDefinition`` is "global" only in the sense of
tenant-wide-per-(item_type, preset); it still carries a per-tenant
``tenant_id``, so the standard policy applies unchanged.
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "ad_global_definition",
    "ad_workspace_definition",
]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0001_initial"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
