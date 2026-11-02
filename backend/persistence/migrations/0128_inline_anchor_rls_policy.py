"""
COMP-PL-006 RLSPolicyEnforcer — RLS policy for the inline-anchor table.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind COMP-PL-002 TenantManager)
- Plan F F3-T7 / KA-F-13 (the policy ships with the table, never as a follow-up PR)

``InlineAnchor`` (Plan F F3-T7, #1374) is a ``TenantScopedModel``: the text
anchor register that keeps an inline reference token's "Fundort" next to the
TraceLink it implies. ``persistence/tests/test_rls_coverage.py`` fails the build
for any ``TenantScopedModel`` whose table has no policy migration, so both
halves live in the same release.

Policy semantics are byte-identical to the other policy migrations (0003, 0086,
0089, 0091, 0097, 0108, 0122, 0124, 0126): ENABLE + FORCE ROW LEVEL SECURITY
plus one ``ALL`` policy exposing only rows whose ``tenant_id`` equals the
session variable ``app.current_tenant``. An unset/empty setting matches no
rows, so a query without an armed tenant context is fail-closed.

Access path: every read and write goes through ``InlineAnchor.objects``
(TenantManager) or the service layer, both of which arm the tenant before
querying. The workspace/Artifact/TraceLink CASCADE deletes run through Django's
non-tenant ``_base_manager``, which stays inside the same tenant.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "pl_inline_anchor"


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
        ("persistence", "0127_inline_anchor"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
