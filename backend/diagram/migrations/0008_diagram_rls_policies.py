"""
COMP-PL-006 RLSPolicyEnforcer — RLS for the ``diagram_*`` tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    ``Diagram`` and ``DiagramVersion`` are ``TenantScopedModel`` subclasses
    whose tables shipped without an RLS policy — tenant isolation relied solely
    on the ORM-layer filter. Both already carry a ``tenant_id`` UUID column, so
    no schema change is required; this migration is purely additive DDL.

Policy semantics (byte-identical to persistence/0003):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows, satisfying REQ-L2-PL-010.

Access-path review:
    ``diagram.manager`` reads ``DiagramVersion.unscoped`` with an explicit
    ``tenant_id=`` from request-scoped services (context armed by
    ``TenantContextService.activate``). ``diagram/admin.py`` uses ``unscoped``
    for cross-tenant Django-admin listings — already the situation for every
    table covered by ``persistence/0003``, so no new behaviour class.

    ``diagram/management/commands/convert_canvas_to_node_graph.py`` iterates
    ``Diagram.unscoped`` from a maintenance context with no tenant armed. Under
    this policy that command sees zero rows when run as the least-privilege
    ``reqogniloom_app`` role. This is the same constraint that already applies
    to ``workflow/management/commands/provision_workflow_definitions.py``
    (which iterates the RLS-protected ``pl_workspace``): such cross-tenant
    maintenance commands must be run as a superuser connection, or be reworked
    to arm ``set_request_tenant`` per tenant. Flagged here rather than silently
    accepted.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "diagram_diagram",
    "diagram_diagramversion",
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
        ("diagram", "0007_diagram_artifact"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
