"""F1 — delete ``we_*`` rows whose ``workspace_id`` no longer resolves.

Why this module exists
----------------------
``workflow/0021_we_item_state_integrity`` adds
``fk_we_state_workspace`` to ``we_item_state`` **without** ``NOT VALID``, so
PostgreSQL validates every existing row at ``ADD CONSTRAINT`` time. The POC
database carried 2739 ``we_item_state`` rows plus 42 ``we_engine_definition``
rows whose parent ``pl_workspace`` row is gone (historical bulk import /
load-test backfill, measured 2026-10-02/03 — see 0021's data preflight
docstring). Those rows raised ``ForeignKeyViolation``, the migration
transaction rolled back completely and ``migrate`` was deadlocked with no
``django_migrations`` entry.

Operator decision 2026-10-08: the orphans are unreachable legacy and **may be
deleted**; future truncation goes through the new FK/CASCADE.

Why a module and not just the command
-------------------------------------
The identical delete logic is needed in two places that must never drift apart:

* ``workflow.management.commands.cleanup_workflow_orphans`` — the operator-facing
  command the deploy stack runs **before** ``migrate`` (a cleanup migration
  depending on 0021 could never run on a database where 0021 still fails, and a
  second leaf node depending on 0020 trips ``MultipleLeafNodesError``).
* ``workflow/0022_we_engine_definition_workspace_fk`` — the in-migration
  ``RunPython`` pre-step that keeps a plain ``manage.py migrate`` from failing
  on the definition orphans.

The module is deliberately free of any model import: migrations must not depend
on the live model classes, and raw SQL is what both callers need anyway
(``we_item_state`` and ``we_engine_definition`` carry ``FORCE ROW LEVEL SECURITY``
since ``workflow/0015``, which applies to the table owner too).

Ordering is load-bearing
------------------------
``we_item_state`` is deleted first: every orphan item state observed on the POC
stack referenced an orphan definition, so clearing the states first is what
makes the definition delete legal (``WorkflowItemState.definition`` is
``on_delete=PROTECT``). A definition that is still referenced by a *valid*
item state makes the second ``DELETE`` fail loudly at the database instead of
silently deleting reachable data — fail-closed by design.

Idempotency
----------
Both statements are ``DELETE ... WHERE NOT EXISTS ...``, so re-running is a
no-op that reports 0 rows. On a fresh database the tables do not exist yet;
:func:`delete_workspace_orphans` and :func:`count_workspace_orphans`
introspect ``information_schema`` first, so the first run is a no-op as well.

Reversibility
-------------
The deleted rows **cannot** be restored — there is no copy and no log of them,
and the operator decision explicitly accepted the loss (they were unreachable
legacy data). The reverse of every data step is therefore a documented no-op.
"""

from __future__ import annotations

from typing import Any

#: Parent table both orphans point at.
WORKSPACE_TABLE = "pl_workspace"

#: ``workflow.models.WorkflowItemState`` (``we_item_state``).
ITEM_STATE_TABLE = "we_item_state"

#: ``workflow.models.WorkflowEngineDefinition`` (``we_engine_definition``).
ENGINE_DEFINITION_TABLE = "we_engine_definition"

#: Deletion order — see the module docstring, "Ordering is load-bearing".
TABLES_IN_DELETE_ORDER: tuple[str, ...] = (ITEM_STATE_TABLE, ENGINE_DEFINITION_TABLE)


def _table_exists(cursor: Any, table: str) -> bool:
    """True when *table* is visible in the connection's current schema.

    Checked before acting so a fresh database (pre-``CreateModel``) is a
    no-op instead of a ``UndefinedTable`` abort.
    """
    cursor.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = %s",
        [table],
    )
    return cursor.fetchone() is not None


def _orphan_predicate() -> str:
    """The ``workspace_id`` has no parent row — shared by count and delete.

    ``SET LOCAL row_security = off`` (issued once per transaction by the
    functions below) is what makes these statements see the rows under
    ``FORCE ROW LEVEL SECURITY`` — the same house pattern as
    ``workflow/0018_restore_states_hijacked_by_outdate.py``.
    """
    return (
        "NOT EXISTS ("
        f'SELECT 1 FROM "{WORKSPACE_TABLE}" AS w WHERE w.id = orphan.workspace_id'
        ")"
    )


def count_workspace_orphans(connection: Any) -> dict[str, int]:
    """Count the orphans :func:`delete_workspace_orphans` would remove.

    Read-only counterpart for the command's ``--dry-run`` and for operators
    who want the number before deciding. Same transaction/RLS scoping rules as
    :func:`delete_workspace_orphans`.
    """
    counts: dict[str, int] = {table: 0 for table in TABLES_IN_DELETE_ORDER}

    with connection.cursor() as cursor:
        if not _table_exists(cursor, WORKSPACE_TABLE):
            return counts

        cursor.execute("SET LOCAL row_security = off")
        for table in TABLES_IN_DELETE_ORDER:
            if not _table_exists(cursor, table):
                continue
            cursor.execute(
                f'SELECT count(*) FROM "{table}" AS orphan '
                f"WHERE {_orphan_predicate()}"
            )
            counts[table] = cursor.fetchone()[0]

    return counts


def delete_workspace_orphans(connection: Any) -> dict[str, int]:
    """Delete workspace orphans from the ``we_*`` tables; return per-table counts.

    Runs in the caller's transaction — the caller is responsible for wrapping
    this in ``transaction.atomic()`` (the management command) or for relying on
    the migration's own atomic block (``RunPython``), because the
    ``SET LOCAL row_security = off`` below is only scoped to such a transaction.

    Returns a mapping ``{table_name: deleted_row_count}``; missing tables yield
    ``0`` rather than an error.
    """
    deleted: dict[str, int] = {table: 0 for table in TABLES_IN_DELETE_ORDER}

    with connection.cursor() as cursor:
        if not _table_exists(cursor, WORKSPACE_TABLE):
            # Pre-``CreateModel`` database: nothing to clean, nothing to report.
            return deleted

        # FORCE RLS applies to the table owner (workflow/0015), so without this
        # both DELETEs would silently match zero rows.
        cursor.execute("SET LOCAL row_security = off")

        for table in TABLES_IN_DELETE_ORDER:
            if not _table_exists(cursor, table):
                continue
            cursor.execute(
                f'DELETE FROM "{table}" AS orphan WHERE {_orphan_predicate()}'
            )
            deleted[table] = cursor.rowcount

    return deleted
