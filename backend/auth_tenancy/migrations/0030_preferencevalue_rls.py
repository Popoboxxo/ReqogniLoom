"""auth_tenancy — Row-Level Security for ``at_preference_value`` (Q1, #1094).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the service-layer filter)

``PreferenceValue`` is a ``TenantScopedModel`` (see 0029), so it must ship the
standard policy or ``persistence/tests/test_rls_coverage.py`` fails. Policy
shape is byte-identical to ``auth_tenancy/0026_treedisplayconfig_rls.py``:
ENABLE + FORCE RLS plus one ``ALL`` policy keyed on ``app.current_tenant``. An
unset/empty setting matches no rows (closed-world default). The table is only
ever touched by an authenticated REST/MCP route, i.e. after
``TenantContextService.activate`` has armed the session variable.

The policy is the outermost of three isolation layers for this table: the
service-layer filter, the ``tenant`` column in every uniqueness constraint and
this policy. User-level rows are additionally narrowed in code (``ctx.user_id``
is the boundary for reading another principal's value) — RLS answers
"which tenant", not "which user".
"""

from django.db import migrations

_TABLE = "at_preference_value"
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
        ("auth_tenancy", "0029_preferencevalue"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
