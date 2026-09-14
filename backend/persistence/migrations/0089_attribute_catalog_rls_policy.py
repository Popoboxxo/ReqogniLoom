"""
COMP-PL-006 RLSPolicyEnforcer — RLS policy for ``pl_attribute_catalog_entry``.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind COMP-PL-002 TenantManager)

``AttributeCatalogEntry`` (Attribut v3 WS5, #942) is a new
``TenantScopedModel``. Every tenant-scoped table added after
``0003_rls_policies.py`` ships its own policy migration — otherwise its
tenant isolation rests solely on the ORM-layer ``TenantManager`` filter, and
any query that bypasses the manager (raw SQL, ``unscoped`` without an
explicit ``tenant_id``) can read across tenants.
``persistence/tests/test_rls_coverage.py`` enforces this at model-add time.

Policy semantics are byte-identical to the other policy migrations (0003,
0067, 0086, ...): ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy
exposing only rows whose ``tenant_id`` equals the session variable
``app.current_tenant`` (armed by
``persistence.middleware.set_request_tenant`` per request and explicitly by
worker entry points). An unset/empty setting matches no rows.

Access path: all catalog reads/writes go through
``application.attribute_catalog_service.AttributeCatalogService``, which
activates the tenant context (``ServiceBase._set_tenant_context``) before any
query, so the standard policy is exactly what it expects.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "pl_attribute_catalog_entry"
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
        ("persistence", "0088_attribute_catalog_entry"),
    ]

    operations = [
        migrations.RunSQL(sql=_ENABLE_SQL, reverse_sql=_DISABLE_SQL),
    ]
