"""COMP-PL-006 RLSPolicyEnforcer — RLS for both table-view tables (slice 3).

``UserTableViewState`` and ``SavedView`` are ``TenantScopedModel`` subclasses;
``persistence/tests/test_rls_coverage.py`` fails the build for any such table
without a policy migration. The SQL is byte-identical to the house pattern
(``0148_artifact_summary_rls_policy``, ``0136``/``0140``): ENABLE + FORCE ROW
LEVEL SECURITY plus one ``ALL`` policy per table exposing only rows whose
``tenant_id`` equals ``app.current_tenant``.

Both tables are read and written only inside an armed tenant context
(``SavedViewService``/``TableViewStateService`` call
``ServiceBase._set_tenant_context`` before their first query), so no exemption
and no staged GUC is needed.
"""
from __future__ import annotations

from django.db import migrations

_TABLES = ("pl_user_table_view_state", "pl_saved_view")


def _policy(table: str) -> str:
    return f"{table}_tenant_isolation"


def _enable_sql() -> str:
    statements = []
    for table in _TABLES:
        policy = _policy(table)
        statements.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            "    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            "    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(statements)


def _disable_sql() -> str:
    statements = []
    for table in _TABLES:
        policy = _policy(table)
        statements.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(statements)


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0151_table_views"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
