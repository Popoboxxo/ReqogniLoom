"""
Migration 0013: PostgreSQL Row-Level Security for the remaining ``as_*`` tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

Background:
    ``application/0009_risk_issue_rls_policies.py`` closed the RLS gap for
    ``as_risk`` and ``as_issue`` but explicitly deferred ``as_adr`` to a
    separate change. ``as_change_request`` (migration 0011) and ``as_goal`` /
    ``as_main_goal`` (migration 0012) were added afterwards and never joined
    the policy set either.

    Tenant isolation for these four tables therefore relies solely on the
    service-layer tenant filter. That filter is correct today — every read path
    scopes by ``tenant_id`` — so this is a defense-in-depth gap rather than an
    active vulnerability: a query bypassing the service layer (raw SQL, a future
    ORM call that forgets the filter) could read across tenants.

    This migration closes the gap for all four remaining tables. Each already
    carries a ``tenant_id`` column, which is all the policy needs; no schema
    change to the tables is required. After this migration, every table in the
    ``application`` app that stores tenant data is RLS-protected.

Policy semantics (identical to persistence/0003 and application/0009):
    Each table gets RLS enabled + FORCE (so the application DB role, typically
    the table owner, is also constrained) plus a policy exposing only rows whose
    ``tenant_id`` equals the session variable ``app.current_tenant`` (set per
    request via ``SET app.current_tenant`` — see persistence/middleware.py). An
    unset/empty setting matches no rows (empty result), satisfying
    REQ-L2-PL-010's "direct DB access without the setting -> empty result"
    criterion.

    Note that a superuser bypasses RLS unconditionally, even with FORCE. Only
    connections authenticated as the least-privilege application role
    (``persistence.db_roles.APP_DB_ROLE``, created in persistence/0048) are
    actually constrained — which is what production and Celery traffic use.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

# The remaining tenant-scoped tables owned by the application app. Each carries
# a ``tenant_id`` UUID column. ``as_risk``/``as_issue`` are already covered by
# migration 0009 and are deliberately not repeated here (CREATE POLICY is not
# idempotent — re-declaring them would fail on an already-migrated database).
_TENANT_TABLES = [
    "as_adr",
    "as_change_request",
    "as_goal",
    "as_main_goal",
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
        # Creates as_goal / as_main_goal; transitively covers as_change_request
        # (0011) and as_adr (0003).
        ("application", "0012_add_goal_and_main_goal"),
        # The original RLS sweep, for ordering parity with 0009.
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
