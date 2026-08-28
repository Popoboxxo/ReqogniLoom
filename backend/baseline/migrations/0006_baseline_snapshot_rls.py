"""
COMP-PL-006 RLSPolicyEnforcer — RLS for ``bl_baseline_snapshot``.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    ``BaselineSnapshot`` is a ``TenantScopedModel`` whose table shipped without
    an RLS policy — a baseline snapshot is a full point-in-time copy of a
    tenant's artefacts, so a cross-tenant read here is the highest-value
    exfiltration target in the schema. The table already carries a ``tenant_id``
    UUID column, so no schema change is required.

Policy semantics (byte-identical to persistence/0003):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows, satisfying REQ-L2-PL-010.

Access-path review:
    ``baseline.store``, ``baseline.diff_engine`` and
    ``baseline.delta_index_builder`` query via ``unscoped`` with an explicit
    ``tenant_id=`` from request-scoped services. ``baseline.state_capture``,
    which runs in the same call chain, already reads the RLS-protected
    ``pl_artifact`` / ``pl_requirement`` / ``pl_tracelink`` tables — baselines
    demonstrably capture those artefacts today, which proves
    ``app.current_tenant`` is armed on this path.

NOTE: ``bl_delta_index_entry`` is NOT included. It is a plain
    ``models.Model`` (not a ``TenantScopedModel``) with no ``tenant_id``
    column; it is scoped transitively through its ``BaselineSnapshot`` FK.
    Protecting it would require a relation-based policy (an ``EXISTS`` subquery
    against ``bl_baseline_snapshot``), which is a different policy shape than
    the one used everywhere else in this codebase and therefore belongs in its
    own reviewed change.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "bl_baseline_snapshot"
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
        ("baseline", "0005_baselinedeltaindexentry_state"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_ENABLE_SQL, reverse_sql=_DISABLE_SQL),
    ]
