"""
COMP-PL-006 RLSPolicyEnforcer — RLS for ``bl_delta_index_entry``.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as second isolation layer behind the ORM tenant filter)

Closes the deferral documented in ``0006_baseline_snapshot_rls.py`` ("``bl_delta_index_entry``
is NOT included ... a different policy shape than the one used everywhere else
in this codebase and therefore belongs in its own reviewed change"). That
review is this migration.

Shape: the table has no ``tenant_id`` column of its own — tenant identity is
inherited through the ``baseline_id`` FK — so this is a relation-based policy
rather than the direct ``tenant_id = ...`` comparison used everywhere else.
The ``EXISTS`` subquery against ``bl_baseline_snapshot`` is what keeps it
single-statement and index-friendly: ``bl_baseline_snapshot.id`` is the primary
key, so the subquery is one index lookup per candidate row. An unset/empty
``app.current_tenant`` makes the comparison NULL, so the subquery matches no
row and the policy hides every row — the same fail-closed semantics as the
direct policies.

Access-path review (unchanged by this migration — every path already proved
tenant ownership of the parent snapshot first, so the policy is transparent to
them and only closes the direct-query bypass):
    ``baseline.store.BaselineStore.create``          (bulk_create, parent just
        INSERTed by the same request-scoped call)
    ``baseline.store.BaselineStore.load_delta_index``/``load_states``/
        ``lookup_item_version``/``get`` (each gated on
        ``BaselineSnapshot.unscoped.filter(id=..., tenant_id=...)``)
    ``application.baseline_facade.BaselineFacade._memberships_armed`` (gated on
        ``BaselineSnapshot.unscoped.filter(tenant_id=ctx.tenant_id)``, with the
        tenant context armed)

All of them run request-scoped, where ``persistence.middleware`` has already
armed ``app.current_tenant``. Unit tests connect as the cluster owner role, for
which FORCE ROW LEVEL SECURITY is transparent, exactly as for ``0006``/``0008``.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "bl_delta_index_entry"
_PARENT_TABLE = "bl_baseline_snapshot"
_POLICY = f"{_TABLE}_tenant_isolation"

_TENANT_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"

_PARENT_MATCH = (
    f"EXISTS (SELECT 1 FROM {_PARENT_TABLE} p "
    f"WHERE p.id = {_TABLE}.baseline_id AND p.tenant_id = {_TENANT_EXPR})"
)

_ENABLE_SQL = (
    f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;\n"
    f"CREATE POLICY {_POLICY} ON {_TABLE}\n"
    f"    USING ({_PARENT_MATCH})\n"
    f"    WITH CHECK ({_PARENT_MATCH});"
)

_DISABLE_SQL = (
    f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE};\n"
    f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
)


class Migration(migrations.Migration):

    dependencies = [
        ("baseline", "0009_baselinegatewaiver_expires_at"),
        ("baseline", "0006_baseline_snapshot_rls"),
    ]

    operations = [
        migrations.RunSQL(sql=_ENABLE_SQL, reverse_sql=_DISABLE_SQL),
    ]
