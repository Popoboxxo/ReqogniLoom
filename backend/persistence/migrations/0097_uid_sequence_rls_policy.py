"""
COMP-PL-006 RLSPolicyEnforcer — RLS policy for the local-uid counter table.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind COMP-PL-002 TenantManager)

``UidSequence`` (issue #932) is a new ``TenantScopedModel``: a monotonic
``(workspace, item_type)`` counter behind
``application.local_uid.generate_local_uid``. Every tenant-scoped table added
after ``persistence/0003_rls_policies.py`` ships its own policy migration —
otherwise its isolation rests solely on the ORM-layer ``TenantManager`` filter,
and any query that bypasses the manager (raw SQL, ``unscoped`` without an
explicit ``tenant_id``) can read across tenants.
``persistence/tests/test_rls_coverage.py`` enforces this at model-add time.

Policy semantics are byte-identical to the other policy migrations (0003,
0086, 0089, 0091, ...): ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL``
policy exposing only rows whose ``tenant_id`` equals the session variable
``app.current_tenant``. An unset/empty setting matches no rows.

Access path: the counter is read and incremented inside an artifact-create
service, which has already armed the tenant context via
``ServiceBase._set_tenant_context`` before any query, so the standard policy is
exactly what it expects.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "pl_uid_sequence"


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
        ("persistence", "0096_alter_adr_uid_alter_architectureelement_uid_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
