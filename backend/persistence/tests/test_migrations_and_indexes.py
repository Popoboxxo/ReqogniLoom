"""
COMP-PL-004 SchemaMigrationEngine + COMP-PL-005 PerformanceOptimizationLayer.

Covers:
- REQ-L2-PL-006 / REQ-L3-PL004-001 (makemigrations --check is clean)
- REQ-L2-PL-003 / REQ-L3-PL005-001 (BTree, graph and full-text indexes exist)
- REQ-L2-PL-010 (RLS enabled on tenant-scoped tables)

The index/RLS assertions are PostgreSQL-specific and are skipped on other
backends so the suite stays green on a non-PostgreSQL test DB.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django.db import connection

from persistence import models as m

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def test_no_missing_migrations():
    """REQ-L3-PL004-001: models and migrations are in sync."""
    # Raises SystemExit(1) if migrations are missing.
    call_command("makemigrations", "persistence", check=True, dry_run=True)


def _index_names() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
        )
        return {row[0] for row in cursor.fetchall()}


def _index_definitions(table: str) -> dict[str, str]:
    """Map index name -> ``pg_get_indexdef`` text for one table.

    The definition text ends with the key column list, e.g.
    ``... USING btree (created_at, id)``, which lets a test distinguish a
    single-column index from a composite one without joining ``pg_index`` /
    ``pg_attribute``.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = %s",
            [table],
        )
        return {name: ddl for name, ddl in cursor.fetchall()}


@_pg_only
def test_index_hygiene_1411():
    """Issue #1411: one redundant index dropped, one missing sort index added.

    Kept as a single assertion pair because both halves are the same
    migration-level concern: which indexes the schema actually carries after
    ``migrate``, read straight from the PostgreSQL catalog rather than from
    Django state (which would agree with the model even if the migration never
    ran). See ``_index_definitions`` for why the whole catalog, including
    ``at_refresh_token``, is read here.
    """
    # --- R8-08: the TraceLink list sort key is now index-backed. -----------
    tracelink = _index_definitions("pl_tracelink")
    assert "idx_tracelink_created" in tracelink, (
        "Issue #1411 (R8-08): TraceLinkManager.list() orders by "
        "('created_at', 'id') but pl_tracelink has no index on that sort key. "
        f"Existing indexes: {sorted(tracelink)}"
    )
    assert tracelink["idx_tracelink_created"].rstrip().endswith(
        "(created_at, id)"
    ), (
        "idx_tracelink_created must cover both sort columns in order; "
        f"got: {tracelink['idx_tracelink_created']}"
    )
    # REQ-L3-PL005-001: the graph index must survive #1411 untouched.
    assert "idx_tracelink_graph" in tracelink

    # --- R8-07(d): the redundant standalone session_id B-tree is gone. -----
    refresh_token = _index_definitions("at_refresh_token")
    single_column_session_id = [
        name
        for name, ddl in refresh_token.items()
        if ddl.rstrip().endswith("(session_id)")
    ]
    assert not single_column_session_id, (
        "Issue #1411 (R8-07(d)): a standalone btree on at_refresh_token"
        "(session_id) is a strict prefix of the composite "
        "idx_refresh_session_active(session_id, revoked_at) and must not "
        f"exist. Found: {single_column_session_id}"
    )
    # The composite that replaces it — and that keeps the 0021 lookup/revoke
    # functions index-covered — must still be present.
    assert "idx_refresh_session_active" in refresh_token
    assert refresh_token["idx_refresh_session_active"].rstrip().endswith(
        "(session_id, revoked_at)"
    )


@_pg_only
def test_btree_and_graph_indexes_exist():
    """REQ-L3-PL005-001: BTree (parent) and graph (source,target) indexes exist."""
    names = _index_names()
    assert "idx_artifact_parent_btree" in names
    assert "idx_tracelink_graph" in names


@_pg_only
def test_fulltext_indexes_exist():
    """REQ-L3-PL005-001: tsvector GIN indexes exist for the FTS entities."""
    names = _index_names()
    assert "idx_requirement_fts_gin" in names
    assert "idx_arch_element_fts_gin" in names
    assert "idx_testcase_fts_gin" in names


@_pg_only
def test_rls_enabled_on_tenant_tables():
    """REQ-L2-PL-010: RLS is enabled on tenant-scoped tables."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class "
            "WHERE relrowsecurity = true AND relname LIKE 'pl_%'"
        )
        rls_tables = {row[0] for row in cursor.fetchall()}
    assert "pl_requirement" in rls_tables
    assert "pl_artifact" in rls_tables
    assert "pl_tracelink" in rls_tables


@_pg_only
def test_rls_blocks_raw_query_without_set_local(tenant_a, workspace_a):
    """REQ-L2-PL-010: Verify RLS physically blocks raw SQL SELECTs outside context."""
    from persistence.db_roles import APP_DB_ROLE
    from persistence.middleware import clear_request_tenant, set_request_tenant

    # ``active_tenant`` only sets the thread-local app-layer context — it never
    # touches the DB session variable ``app.current_tenant`` that the RLS policy
    # (migration 0003) checks. To exercise RLS we must propagate the tenant to
    # BOTH layers via set_request_tenant, so the INSERT satisfies the policy's
    # WITH CHECK clause, then clear it so the raw SELECT runs with no tenant
    # context at the DB layer.
    set_request_tenant(tenant_a.id)
    try:
        art = m.Artifact.objects.create(tenant=tenant_a, workspace=workspace_a, artifact_type="x")
        m.Requirement.objects.create(tenant=tenant_a, artifact=art, title="rls-test")
    finally:
        clear_request_tenant()

    # app.current_tenant is now RESET. The test connection authenticates as the
    # migration-runner (superuser), which always bypasses RLS regardless of
    # FORCE ROW LEVEL SECURITY. SET ROLE to the dedicated non-superuser
    # application role (migration 0048) so this assertion actually exercises
    # what production traffic experiences.
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("SELECT * FROM pl_requirement WHERE title = 'rls-test'")
            rows = cursor.fetchall()
        finally:
            cursor.execute("RESET ROLE")

    assert len(rows) == 0, "RLS failed to block direct SQL access without SET LOCAL app.current_tenant"
