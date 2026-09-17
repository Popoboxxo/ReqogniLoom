"""
COMP-PL-006 RLSPolicyEnforcer — RLS for the ``icd_*`` tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    ``Icd``, ``IcdVersion`` and ``IcdParameter`` are ``TenantScopedModel``
    subclasses whose tables shipped without an RLS policy — tenant isolation
    relied solely on the ORM-layer filter. All three already carry a
    ``tenant_id`` UUID column, so no schema change is required; this migration
    is purely additive DDL.

Policy semantics (byte-identical to persistence/0003):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows, satisfying REQ-L2-PL-010.

Access-path review:
    ``icd.icd_manager`` and ``icd.icd_parameter_service`` query via ``unscoped``
    with an explicit ``tenant_id=`` from request-scoped services, where
    ``TenantContextService.activate`` has armed both isolation layers.
    ``baseline.state_capture`` reads ``IcdVersion.unscoped`` alongside the
    already-RLS-protected ``pl_artifact`` / ``pl_requirement`` reads in the same
    function — proof that the session variable is armed on that path too.
    ``icd/admin.py`` uses ``unscoped`` for cross-tenant Django-admin listings,
    which is already the situation for every table covered by
    ``persistence/0003``.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "icd_icd",
    "icd_version",
    "icd_parameter",
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
        ("icd", "0006_icd_version_delete_guard"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
