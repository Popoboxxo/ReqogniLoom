"""COMP-PL-006 RLSPolicyEnforcer — RLS for ``bl_baseline_tag`` (F4.2).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Policy semantics are byte-identical to ``baseline/0008_baseline_gate_waiver_rls``
and ``0006_baseline_snapshot_rls``: ENABLE + FORCE ROW LEVEL SECURITY plus one
``ALL`` policy keyed on the session variable ``app.current_tenant``. An
unset/empty setting matches no rows.

Reverse drops the policy and turns both flags off, leaving the table (and its
data) in place — ``0012`` owns the table lifecycle.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "bl_baseline_tag"
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
        ("baseline", "0012_baselinetag"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_ENABLE_SQL, reverse_sql=_DISABLE_SQL),
    ]
