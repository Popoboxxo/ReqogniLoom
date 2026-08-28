"""
COMP-PL-006 RLSPolicyEnforcer — RLS for ``resilience_circuitbreakerstate``.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    ``CircuitBreakerState`` is a ``TenantScopedModel`` keyed on
    ``(tenant, target_subsystem)``. Without RLS a cross-tenant read exposes
    which tenants are hitting provider failures, and — worse — a cross-tenant
    *write* through a manager bypass could trip another tenant's breaker into
    Open, denying them LLM traffic. The table already carries a ``tenant_id``
    UUID column, so no schema change is required.

Policy semantics (byte-identical to persistence/0003):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows, satisfying REQ-L2-PL-010.

Access-path review:
    ``CircuitBreaker`` uses the tenant-scoped ``objects`` manager exclusively,
    so it already requires an active ``TenantContext``. The only entry point
    that constructs one, ``llm_adapter.resilient_transport._breaker_for``,
    probes ``TenantContext.get_tenant()`` first and returns a
    ``_NullCircuitBreaker`` (no DB access at all) when no context is active —
    so there is no code path that touches this table without a tenant.

    On the Celery side ``llm_adapter.tasks.run_capability`` arms the DB session
    variable via ``set_request_tenant(tenant_id)`` (fix #444) rather than the
    Python-only ``TenantContext.set_tenant``, which is exactly what this policy
    needs. ``resilience/admin.py`` uses ``unscoped`` for cross-tenant
    Django-admin listings — already the situation for every table covered by
    ``persistence/0003``.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "resilience_circuitbreakerstate"
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
        ("resilience", "0001_initial"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_ENABLE_SQL, reverse_sql=_DISABLE_SQL),
    ]
