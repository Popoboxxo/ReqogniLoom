"""
COMP-PL-006 RLSPolicyEnforcer — RLS policies for the AWMS run/snapshot tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind COMP-PL-002 TenantManager)

``AttributeMigrationRun`` / ``AttributeMigrationSnapshot`` (Attribut v3 WS7,
#940) are new ``TenantScopedModel``s. Every tenant-scoped table added after
``persistence/0003_rls_policies.py`` ships its own policy migration —
otherwise its isolation rests solely on the ORM-layer ``TenantManager`` filter,
and any query that bypasses the manager (raw SQL, ``unscoped`` without an
explicit ``tenant_id``) can read across tenants.
``persistence/tests/test_rls_coverage.py`` enforces this at model-add time.

Policy semantics are byte-identical to the other policy migrations (0003,
0086, 0089, ...): ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy
exposing only rows whose ``tenant_id`` equals the session variable
``app.current_tenant`` (armed by ``persistence.middleware.set_request_tenant``
per request, by the management command and by worker entry points). An
unset/empty setting matches no rows.

Access path: all run/snapshot reads and writes go through
``application.attribute_migration_service.AttributeMigrationService`` (or the
``attribute_migrate`` management command, which arms the same variable
explicitly) — both activate the tenant context via
``ServiceBase._set_tenant_context``/``set_request_tenant`` before any query, so
the standard policy is exactly what they expect.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "pl_attribute_migration_run",
    "pl_attribute_migration_snapshot",
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
        ("persistence", "0090_attributemigrationrun_attributemigrationsnapshot_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
