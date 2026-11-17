"""PERF-005: the full-text GIN indexes shipped by persistence/0154.

Four oracles:

1. all eleven expression indexes from migration 0154 are physically present in
   ``pg_indexes`` with the expected table and GIN method;
2. an ``EXPLAIN (ANALYZE, FORMAT JSON)`` of the *actual* SQL produced by
   ``search_service._run_fulltext_query`` over a discriminating corpus shows a
   bitmap/index scan on the new index and no sequential scan of the table;
3. search results are unchanged by ``type_filter`` and are not silently capped:
   no uniform ``LIMIT`` was added to the full-text pass (the gate explicitly
   rejected that behaviour change);
4. the migration's CONCURRENTLY/plain switch is correct and an in-transaction
   execution (the fresh ``setup_databases`` failure mode) does not raise.

PostgreSQL-only; the whole module skips on another backend. The EXPLAIN oracle
needs a database the runner can reach (``DB_HOST``/``DB_PASSWORD`` env vars).
"""
from __future__ import annotations

import contextlib
import importlib
import json
from collections.abc import Iterator
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from application.search_service import (
    SearchService,
    _TABLE_SPECS,
    _run_fulltext_query,
    _TableSpec,
)
from persistence.models import Adr
from persistence.tenancy import TenantContext
from persistence.tests.factories import editor_ctx, make_requirement, make_workspace

pytestmark = pytest.mark.django_db

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

_migration = importlib.import_module(
    "persistence.migrations.0154_search_fulltext_gin_indexes"
)
_FTS_TARGETS = _migration._FTS_TARGETS


def _walk(node: dict[str, Any]):
    """Yield a JSON EXPLAIN plan node and all of its descendants."""
    yield node
    for child in node.get("Plans", []):
        yield from _walk(child)


@contextlib.contextmanager
def _tenant_scope(tenant) -> Iterator[None]:
    """Arm the thread-local tenant context for the ORM writes under test."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@_pg_only
def test_all_search_fulltext_indexes_exist() -> None:
    """011: every target index exists, on the right table, using GIN."""
    expected = {name: table for table, name, *_rest in _FTS_TARGETS}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, tablename, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(%s)",
            [list(expected)],
        )
        found = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    assert set(found) == set(expected), (
        "missing full-text GIN indexes: "
        f"{sorted(set(expected) - set(found))}"
    )
    for name, (table, definition) in found.items():
        assert table == expected[name], (
            f"{name} is on {table!r}, expected {expected[name]!r}"
        )
        assert "using gin" in definition.lower(), (
            f"{name} is not a GIN index: {definition}"
        )
        assert "to_tsvector('german'" in definition, (
            f"{name} is not the German tsvector expression index: {definition}"
        )


@_pg_only
def test_fulltext_query_uses_the_gin_index(tenant) -> None:
    """The real search SQL is index-served on a discriminating corpus.

    3000 ADRs carry a common word and exactly one carries the rare search term.
    With the statistics refreshed, a sequential scan of ``as_adr`` would be far
    more expensive than the GIN bitmap scan, so the planner must use the new
    index. The SQL is captured from ``_run_fulltext_query`` itself rather than
    reconstructed, so this oracle cannot drift from the shipped query.
    """
    with _tenant_scope(tenant):
        workspace = make_workspace(tenant)
        rows = [
            Adr(
                tenant=tenant,
                workspace_id=workspace.id,
                title=f"Normalbetrieb ADR {index:04d}",
                description="Alltagseintrag ohne den Suchbegriff",
            )
            for index in range(3_000)
        ]
        rows.append(
            Adr(
                tenant=tenant,
                workspace_id=workspace.id,
                title="Zeppelin Seltenheitsfall",
                description="Einziger Treffer im Testkorpus",
            )
        )
        Adr.objects.bulk_create(rows, batch_size=1_000)

    with connection.cursor() as cursor:
        # Keep the tenant GUC armed for a least-privilege (non-superuser) runner.
        cursor.execute(
            "SELECT set_config('app.current_tenant', %s, true)", [str(tenant.id)]
        )
        cursor.execute("ANALYZE as_adr")
        cursor.execute("ANALYZE pl_artifact")

    spec = _TABLE_SPECS["Adr"]
    with CaptureQueriesContext(connection) as captured:
        hits = _run_fulltext_query("Adr", spec, "Zeppelin", tenant.id, workspace.id)
    assert captured.captured_queries, "the full-text pass issued no SQL"
    assert [hit.title for hit in hits] == ["Zeppelin Seltenheitsfall"]

    sql = captured.captured_queries[0]["sql"]
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql)
        raw_plan = cursor.fetchone()[0]
    plan = raw_plan[0]["Plan"] if isinstance(raw_plan, list) else raw_plan["Plan"]
    nodes = list(_walk(plan))

    index_nodes = [node for node in nodes if node.get("Index Name") == "idx_adr_fts_gin"]
    assert index_nodes, (
        "the full-text query did not use idx_adr_fts_gin; plan="
        f"{json.dumps(plan)[:2_000]}"
    )
    assert any(
        "Index Scan" in node.get("Node Type", "") for node in index_nodes
    ), (
        "idx_adr_fts_gin appeared in the plan but not as an index scan; plan="
        f"{json.dumps(plan)[:2_000]}"
    )
    seq_scans = [
        node.get("Relation Name")
        for node in nodes
        if node.get("Node Type") == "Seq Scan" and node.get("Relation Name") == "as_adr"
    ]
    assert not seq_scans, (
        "a sequential scan of as_adr means the GIN index was bypassed; "
        f"plan={json.dumps(plan)[:2_000]}"
    )


@_pg_only
def test_results_unchanged_with_and_without_type_filter(tenant) -> None:
    """No uniform LIMIT was added: filtering selects a subset, it does not cap.

    220 matching ADRs exceed the lexical pass's 200-row cap. The full-text pass
    is (and stays) uncapped for non-permission-scoped types, so ``total_count``
    must be 220 for the filtered query and 221 with one extra Requirement hit —
    a uniform ``LIMIT`` in the full-text SQL would show 200/201 instead.
    """
    with _tenant_scope(tenant):
        workspace = make_workspace(tenant)
        context = editor_ctx(tenant, workspace)
        Adr.objects.bulk_create(
            [
                Adr(
                    tenant=tenant,
                    workspace_id=workspace.id,
                    title=f"Zeppelin ADR {index:04d}",
                    description=f"Treffer {index}",
                )
                for index in range(220)
            ],
            batch_size=500,
        )
        make_requirement(workspace, title="Zeppelin Requirement")

        unfiltered = SearchService().search(
            "Zeppelin", context, workspace_id=workspace.id, mode="keyword", limit=100
        )
        filtered = SearchService().search(
            "Zeppelin",
            context,
            workspace_id=workspace.id,
            type_filter=["Adr"],
            mode="keyword",
            limit=100,
        )

    assert filtered.total_count == 220
    assert unfiltered.total_count == 221
    assert {hit.id for hit in filtered.results} == {
        hit.id for hit in unfiltered.results if hit.artifact_type == "Adr"
    }


def test_fts_targets_pin_every_unindexed_table_spec() -> None:
    """Static: 0154's expression list is derived from, and matches, _TABLE_SPECS (S2.2-02).

    Migration 0154's docstring claims `persistence/tests/test_search_fulltext_indexes.py`
    pins the index expressions to the live search specs. Make that claim true:
    for every searchable type NOT already indexed by ``0002``, derive the bare
    (title, description, extra) SQL expressions from the *live*
    ``search_service._TABLE_SPECS`` and require an exactly matching
    ``_FTS_TARGETS`` entry. A future change to a spec's fields or their order
    that is not mirrored in the migration must fail here.
    """
    migration_0002 = importlib.import_module(
        "persistence.migrations.0002_fulltext_indexes"
    )
    legacy_tables = {table for table, _name in migration_0002._FTS_TARGETS}

    def _bare(expr: str) -> str:
        # Migration targets store bare column names; specs use the ``e.`` alias.
        return expr.replace("e.", "")

    def _spec_columns(spec: _TableSpec) -> tuple[str, str, str | None]:
        """Derive (title, description, extra) expressions from a live spec."""
        title = _bare(spec.title_col)
        raw_description = _bare(spec.description_col)
        # description_col is stored as COALESCE(<expr>, ''); unwrap it because
        # _tsvector_expression adds that wrapper itself.
        prefix, suffix = "COALESCE(", ", '')"
        description = (
            raw_description[len(prefix) : -len(suffix)]
            if raw_description.startswith(prefix) and raw_description.endswith(suffix)
            else raw_description
        )
        extra = _bare(spec.extra_fulltext_col) if spec.extra_fulltext_col else None
        return title, description, extra

    derived = {
        spec.table: _spec_columns(spec)
        for _entity_type, spec in _TABLE_SPECS.items()
        if spec.table not in legacy_tables
    }
    indexed = {
        table: (title, description, extra)
        for table, _name, title, description, extra in _FTS_TARGETS
    }

    assert set(indexed) == set(derived), (
        "0154 target tables diverged from the unindexed _TABLE_SPECS: "
        f"missing={sorted(set(derived) - set(indexed))}, "
        f"unexpected={sorted(set(indexed) - set(derived))}"
    )
    for table, columns in derived.items():
        assert indexed[table] == columns, (
            f"{table}: migration stores {indexed[table]!r}, "
            f"live _TableSpec derives {columns!r}"
        )
        expected_sql = _migration._tsvector_expression(*columns)
        assert f"USING GIN ({expected_sql})" in " ".join(_migration._forward_sql()), (
            f"{table}: no forward-DDL statement carries expression {expected_sql!r}"
        )

    # The three legacy types belong to 0002 and must not be duplicated in 0154.
    assert legacy_tables == {
        "pl_requirement",
        "pl_architecture_element",
        "pl_testcase",
    }
    assert legacy_tables.isdisjoint(indexed)


@_pg_only
def test_sql_builders_switch_to_plain_ddl_inside_a_transaction() -> None:
    """Static: the fallback keeps names/expressions and only drops CONCURRENTLY."""
    plain = _migration._forward_sql(in_transaction=True)
    concurrent = _migration._forward_sql(in_transaction=False)
    assert len(plain) == len(concurrent) == len(_FTS_TARGETS)
    for forward_plain, forward_concurrent, (_table, name, *_rest) in zip(
        plain, concurrent, _FTS_TARGETS
    ):
        assert forward_plain.startswith(f"CREATE INDEX IF NOT EXISTS {name} ON ")
        assert forward_concurrent.startswith(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON "
        )
        # Identical table + expression after the differing verb prefix.
        assert forward_plain[len("CREATE INDEX IF NOT EXISTS") :] == forward_concurrent[
            len("CREATE INDEX CONCURRENTLY IF NOT EXISTS") :
        ]

    reverse_plain = _migration._reverse_sql(in_transaction=True)
    reverse_concurrent = _migration._reverse_sql(in_transaction=False)
    assert len(reverse_plain) == len(reverse_concurrent) == len(_FTS_TARGETS)
    assert all(statement.startswith("DROP INDEX IF EXISTS ") for statement in reverse_plain)
    assert all(
        statement.startswith("DROP INDEX CONCURRENTLY IF EXISTS ")
        for statement in reverse_concurrent
    )


@_pg_only
def test_in_transaction_migration_does_not_raise() -> None:
    """Simulate the fresh-setup failure mode: run both directions in a txn.

    pytest-django already opened an atomic block for this test — the exact
    context in which ``CREATE INDEX CONCURRENTLY`` raises. Calling the database
    operation directly there proves the fallback path is taken end-to-end
    (forward drops nothing, reverse drops the indexes without CONCURRENTLY, and
    a second forward re-creates them), with no transaction-state error.
    """
    from django.db.migrations.state import ProjectState

    assert connection.in_atomic_block, "pytest-django must wrap this test in a txn"
    operation = _migration.Migration.operations[0].database_operations[0]
    names = {name for _table, name, *_rest in _FTS_TARGETS}

    def _index_names() -> set[str]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = ANY(%s)",
                [list(names)],
            )
            return {row[0] for row in cursor.fetchall()}

    assert _index_names() == names

    with connection.schema_editor(atomic=True) as editor:
        assert editor.connection.in_atomic_block
        operation.database_backwards(
            "persistence", editor, ProjectState(), ProjectState()
        )
    assert _index_names() == set(), "in-transaction reverse did not drop the indexes"

    with connection.schema_editor(atomic=True) as editor:
        assert editor.connection.in_atomic_block
        operation.database_forwards(
            "persistence", editor, ProjectState(), ProjectState()
        )
    assert _index_names() == names, "in-transaction forward did not restore the indexes"
