"""
Migration 0009: PostgreSQL Row-Level Security for as_risk and as_issue.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

Background:
    Risk and Issue live in the ``application`` app and were NOT covered by the
    original RLS migration (persistence/0003_rls_policies.py), which only enabled
    RLS on the eleven ``pl_*`` tables. Multi-tenant isolation for Risk/Issue
    therefore relied solely on the service-layer tenant filter — a defense-in-depth
    gap: a query bypassing the service layer could read across tenants.

    This migration closes that gap by enabling the same RLS policy pattern on
    ``as_risk`` and ``as_issue``. Both tables already carry a ``tenant_id`` column,
    which is all the policy needs; no schema change to the tables is required.

Policy semantics (identical to persistence/0003):
    Each table gets RLS enabled + FORCE (so the application DB role, typically the
    table owner, is also constrained) plus a policy exposing only rows whose
    ``tenant_id`` equals the session variable ``app.current_tenant`` (set per
    request via ``SET app.current_tenant`` — see persistence/middleware.py). An
    unset/empty setting matches no rows (empty result), satisfying REQ-L2-PL-010's
    "direct DB access without the setting → empty result" criterion.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

# Tenant-scoped tables owned by the application app that carry a tenant_id
# column. Adr (as_adr) is intentionally left for a separate change to keep this
# migration focused on the Risk/Issue isolation gap.
_TENANT_TABLES = [
    "as_risk",
    "as_issue",
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
        ("application", "0008_risk_issue_artifact_backing"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
