"""F1 — delete ``we_item_state`` / ``we_engine_definition`` workspace orphans.

Blocks removed
--------------
``workflow/0021_we_item_state_integrity`` installs ``fk_we_state_workspace`` on
``we_item_state`` without ``NOT VALID``, so PostgreSQL validates every existing
row. The database carried 2739 ``we_item_state`` rows and 42
``we_engine_definition`` rows whose parent ``pl_workspace`` row is gone
(historical bulk import / load-test backfill, measured 2026-10-02/03). Those
orphans raised ``ForeignKeyViolation`` at ``ADD CONSTRAINT`` time, the
migration's transaction rolled back completely and ``migrate`` could not record
``workflow/0021`` at all.

**Operator decision 2026-10-08:** the orphans are unreachable legacy data and
MAY be deleted; future truncation goes through the new FK/CASCADE. This command
is the sanctioned cleanup, and the deploy stack runs it *before* ``migrate``
(see the ``migrate`` service in ``deploy/docker-compose.yml``).

Why this is a command and not a migration
-----------------------------------------
A cleanup migration depending on 0021 can never run on a database where 0021
still fails — and a second leaf node depending on 0020 trips
``MultipleLeafNodesError``. The delete therefore has to happen *before* the
migration graph is walked. ``workflow/0022`` repeats the same delete as an
in-migration ``RunPython`` pre-step for the definition orphans, using the very
same logic in :mod:`workflow.workspace_orphans`.

Idempotency
-----------
Every delete is ``DELETE ... WHERE NOT EXISTS ...``: the second run reports 0
rows and changes nothing. Tables that do not exist yet (fresh database) are
detected via ``information_schema`` and skipped, so the first run of a fresh
deployment is also a no-op.

Reversibility
-------------
**Reversal is not possible.** Deleted rows cannot be restored — no copy, no log,
and the operator decision accepted the loss because the rows were unreachable
legacy data. The reverse of this operation is a documented no-op (the same
convention ``workflow/0018`` uses for its one-shot data step).

Usage::

    python manage.py cleanup_workflow_orphans
    python manage.py cleanup_workflow_orphans --dry-run

Runs inside ``transaction.atomic()`` with ``SET LOCAL row_security = off``:
``we_item_state`` and ``we_engine_definition`` carry ``FORCE ROW LEVEL SECURITY``
(``workflow/0015``), which applies to the table owner too and would otherwise
make both statements silently match zero rows.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from workflow.workspace_orphans import (
    TABLES_IN_DELETE_ORDER,
    count_workspace_orphans,
    delete_workspace_orphans,
)


class Command(BaseCommand):
    help = (
        "Delete workflow rows whose workspace_id no longer resolves "
        "(fix F1; prerequisites for workflow/0021 + 0022)."
    )

    def add_arguments(self, parser) -> None:
        # ``--no-input`` is accepted (and ignored) so the deploy stack can call
        # this command and ``migrate`` with the same flags: Django declares the
        # option per-command, not in ``BaseCommand``, so without it the one-shot
        # ``migrate`` container would abort with "unrecognized arguments".
        # The command never prompts — it carries no interactive step.
        parser.add_argument(
            "--no-input",
            action="store_true",
            dest="no_input",
            help="Accepted and ignored: this command never prompts.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]

        # The atomic block is load-bearing, not decoration: ``SET LOCAL
        # row_security = off`` is a no-op outside a transaction, and both
        # statements per table have to land together or not at all.
        with transaction.atomic():
            if dry_run:
                counts = count_workspace_orphans(connection)
            else:
                counts = delete_workspace_orphans(connection)

        total = sum(counts.values())
        verb = "would delete" if dry_run else "deleted"
        for table in TABLES_IN_DELETE_ORDER:
            self.stdout.write(
                f"{table}: workspace orphans {verb}: {counts[table]}"
            )

        if not total:
            self.stdout.write(
                self.style.SUCCESS("No workspace orphans found — nothing to do.")
            )
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"--dry-run: {total} row(s) would be deleted; nothing was "
                    "changed."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Workspace orphan cleanup complete ({total} row(s) deleted)."
            )
        )
