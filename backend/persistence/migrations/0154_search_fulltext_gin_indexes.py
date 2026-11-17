"""PERF-005: GIN full-text indexes for the remaining searchable tables.

``application/search_service._TABLE_SPECS`` publishes 14 searchable artifact
types. ``persistence/0002_fulltext_indexes.py`` only indexed three of them
(Requirement, ArchitectureElement, TestCase); the other eleven ran their
``to_tsvector('german', ...) @@ plainto_tsquery(...)`` predicate without an
index and therefore sequentially scanned the whole table on every query.

This migration adds the missing expression GIN indexes. The indexed expression
is copied verbatim from ``_run_fulltext_query`` for each type:

    to_tsvector('german',
        COALESCE(<title>, '') || ' ' || COALESCE(<description>, '')
        [ || ' ' || COALESCE(<extra_fulltext>, '')])

Column choices mirror ``_TableSpec`` exactly (e.g. GlossaryTerm uses
``term``/``definition``, Icd uses ``name``/``semantic_description``, Document
and WorkItem fold in ``body``, WorkItem's description is ``next_action`` and
TraceLink's synthetic title is built from link type + endpoint ids). An
expression index is only used when its expression matches the query's, so any
future change to ``_TableSpec`` must be accompanied by a matching index
migration (``persistence/tests/test_search_fulltext_indexes.py`` pins this).

CONCURRENTLY with a transaction-safe fallback: production and normal
``manage.py migrate`` runs build the indexes with ``CREATE INDEX CONCURRENTLY``
so no write lock is held on the busiest artifact tables. ``atomic = False``
makes Django run the migration in autocommit. Some runners — notably a fresh
pytest-django ``setup_databases`` cycle — open an outer transaction around the
whole migration plan; PostgreSQL then rejects ``CONCURRENTLY``. The operation
therefore inspects ``connection.in_atomic_block`` at *execution* time and
switches to a plain ``CREATE INDEX IF NOT EXISTS`` / ``DROP INDEX IF EXISTS``
inside a transaction, keeping identical names and expressions. The index is
still built; only its lock level differs, which is acceptable in a disposable
test database and is the only correct choice when CONCURRENTLY is impossible.

The SQL is passed as a LIST of separate statements, never one joined string:
PostgreSQL wraps a multi-statement string in a single implicit transaction,
which would reject CONCURRENTLY even in autocommit mode.

As in ``persistence/0153`` the operation is wrapped in
``SeparateDatabaseAndState`` with an empty state half: the indexes are physical
only and must not create a schema drift against the apps' ``Meta.indexes``.
``RunSQL`` is used instead of ``AddIndexConcurrently`` because Django's
Operation can only express column indexes, not expression indexes.

Recovery after a failed/non-atomic run: a half-built concurrent index is left
INVALID by PostgreSQL. ``IF NOT EXISTS`` will NOT repair it — drop the invalid
index with ``DROP INDEX CONCURRENTLY <name>`` first, then re-run the migration.

Deliberately NOT changed (gate PERF-005 / R2D-003 adaptation): no uniform
``LIMIT`` is added to the full-text query, and no live helper is imported into
this frozen migration. Both would be behaviour/audit changes outside this
change's scope.
"""
from __future__ import annotations

from django.db import migrations, router

# (table, index_name, title expression, description expression, extra expression)
# The expression list is derived from ``search_service._TABLE_SPECS``, excluding
# the three tables already covered by ``0002_fulltext_indexes.py``.
_FTS_TARGETS: list[tuple[str, str, str, str, str | None]] = [
    ("pl_stakeholder_need", "idx_stakeholder_need_fts_gin", "title", "description", None),
    ("as_adr", "idx_adr_fts_gin", "title", "description", None),
    ("as_risk", "idx_risk_fts_gin", "title", "description", None),
    ("as_issue", "idx_issue_fts_gin", "title", "description", None),
    ("as_change_request", "idx_change_request_fts_gin", "title", "description", None),
    ("as_goal", "idx_goal_fts_gin", "title", "description", None),
    ("pl_glossary_term", "idx_glossary_term_fts_gin", "term", "definition", None),
    ("icd_icd", "idx_icd_fts_gin", "name", "semantic_description", None),
    ("pl_document", "idx_document_fts_gin", "title", "description", "body"),
    ("pl_work_item", "idx_work_item_fts_gin", "title", "next_action", "body"),
    (
        "pl_tracelink",
        "idx_tracelink_fts_gin",
        "link_type || ': ' || source_id::text || ' → ' || target_id::text",
        "rationale",
        None,
    ),
]


def _tsvector_expression(title: str, description: str, extra: str | None) -> str:
    """Rebuild the exact expression ``_run_fulltext_query`` puts in its WHERE."""
    expr = f"COALESCE({title}, '') || ' ' || COALESCE({description}, '')"
    if extra:
        expr += f" || ' ' || COALESCE({extra}, '')"
    return f"to_tsvector('german', {expr})"


def _forward_sql(*, in_transaction: bool = False) -> list[str]:
    """CREATE statements; CONCURRENTLY only when no transaction is open."""
    verb = "CREATE INDEX" if in_transaction else "CREATE INDEX CONCURRENTLY"
    return [
        f"{verb} IF NOT EXISTS {index_name} ON {table} "
        f"USING GIN ({_tsvector_expression(title, description, extra)});"
        for table, index_name, title, description, extra in _FTS_TARGETS
    ]


def _reverse_sql(*, in_transaction: bool = False) -> list[str]:
    """DROP statements; CONCURRENTLY only when no transaction is open."""
    verb = "DROP INDEX" if in_transaction else "DROP INDEX CONCURRENTLY"
    return [
        f"{verb} IF EXISTS {index_name};"
        for _table, index_name, _title, _description, _extra in reversed(_FTS_TARGETS)
    ]


class _GinIndexSQL(migrations.RunSQL):
    """RunSQL that picks its DDL form from the *live* transaction state.

    ``atomic = False`` on the migration is necessary but not sufficient: a
    runner can open an outer transaction around the whole migration plan, in
    which case ``CONCURRENTLY`` is illegal. Deciding at execution time covers
    both contexts without duplicating the index list.
    """

    atomic = False

    def _statements(self, schema_editor, *, forward: bool) -> list[str]:
        in_transaction = bool(schema_editor.connection.in_atomic_block)
        builder = _forward_sql if forward else _reverse_sql
        return builder(in_transaction=in_transaction)

    def _run_fallback(self, schema_editor, app_label: str, *, forward: bool) -> None:
        if not router.allow_migrate(schema_editor.connection.alias, app_label, **self.hints):
            return
        for statement in self._statements(schema_editor, forward=forward):
            schema_editor.execute(statement)

    def database_forwards(self, app_label, schema_editor, from_state, to_state) -> None:
        self._run_fallback(schema_editor, app_label, forward=True)

    def database_backwards(self, app_label, schema_editor, from_state, to_state) -> None:
        self._run_fallback(schema_editor, app_label, forward=False)


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block; the
    # operation above downgrades gracefully when a runner opens one anyway.
    atomic = False

    dependencies = [
        ("persistence", "0153_tracelink_source_link_type_tenant_index"),
        # icd_icd is not owned by persistence; depend on its leaf migration so a
        # fresh database always has the table (and semantic_description) before
        # this migration creates idx_icd_fts_gin. icd/0015 only depends on
        # persistence/0130, so this adds no cycle.
        ("icd", "0015_icd_workspace_fk"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                _GinIndexSQL(sql=_forward_sql(), reverse_sql=_reverse_sql())
            ],
            state_operations=[],
        ),
    ]
