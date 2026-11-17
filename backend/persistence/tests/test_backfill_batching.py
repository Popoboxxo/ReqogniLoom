"""R2D-004 / R2D-006 — migration backfill safety tests.

R2D-004: the high-volume backfills in ``application/0031`` and
``persistence/0141`` must walk their tables in committed 1000-row keyset pages
instead of one unbounded statement. The fake connection below records the
statements a real Postgres would receive so page boundaries, RLS lifting and
idempotency can be asserted without seeding thousands of ORM rows.

R2D-006: running 0024's reverse while ``VectorField`` columns depend on the
extension must not raise, and the extension must survive — that is the whole
point of the ``RunSQL.noop`` reverse.
"""
from __future__ import annotations

import importlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from django.db import connection, migrations

_BACKFILL_0141 = importlib.import_module(
    "persistence.migrations.0141_backfill_allocations"
)
_BACKFILL_0031 = importlib.import_module(
    "application.migrations.0031_backfill_staged_tenant_id"
)
_PGVEC_0024 = importlib.import_module("persistence.migrations.0024_requirement_embedding")


def _normalize(sql: str) -> str:
    return " ".join(sql.split())


# ---------------------------------------------------------------------------
# Fake connection / cursor harness
# ---------------------------------------------------------------------------


@dataclass
class _FakeState:
    """Simulated rows for both backfills (ids are plain ints for ordering)."""

    links: dict[int, tuple[int, int]] = field(default_factory=dict)
    allocated: set[tuple[int, int]] = field(default_factory=set)
    event_rows: dict[str, set[int]] = field(default_factory=dict)
    pages: int = 0
    set_local: int = 0
    batch_sizes: list[int] = field(default_factory=list)


class _FakeCursor:
    def __init__(self, state: _FakeState) -> None:
        self._state = state
        self._result: list[tuple[Any, ...]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        statement = _normalize(sql)
        state = self._state

        if statement == "SET LOCAL row_security = off":
            state.set_local += 1
            self._result = []
            return

        if "SELECT count(*) FROM pl_tracelink" in statement:
            pending = [
                link_id
                for link_id, pair in state.links.items()
                if pair not in state.allocated
            ]
            self._result = [(len(pending),)]
            return

        if statement.startswith("SELECT count(*) FROM as_"):
            table = statement.split()[3]
            self._result = [(len(state.event_rows.get(table, set())),)]
            return

        if statement.startswith("SELECT tl.id FROM pl_tracelink"):
            pending = sorted(
                link_id
                for link_id, pair in state.links.items()
                if pair not in state.allocated
            )
            if params and len(params) == 2:
                pending = [link_id for link_id in pending if link_id > params[0]]
            limit = params[-1] if params else 1000
            self._result = [(link_id,) for link_id in pending[:limit]]
            return

        if statement.startswith("SELECT id FROM as_"):
            table = statement.split()[3]
            rows = sorted(state.event_rows.get(table, set()))
            if params and len(params) == 2:
                rows = [row for row in rows if row > params[0]]
            self._result = [(row,) for row in rows[: params[-1] if params else 1000]]
            return

        if statement.startswith("INSERT INTO pl_allocation"):
            for link_id in params[0]:
                state.allocated.add(state.links[link_id])
            return

        if statement.startswith("UPDATE as_"):
            table = statement.split()[1]
            state.event_rows[table].difference_update(params[0])
            return

        # SET LOCAL, ALTER TABLE ... VALIDATE CONSTRAINT: nothing to simulate.
        self._result = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._result

    def fetchone(self) -> tuple[Any, ...]:
        return self._result[0] if self._result else (None,)


class _FakeConnection:
    def __init__(self, state: _FakeState) -> None:
        self.state = state
        self.alias = "default"
        self.vendor = "postgresql"

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.state)


@contextmanager
def _fake_pages(state: _FakeState):
    """Replace ``transaction.atomic`` with a page counter for both modules.

    Both migration modules import the same ``django.db.transaction`` module, so
    a single patch covers them; patching each in turn would lose the original.
    """
    transaction_module = _BACKFILL_0141.transaction
    assert transaction_module is _BACKFILL_0031.transaction
    original = transaction_module.atomic

    def fake_atomic(*args: Any, using: str | None = None, **kwargs: Any):
        state.pages += 1
        return contextmanager(lambda: (yield))()

    transaction_module.atomic = fake_atomic  # type: ignore[assignment]
    try:
        yield
    finally:
        transaction_module.atomic = original


def _seed_links(count: int) -> _FakeState:
    state = _FakeState()
    for i in range(1, count + 1):
        # Distinct source ids: the production unique constraint allows only
        # one active primary allocation per requirement.
        state.links[i] = (i, 10_000)
    return state


# ---------------------------------------------------------------------------
# 0141 — allocation backfill
# ---------------------------------------------------------------------------


def test_0141_2500_rows_are_backfilled_in_three_committed_pages() -> None:
    state = _seed_links(2500)
    connection = _FakeConnection(state)

    with _fake_pages(state):
        pages = _BACKFILL_0141._batched_backfill(connection)

    assert pages == 3
    assert state.pages == 3, "each page must commit on its own"
    assert state.set_local == 3, "RLS must be lifted once per page transaction"
    assert len(state.allocated) == 2500, "every link became an allocation"
    assert state.allocated == {
        pair for pair in state.links.values()
    }, "all rows correct, none duplicated or skipped"


def test_0141_keyset_pages_are_ordered_and_bounded() -> None:
    state = _seed_links(2500)
    connection = _FakeConnection(state)

    sizes: list[int] = []
    original_execute = _FakeCursor.execute

    def recording_execute(self: _FakeCursor, sql: str, params: Any = None) -> None:
        statement = _normalize(sql)
        if statement.startswith("SELECT tl.id FROM pl_tracelink"):
            sizes.append(params[-1] if params else 1000)
        original_execute(self, sql, params)

    _FakeCursor.execute = recording_execute  # type: ignore[assignment]
    try:
        with _fake_pages(state):
            _BACKFILL_0141._batched_backfill(connection)
    finally:
        _FakeCursor.execute = original_execute  # type: ignore[assignment]

    assert sizes == [1000, 1000, 1000], "last page queries LIMIT 1000 as well"
    assert len(state.allocated) == 2500


def test_0141_second_run_is_a_noop() -> None:
    state = _seed_links(2500)
    connection = _FakeConnection(state)

    with _fake_pages(state):
        assert _BACKFILL_0141._batched_backfill(connection) == 3
    state.pages = 0
    state.set_local = 0

    with _fake_pages(state):
        assert _BACKFILL_0141._batched_backfill(connection) == 0
    assert state.pages == 0, "idempotent second run opens no page transaction"
    assert len(state.allocated) == 2500


def test_0141_dry_run_count_does_not_write() -> None:
    state = _seed_links(2500)
    connection = _FakeConnection(state)

    with _fake_pages(state):
        assert _BACKFILL_0141._batched_backfill(connection, dry_run=True) == 2500
    assert state.pages == 0
    assert state.allocated == set()


# ---------------------------------------------------------------------------
# 0031 — staged tenant_id backfill
# ---------------------------------------------------------------------------


def test_0031_batches_each_event_table_and_is_idempotent() -> None:
    state = _FakeState()
    for table, _ in _BACKFILL_0031._BACKFILLS:
        state.event_rows[table] = set(range(1, 2501))
    connection = _FakeConnection(state)

    with _fake_pages(state):
        for table, sql in _BACKFILL_0031._BACKFILLS:
            assert _BACKFILL_0031._batched_update(connection, table, sql) == 3

    assert state.pages == 12, "four tables x three pages"
    assert state.set_local == 12
    assert all(not rows for rows in state.event_rows.values()), "all rows correct"

    state.pages = 0
    with _fake_pages(state):
        for table, sql in _BACKFILL_0031._BACKFILLS:
            assert _BACKFILL_0031._batched_update(connection, table, sql) == 0
    assert state.pages == 0, "second run is a dry-run-count no-op"


def test_0031_dry_run_returns_pending_count() -> None:
    state = _FakeState()
    state.event_rows["as_domain_event_outbox"] = set(range(1, 2501))
    connection = _FakeConnection(state)
    table, sql = _BACKFILL_0031._BACKFILLS[0]

    with _fake_pages(state):
        assert (
            _BACKFILL_0031._batched_update(
                connection, table, sql, dry_run=True
            )
            == 2500
        )
    assert state.event_rows["as_domain_event_outbox"]
    assert state.pages == 0


# ---------------------------------------------------------------------------
# 0024 — extension reverse (R2D-005 / R2D-006)
# ---------------------------------------------------------------------------


def test_0024_reverse_is_noop_and_no_stale_init_hook_reference() -> None:
    operations = _PGVEC_0024.Migration.operations
    create_extension = next(
        op
        for op in operations
        if isinstance(op, migrations.RunSQL)
        and "CREATE EXTENSION" in str(op.sql)
    )
    assert create_extension.reverse_sql is migrations.RunSQL.noop
    source = _PGVEC_0024.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "docker/postgres/initdb/10-pgvector.sh" in text  # named as removed
    assert "retrofit" in text
    assert "DROP EXTENSION IF EXISTS vector;" not in text


@pytest.mark.django_db(transaction=True)
def test_0024_reverse_keeps_extension_with_dependent_vector_columns() -> None:
    """Reversing 0024 while vector columns exist must not drop the extension."""
    operation = next(
        op
        for op in _PGVEC_0024.Migration.operations
        if isinstance(op, migrations.RunSQL) and "CREATE EXTENSION" in str(op.sql)
    )
    # The test DB is migrated to HEAD, so dependent vector columns exist.
    with connection.schema_editor() as editor:
        operation.database_backwards("persistence", editor, None, None)

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        assert cursor.fetchone() == (1,)
