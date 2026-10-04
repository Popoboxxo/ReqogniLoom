"""Staged RLS policy on the four ``as_*`` tables (#1136, IC-2 / P6).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Applies a GUC-guarded permissive policy to the four worker-owned tables after
their ``tenant_id`` was added + backfilled (``0030``/``0031``):

    current_setting('app.rls_as_enforced', true) IS DISTINCT FROM 'on'
    OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid

While ``app.rls_as_enforced`` is unset (the default) the policy is fully
permissive, so the Celery outbox poller and every existing path are unchanged.
Only ``RLS_AS_ENFORCED=true`` arms the tenant predicate — and that flip is a
deferred precondition (A4, poller tenant arming; residual R-2).

Deliberately NO ``FORCE ROW LEVEL SECURITY`` (APP_DB_ROLE is not the owner and
is bound without it). Reverse: drop the policy and disable RLS.
"""
from __future__ import annotations

from django.db import migrations

_TABLES = [
    "as_domain_event_outbox",
    "as_domain_event_dlq",
    "as_webhook_subscription",
    "as_webhook_delivery_log",
]

_GUC = "app.rls_as_enforced"


def _enable_sql() -> str:
    parts = []
    for table in _TABLES:
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
    for table in _TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0031_backfill_staged_tenant_id"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
