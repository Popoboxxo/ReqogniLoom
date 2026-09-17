"""
COMP-PL-006 RLSPolicyEnforcer — PostgreSQL Row-Level Security (Defense-in-Depth).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as second isolation layer behind COMP-PL-002 Custom Manager)

Architecture:
- L2_PersistenceLayerSystem_Architecture.md §3 (COMP-PL-006, IF-PL-INT-006)

Each tenant-scoped table gets RLS enabled plus a policy that only exposes rows
whose ``tenant_id`` equals the session variable ``app.current_tenant``. A Django
middleware (owned by AuthAndTenancy, ARCH-L1-011) must set this variable per
request via ``SET app.current_tenant = '<uuid>'`` (IF-PL-EXT-IN-008).

#522: this docstring (and the L2 architecture document) originally specified
``SET LOCAL``. ``persistence.middleware.set_request_tenant`` uses session-scoped
``SET`` instead, and must: ``ATOMIC_REQUESTS`` is off, so most requests run each
statement in its own auto-committed transaction and ``SET LOCAL`` would revert
after the first query — silently disabling RLS for the rest of the request
(fix #110). The scope is therefore the connection, paired with an unconditional
``RESET`` in ``clear_request_tenant``; see that module for the guarantees this
relies on.

Behaviour when ``app.current_tenant`` is unset/empty:
    The policy compares against ``current_setting('app.current_tenant', true)``
    (the second arg suppresses the error for a missing setting and returns NULL).
    A NULL/empty setting matches no rows → empty result set, satisfying the
    REQ-L2-PL-010 acceptance criterion "direct DB access without the setting →
    empty result".

NOTE (table owner / superuser): RLS does not apply to the table owner unless
``FORCE ROW LEVEL SECURITY`` is set. We enable FORCE so the application DB role
(typically the owner in this single-role deployment) is also constrained. The
migration runner connects as the owner; DDL is unaffected by RLS, so migrations
still run. See escalation note in the implementation report regarding a dedicated
least-privilege application role.
"""
from __future__ import annotations

from django.db import migrations

# All tenant-scoped tables (every TenantScopedModel subclass). Tenant and User
# are intentionally excluded: Tenant is the boundary itself and User may be
# tenant-less (platform admin).
_TENANT_TABLES = [
    "pl_role",
    "pl_workspace",
    "pl_artifact",
    "pl_requirement",
    "pl_architecture_element",
    "pl_tracelink",
    "pl_testcase",
    "pl_baseline",
    "pl_workflow_definition",
    "pl_workflow_state",
    "pl_audit_log_entry",
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
        ("persistence", "0002_fulltext_indexes"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
