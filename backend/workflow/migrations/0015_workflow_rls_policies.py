"""
COMP-PL-006 RLSPolicyEnforcer — RLS for the ``we_*`` WorkflowEngine tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    All four WorkflowEngine tables are ``TenantScopedModel`` subclasses that
    shipped without an RLS policy. ``we_history_entry`` in particular is an
    audit-adjacent record of who moved which item into which state — a
    cross-tenant read there leaks process metadata. All four already carry a
    ``tenant_id`` UUID column, so no schema change is required; this migration
    is purely additive DDL.

    ``GlobalWorkflowDefinition`` is "global" only in the sense of
    tenant-wide-per-item-type; it is still a ``TenantScopedModel`` with a
    per-tenant ``tenant_id`` row, so the standard policy applies unchanged.

Policy semantics (byte-identical to persistence/0003):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows, satisfying REQ-L2-PL-010.

Access-path review:
    * ``workflow.services`` / ``workflow.lifecycle_manager`` /
      ``workflow.definition_store`` run inside request-scoped services, where
      ``TenantContextService.activate`` has armed both isolation layers.
      ``definition_store`` additionally guards its ``GlobalWorkflowDefinition``
      write behind an explicit ``TenantContext.get_tenant()`` probe and skips
      the write when no context is active.
    * ``se_metrics.aggregator`` reads these tables from worker threads and
      explicitly calls ``set_request_tenant`` per thread (fix #405) precisely
      because RLS applies there — that code path was written for this.

KNOWN DEGRADATION — ``reqogniloom.health``:
    The readiness check counts definitions with empty ``states`` via
    ``GlobalWorkflowDefinition.unscoped`` / ``WorkflowEngineDefinition.unscoped``
    on an unauthenticated request, so no ``app.current_tenant`` is armed. Under
    this policy those counts become 0 and the "workflow definition has no
    states" warning stops firing when the app connects as the least-privilege
    ``reqogniloom_app`` role. That is a lost warning, not an outage: the block
    is already wrapped in a ``try/except`` that only appends to
    ``status["warnings"]``, and the check cannot produce a false *alarm*, only
    a false *silence*. Restoring it requires iterating tenants with
    ``set_request_tenant`` (the ``se_metrics.aggregator`` shape) and is tracked
    as follow-up work rather than blocking this isolation fix.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "we_global_definition",
    "we_engine_definition",
    "we_item_state",
    "we_history_entry",
]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0014_testcase_status_lowercase"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
