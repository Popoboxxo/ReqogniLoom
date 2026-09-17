"""COMP-PL-006 RLSPolicyEnforcer — RLS for the ``lt_*`` LinkTypeCatalog tables.

Both LinkTypeCatalog models are ``TenantScopedModel`` subclasses carrying a
``tenant_id`` UUID column, so this migration is purely additive DDL. Policy
semantics are byte-identical to ``persistence/0003`` and ``workflow/0015``:
ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
session variable ``app.current_tenant``. An unset/empty setting matches no
rows (REQ-L2-PL-010).

Access-path review: every read of these tables goes through
``link_types.catalog.resolve_catalog``, which is only ever called from
request-scoped services where ``TenantContextService.activate`` has already
armed both isolation layers, and from the seed/backfill migration, which runs
under the migration role and arms the tenant explicitly per tenant row.
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = ["lt_global_definition", "lt_workspace_definition"]


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
        ("link_types", "0001_initial"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
