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

pytestmark = pytest.mark.django_db

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
