"""Staged pre-auth RLS policy (issue #1136, IC-1d).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

This migration brings the two pre-auth ``at_*`` tables into RLS scope, but
behind a GUC guard so the DEFAULT-OFF ship changes no behaviour:

    current_setting('app.rls_preauth_enforced', true) IS DISTINCT FROM 'on'
    OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid

When ``app.rls_preauth_enforced`` is unset (the default) the first operand is
TRUE and the policy is fully permissive — identical to no policy at all. Only
``RLS_PREAUTH_ENFORCED=true`` (which wires ``-c app.rls_preauth_enforced=on``
into the app-role connection OPTIONS, see ``reqogniloom/settings.py``) arms the
tenant predicate. The pre-auth credential reads keep working in the armed
state because they were moved behind the ``SECURITY DEFINER`` functions in
``0016_auth_api_key_lookup_functions``.

Deliberately NO ``FORCE ROW LEVEL SECURITY``: ``APP_DB_ROLE`` is not the table
owner, so it is bound to the policy without FORCE; FORCE would only bind owner
connections (the migration runner / superuser test connection) and would not
rescue the (superuser-owned) definer functions — see residual R-8.

Reverse: drop the policy, clear FORCE, disable RLS.
"""
from __future__ import annotations

from django.db import migrations

#: Tables moved into staged RLS scope by this migration.
_PREAUTH_TABLES = ["at_api_key", "at_user_role"]

_GUC = "app.rls_preauth_enforced"


def _enable_sql() -> str:
    parts = []
    for table in _PREAUTH_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (\n"
            f"        current_setting('{_GUC}', true) IS DISTINCT FROM 'on'\n"
            f"        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid\n"
            f"    )\n"
            f"    WITH CHECK (\n"
            f"        current_setting('{_GUC}', true) IS DISTINCT FROM 'on'\n"
            f"        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid\n"
            f"    );"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _PREAUTH_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0016_auth_api_key_lookup_functions"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
