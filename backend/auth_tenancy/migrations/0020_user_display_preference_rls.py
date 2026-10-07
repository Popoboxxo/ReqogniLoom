"""auth_tenancy — Row-Level Security for ``at_user_display_preference`` (#1096).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

``UserDisplayPreference`` is a ``TenantScopedModel`` (see 0019), so it must ship
the standard policy or ``persistence/tests/test_rls_coverage.py`` fails. Policy
shape is byte-identical to ``auth_tenancy/0011_rls_policies.py``: ENABLE + FORCE
RLS plus one ``ALL`` policy keyed on ``app.current_tenant``. An unset/empty
setting matches no rows (closed-world default). The table is only ever touched
by the authenticated self-service route, i.e. after
``TenantContextService.activate`` has armed the session variable.

PROPOSAL — authored manually for human review, NOT applied (no ``makemigrations``
/ ``migrate`` run). See the hand-off report for the approval gate.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010, Issue #1096
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "at_user_display_preference"
_POLICY = f"{_TABLE}_tenant_isolation"


def _enable_sql() -> str:
    return (
        f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {_POLICY} ON {_TABLE}\n"
        f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )


def _disable_sql() -> str:
    return (
        f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE};\n"
        f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0019_userdisplaypreference"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
