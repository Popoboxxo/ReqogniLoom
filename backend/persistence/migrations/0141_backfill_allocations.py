"""Backfill ``Allocation`` rows from existing ``allocated-to`` trace links.

Every existing edge becomes one active allocation. Deliberately **draft**, not
``released``: the historical edges never carried a release decision, and a
retroactive release would freeze artefacts nobody released. The release path
(``POST /elements/{id}/release/``) sets ``released`` explicitly from now on.

Idempotent by construction: the partial unique constraint on
``(requirement_artifact, element_artifact)`` for active rows plus
``ON CONFLICT DO NOTHING`` means a second run inserts nothing.

R2D-004: the trace-link table is high-volume, so the forward step walks it in
1000-row keyset pages (``WHERE tl.id > %s ORDER BY tl.id LIMIT 1000``). Each
page commits on its own (``atomic = False`` + one ``transaction.atomic()`` per
page) and lifts RLS with ``SET LOCAL row_security = off`` inside that page's
transaction. Before the first write a dry-run count of links still lacking an
active allocation is taken: zero means no-op, which also makes a second run
cost no pages at all.

DELIBERATE ONE-WAY DOOR (S0.3-A / L0-002)
-----------------------------------------
This migration has **no reverse**. Reversing it used to issue an unqualified
bulk ``DELETE`` against ``pl_allocation``, which would wipe *every* allocation
— including the ones subsequently created through the API and released by users. The
backfilled draft rows carry no provenance marker that distinguishes them from
API-created rows ("drafts are indistinguishable from real allocations"), so a
targeted rollback is impossible. A broad delete is worse than an irreversible
forward step: it destroys live data on a routine ``migrate <app> 0140``. The
reverse is therefore ``RunSQL.noop`` on purpose — operators must use an
explicit, audited data-repair path instead of rolling this migration back.
Guarded by ``persistence/tests/test_backfill_allocations_reverse_guard.py``.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.db import migrations, router, transaction

logger = logging.getLogger(__name__)

#: Keyset page size (R2D-004).
BATCH_SIZE = 1000

#: Hard loop bound — a page count beyond this means the "already backfilled"
#: predicate never clears, not a real backfill.
MAX_BATCHES = 100_000

#: Full-set statement, kept for documentation/tests only. The migration never
#: executes it in one shot (R2D-004); :data:`_BATCH_INSERT_SQL` is per page.
_BACKFILL_SQL = """
INSERT INTO pl_allocation (
    id, tenant_id, workspace_id,
    requirement_artifact_id, element_artifact_id,
    status, is_primary, version, revocation_reason,
    created_at, modified_at
)
SELECT
    gen_random_uuid(), tl.tenant_id, req_artifact.workspace_id,
    tl.source_id, tl.target_id,
    'draft', true, 1, '',
    now(), now()
FROM pl_tracelink tl
JOIN pl_artifact req_artifact ON req_artifact.id = tl.source_id
WHERE tl.link_type = 'allocated-to'
ON CONFLICT DO NOTHING;
"""

#: Same insert restricted to one keyset page of trace-link ids.
_BATCH_INSERT_SQL = """
INSERT INTO pl_allocation (
    id, tenant_id, workspace_id,
    requirement_artifact_id, element_artifact_id,
    status, is_primary, version, revocation_reason,
    created_at, modified_at
)
SELECT
    gen_random_uuid(), tl.tenant_id, req_artifact.workspace_id,
    tl.source_id, tl.target_id,
    'draft', true, 1, '',
    now(), now()
FROM pl_tracelink tl
JOIN pl_artifact req_artifact ON req_artifact.id = tl.source_id
WHERE tl.link_type = 'allocated-to' AND tl.id = ANY(%s)
ON CONFLICT DO NOTHING;
"""

#: Links that still lack an active allocation. Mirrors the partial unique
#: constraint ``uq_allocation_active_pair`` so the dry-run count and the keyset
#: scan agree with what ``ON CONFLICT DO NOTHING`` would actually insert.
_NEEDS_BACKFILL = """
tl.link_type = 'allocated-to'
AND NOT EXISTS (
    SELECT 1 FROM pl_allocation AS a
    WHERE a.requirement_artifact_id = tl.source_id
      AND a.element_artifact_id = tl.target_id
      AND a.status IN ('draft', 'released')
)
"""


@contextmanager
def _page_transaction(connection: Any) -> Iterator[None]:
    """One committed keyset page, with RLS lifted for that page only."""
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
        yield


def _dry_run_count(connection: Any) -> int:
    """Count links that would be backfilled, before touching any data."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT count(*) FROM pl_tracelink AS tl WHERE {_NEEDS_BACKFILL}"
        )
        return int(cursor.fetchone()[0])


def _batched_backfill(connection: Any, *, dry_run: bool = False) -> int:
    """Insert one allocation per still-unallocated ``allocated-to`` link.

    Returns the pending count in dry-run mode, otherwise the number of pages
    committed. Raises :class:`RuntimeError` if the page loop runs away.
    """
    pending = _dry_run_count(connection)
    if dry_run:
        return pending
    if pending == 0:
        logger.info("0141 allocation backfill: no links left to backfill")
        return 0

    last_id = None
    pages = 0
    while True:
        with _page_transaction(connection):
            with connection.cursor() as cursor:
                if last_id is None:
                    cursor.execute(
                        f"SELECT tl.id FROM pl_tracelink AS tl "
                        f"WHERE {_NEEDS_BACKFILL} ORDER BY tl.id LIMIT %s",
                        [BATCH_SIZE],
                    )
                else:
                    cursor.execute(
                        f"SELECT tl.id FROM pl_tracelink AS tl "
                        f"WHERE {_NEEDS_BACKFILL} AND tl.id > %s "
                        "ORDER BY tl.id LIMIT %s",
                        [last_id, BATCH_SIZE],
                    )
                batch = [row[0] for row in cursor.fetchall()]
                if batch:
                    cursor.execute(_BATCH_INSERT_SQL, [batch])
                    last_id = batch[-1]
        if not batch:
            break
        pages += 1
        if pages > MAX_BATCHES:  # pragma: no cover - runaway guard
            raise RuntimeError(
                f"0141 allocation backfill exceeded {MAX_BATCHES} pages; "
                "aborting instead of looping indefinitely"
            )
        if len(batch) < BATCH_SIZE:
            break

    logger.info(
        "0141 allocation backfill: %d link(s) in %d page(s)", pending, pages
    )
    return pages


class _BatchedBackfillSQL(migrations.RunSQL):
    """A ``RunSQL`` whose forward step is a Python keyset batching callback.

    Deliberately a *subclass* of ``RunSQL`` (not ``RunPython``): the S0.3 / L0-002
    one-way-door guard asserts a single ``RunSQL`` operation whose
    ``reverse_sql is RunSQL.noop``. Batching the forward step in Python still
    satisfies that structural contract — Django's ``RunSQL`` cannot express a
    dynamic number of committed pages in a static SQL string.
    """

    def __init__(self, forward, reverse_sql) -> None:
        self._forward = forward
        super().__init__(sql=migrations.RunSQL.noop, reverse_sql=reverse_sql)

    def database_forwards(self, app_label, schema_editor, from_state, to_state) -> None:
        if router.allow_migrate(
            schema_editor.connection.alias, app_label, **self.hints
        ):
            if getattr(schema_editor, "collect_sql", False):
                # ``sqlmigrate`` must not execute the batching callback: it is
                # a dry inspection command, not a migration run.
                schema_editor.collected_sql.append(
                    "-- 0141: batched keyset INSERT ... SELECT over "
                    "pl_tracelink (link_type = 'allocated-to'), 1000 rows/page"
                )
                return
            if schema_editor.connection.vendor != "postgresql":
                return
            self._forward(schema_editor.connection)


def _forward(connection: Any) -> None:
    _batched_backfill(connection)


class Migration(migrations.Migration):
    """One-way backfill; see the module docstring for the one-way-door rationale."""

    dependencies = [
        ("persistence", "0140_allocation_rls_policy"),
    ]

    # R2D-004: commit between keyset pages instead of one long transaction.
    atomic = False

    operations = [
        _BatchedBackfillSQL(
            forward=_forward,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
