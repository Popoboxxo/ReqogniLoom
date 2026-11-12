"""COMP-PL-006 RLSPolicyEnforcer — RLS policy for the allocation table (ADR-028).

``Allocation`` is a ``TenantScopedModel``; ``test_rls_coverage.py`` fails the
build for any such table without a policy migration. Policy semantics are
byte-identical to 0136/0130/0128: ENABLE + FORCE ROW LEVEL SECURITY plus one
``ALL`` policy exposing only rows whose ``tenant_id`` equals
``app.current_tenant``.
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "pl_allocation"


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
        ("persistence", "0139_allocation"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
