"""Backfill + validate the staged ``tenant_id`` anchor (#1136, IC-2 / P5).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)

Backfills the nullable ``tenant_id`` added in ``0030`` from
``pl_workspace.tenant_id``: directly for the three tables that carry a
``workspace_id``, and via the owning ``WebhookSubscription`` for
``as_webhook_delivery_log`` (which has none of its own). Then validates the
``NOT VALID`` FK constraints.

R2D-004: the four event tables are high-volume. A single unbatched UPDATE per
table would hold row locks and a large undo log for the whole operation, so the
forward (and reverse) walk each table in 1000-row keyset pages
(``WHERE id > %s ORDER BY id LIMIT 1000``). Each page commits on its own
(``atomic = False`` + one ``transaction.atomic()`` per page) and disables RLS
with ``SET LOCAL row_security = off`` *inside* that page's transaction. A
dry-run count is taken before the first write so an empty table is a no-op and
a runaway loop is caught.

Orphan policy (O-2, decided): a ``workspace_id`` that resolves to no tenant
leaves ``tenant_id`` NULL. **Nothing is deleted and nothing raises** — the
migration counts the orphans per table and logs a WARNING. Orphans are
fail-closed under enforcement (``NULL = ...`` is NULL, no match) and invisible
by default (the policy predicate is permissive while the GUC is unset).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.db import migrations, transaction

logger = logging.getLogger(__name__)

#: Keyset page size (R2D-004). Small enough to bound lock/undo pressure.
BATCH_SIZE = 1000

#: Hard loop bound: a page count beyond this means the anchor predicate is
#: broken (e.g. an UPDATE that never clears ``tenant_id``), not a real backfill.
MAX_BATCHES = 100_000

#: ``(table, UPDATE statement for one id page)``. ``%s`` is bound to a list of
#: UUIDs and used with ``= ANY(%s)`` so each page is one indexed statement.
_BACKFILLS: list[tuple[str, str]] = [
    (
        "as_domain_event_outbox",
        "UPDATE as_domain_event_outbox AS t SET tenant_id = w.tenant_id "
        "FROM pl_workspace AS w "
        "WHERE t.id = ANY(%s) AND t.workspace_id = w.id AND t.tenant_id IS NULL",
    ),
    (
        "as_domain_event_dlq",
        "UPDATE as_domain_event_dlq AS t SET tenant_id = w.tenant_id "
        "FROM pl_workspace AS w "
        "WHERE t.id = ANY(%s) AND t.workspace_id = w.id AND t.tenant_id IS NULL",
    ),
    (
        "as_webhook_subscription",
        "UPDATE as_webhook_subscription AS t SET tenant_id = w.tenant_id "
        "FROM pl_workspace AS w "
        "WHERE t.id = ANY(%s) AND t.workspace_id = w.id AND t.tenant_id IS NULL",
    ),
    (
        "as_webhook_delivery_log",
        "UPDATE as_webhook_delivery_log AS t SET tenant_id = w.tenant_id "
        "FROM as_webhook_subscription AS s "
        "JOIN pl_workspace AS w ON w.id = s.workspace_id "
        "WHERE t.id = ANY(%s) AND t.subscription_id = s.id AND t.tenant_id IS NULL",
    ),
]

_TABLES = [table for table, _ in _BACKFILLS]


def _constraint(table: str) -> str:
    return f"{table}_tenant_id_fk"


@contextmanager
def _page_transaction(connection: Any) -> Iterator[None]:
    """One committed keyset page, with RLS lifted for that page only.

    ``SET LOCAL`` is transaction-scoped, so it must be issued *inside* the
    ``atomic()`` block. ``atomic = False`` on the migration keeps Django from
    wrapping all pages in a single transaction.
    """
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
        yield


def _dry_run_count(connection: Any, table: str, predicate: str) -> int:
    """Count rows matching *predicate* before any write (R2D-004 guard)."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {table} WHERE {predicate}")
        return int(cursor.fetchone()[0])


def _batched_update(
    connection: Any,
    table: str,
    update_sql: str,
    *,
    predicate: str = "tenant_id IS NULL",
    dry_run: bool = False,
) -> int:
    """Update *table* in committed 1000-row keyset pages.

    Args:
        connection: The migration's Django database connection.
        table: Quoted-safe, module-defined table name.
        update_sql: ``UPDATE ... WHERE t.id = ANY(%s) ...`` statement.
        predicate: Which rows still need the write (drives the dry-run count
            and the keyset scan).
        dry_run: When True, only return the pending row count.

    Returns:
        Pending row count in dry-run mode, otherwise the number of pages
        actually committed.

    Raises:
        RuntimeError: If the page loop exceeds :data:`MAX_BATCHES`.
    """
    pending = _dry_run_count(connection, table, predicate)
    if dry_run:
        return pending
    if pending == 0:
        logger.info("RLS staged backfill: %s has no rows to fix", table)
        return 0

    last_id = None
    pages = 0
    while True:
        with _page_transaction(connection):
            with connection.cursor() as cursor:
                if last_id is None:
                    cursor.execute(
                        f"SELECT id FROM {table} WHERE {predicate} "
                        "ORDER BY id LIMIT %s",
                        [BATCH_SIZE],
                    )
                else:
                    cursor.execute(
                        f"SELECT id FROM {table} WHERE {predicate} "
                        "AND id > %s ORDER BY id LIMIT %s",
                        [last_id, BATCH_SIZE],
                    )
                batch = [row[0] for row in cursor.fetchall()]
                if batch:
                    cursor.execute(update_sql, [batch])
                    last_id = batch[-1]
        if not batch:
            break
        pages += 1
        if pages > MAX_BATCHES:  # pragma: no cover - runaway guard
            raise RuntimeError(
                f"RLS staged backfill of {table} exceeded {MAX_BATCHES} pages; "
                "aborting instead of looping indefinitely"
            )
        if len(batch) < BATCH_SIZE:
            break

    logger.info(
        "RLS staged backfill: %s — %d row(s) in %d page(s)", table, pending, pages
    )
    return pages


def _backfill(apps, schema_editor) -> None:
    if getattr(schema_editor, "collect_sql", False):
        schema_editor.collected_sql.append(
            "-- 0031: batched staged tenant_id backfill for 4 event tables"
        )
        return
    if schema_editor.connection.vendor != "postgresql":
        return
    connection = schema_editor.connection
    for table, sql in _BACKFILLS:
        _batched_update(connection, table, sql)
        # O-2: count the residual (unresolvable workspace anchor) after the
        # batched UPDATEs and log a WARNING — as the pre-R2D-004 code did.
        # Nothing is deleted; orphans stay NULL by design.
        orphans = _dry_run_count(connection, table, "tenant_id IS NULL")
        if orphans:
            logger.warning(
                "RLS staged backfill (#1136): %s row(s) of %s still have a "
                "NULL tenant_id (unresolvable workspace anchor); they stay "
                "NULL by design and become invisible when "
                "RLS_AS_ENFORCED is enabled.",
                orphans,
                table,
            )

    with connection.cursor() as cursor:
        for table in _TABLES:
            cursor.execute(
                f"ALTER TABLE {table} VALIDATE CONSTRAINT {_constraint(table)}"
            )


def _unbackfill(apps, schema_editor) -> None:
    """Reverse: set ``tenant_id`` back to NULL on all four tables.

    Intentionally lopsided, and safe to leave so: the FK constraint added in
    ``0030`` stays VALIDATED after this reverse. An all-NULL ``tenant_id``
    column trivially satisfies ``FOREIGN KEY (tenant_id) REFERENCES
    pl_tenant(id)`` (NULL values are not checked), so no ``ALTER CONSTRAINT ...
    NOT VALID`` is needed or wanted here. Re-running forward
    (``0030`` adds no constraint on a re-run, ``0031`` re-validates) restores
    the same state.

    Batched like the forward path (R2D-004) — the reverse would otherwise be
    another four unbounded full-table UPDATEs.
    """
    if getattr(schema_editor, "collect_sql", False):
        schema_editor.collected_sql.append(
            "-- 0031 reverse: batched tenant_id reset for 4 event tables"
        )
        return
    if schema_editor.connection.vendor != "postgresql":
        return
    connection = schema_editor.connection
    for table in _TABLES:
        _batched_update(
            connection,
            table,
            f"UPDATE {table} AS t SET tenant_id = NULL WHERE t.id = ANY(%s)",
            predicate="tenant_id IS NOT NULL",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0030_as_staged_tenant_id"),
    ]

    # R2D-004: each keyset page commits separately; the migration itself must
    # not be wrapped in one long transaction.
    atomic = False

    operations = [
        migrations.RunPython(_backfill, reverse_code=_unbackfill),
    ]
