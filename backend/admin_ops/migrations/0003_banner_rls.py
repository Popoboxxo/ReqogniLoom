"""
Migration 0003: PostgreSQL Row-Level Security for ``admin_ops_banner``.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

Background:
    ``Banner`` (added in ``0002_banner.py``) is a ``TenantScopedModel``, but its
    table shipped without an RLS policy — the same defense-in-depth gap that
    ``application/0009_risk_issue_rls_policies.py`` closed for ``as_risk``/
    ``as_issue``: a query bypassing the service layer could read across
    tenants. This migration closes it with the identical policy shape used by
    ``persistence/0003_rls_policies.py``, ``application/0009`` and
    ``context_graph/0001_initial.py``. ``admin_ops_banner`` already carries a
    ``tenant_id`` column, so no schema change is needed.

Policy semantics (identical to persistence/0003):
    RLS is enabled *and* FORCEd. FORCE matters as much as ENABLE: DDL and
    runtime traffic may share the table-owner role, which bypasses an
    ENABLE-only policy entirely. The policy exposes only rows whose
    ``tenant_id`` equals the session variable ``app.current_tenant``, set per
    authenticated request by ``persistence.middleware.set_request_tenant``. An
    unset/empty setting matches no rows, satisfying REQ-L2-PL-010's "direct DB
    access without the setting -> empty result" criterion.

Interaction with the unauthenticated login-banner endpoint:
    ``GET /api/v1/public/banners/login/`` reads this table on a request that
    the tenant middleware never touches (no credential -> no
    ``app.current_tenant``), so under this policy it would read zero rows.
    ``BannerService.get_login_banner`` therefore activates the resolved tenant
    explicitly via ``set_request_tenant`` for the duration of that single read
    and restores the prior context in a ``finally``. That pairing is what keeps
    the public endpoint working; see the method's docstring and
    ``admin_ops/tests/test_banner_rls.py::test_login_banner_read_works_under_rls``.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "admin_ops_banner"
_POLICY = f"{_TABLE}_tenant_isolation"

_ENABLE_SQL = (
    f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;\n"
    f"CREATE POLICY {_POLICY} ON {_TABLE}\n"
    f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
    f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
)

_DISABLE_SQL = (
    f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE};\n"
    f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
)


class Migration(migrations.Migration):

    dependencies = [
        ("admin_ops", "0002_banner"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_ENABLE_SQL, reverse_sql=_DISABLE_SQL),
    ]
