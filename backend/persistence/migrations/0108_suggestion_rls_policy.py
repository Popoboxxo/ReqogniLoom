"""
COMP-PL-006 RLSPolicyEnforcer — RLS policy for the generic proposal table.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind COMP-PL-002 TenantManager)
- ADR-019 (generic proposal lifecycle; ``Suggestion`` is a ``TenantScopedModel``)

``Suggestion`` (ADR-019, WP1) is a new ``TenantScopedModel``: the durable
receipt/inbox row over the four existing proposal mechanisms M1–M4. Every
tenant-scoped table added after ``persistence/0003_rls_policies.py`` ships its
own policy migration — otherwise its isolation rests solely on the ORM-layer
``TenantManager`` filter, and any query that bypasses the manager (raw SQL,
``unscoped`` without an explicit ``tenant_id``) can read across tenants.
``persistence/tests/test_rls_coverage.py`` enforces this at model-add time.

Policy semantics are byte-identical to the other policy migrations (0003, 0086,
0089, 0091, 0097, ...): ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL``
policy exposing only rows whose ``tenant_id`` equals the session variable
``app.current_tenant``. An unset/empty setting matches no rows, so a query
without an armed tenant context is fail-closed.

Access path: both the produce path (``SuggestionService.propose``/``create``)
and the inbox/accept/reject path (``SuggestionService.list_open``/``accept``/
``reject``) arm the tenant via ``ServiceBase._set_tenant_context`` before any
query, so the standard policy is exactly what they expect.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "pl_suggestion"


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
        ("persistence", "0107_suggestion"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
