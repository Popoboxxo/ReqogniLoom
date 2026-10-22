"""G1.4 (#1403, QR-S16) — archive and delete orphaned type definitions.

``lt_workspace_definition`` / ``ad_workspace_definition`` used to carry a bare
``workspace_id`` UUID with no FK, so deleting a workspace left unreachable
"orphan" definitions behind. The G1.4 migrations add the FK; a validated
``ADD CONSTRAINT`` re-checks every existing row, so the orphans must be removed
first or the migration aborts.

ENT-G2 = A+ (decided 2026-10-22): deletion is **reversible**. The migration and
this command copy every row into ``<table>_orphan_archive`` in the same
statement that deletes it, and the migration's reverse copies it back.

Safety rails (all three are deliberate, fail-closed)
----------------------------------------------------
1. **BYPASSRLS role only.** The tables carry FORCE ROW LEVEL SECURITY, which
   applies to the table owner too. Under the app role ``count`` would report 0
   and the command would claim a clean database. The check is
   ``rolbypassrls OR rolsuper`` on ``current_user``; run it through the
   ``migrate`` compose service (superuser), never the ``backend`` container.
2. **Invisible-rows guard.** ``count(pl_workspace) = 0`` while definitions
   exist means the connection cannot see workspaces (RLS misconfiguration),
   not that every definition is an orphan — abort without changing anything.
3. **``--confirm-count`` required.** The operator must pass the exact total the
   dry run reported; a differing count aborts before the first delete, so a
   concurrent workspace delete cannot silently widen the blast radius.

Usage::

    python manage.py cleanup_workspace_orphans --dry-run
    python manage.py cleanup_workspace_orphans --confirm-count=232
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from workflow.workspace_orphans import (
    DEFINITION_TABLES,
    archive_and_delete_workspace_orphans,
    count_workspace_orphans,
)


def _current_role_can_bypass_rls() -> bool:
    """True when ``current_user`` has ``BYPASSRLS`` or is a superuser."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = current_user"
        )
        row = cursor.fetchone()
    return bool(row and row[0])


def _workspace_count() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pl_workspace")
        return cursor.fetchone()[0]


def _format(counts: dict[str, int]) -> str:
    return " ".join(f"{table}={counts[table]}" for table in DEFINITION_TABLES)


class Command(BaseCommand):
    help = (
        "Archive then delete type-definition rows whose workspace_id no longer "
        "resolves (G1.4/#1403, reversible via *_orphan_archive)."
    )

    def add_arguments(self, parser) -> None:
        # Accepted and ignored so the deploy stack can call this command and
        # ``migrate`` with the same flags (same convention as
        # cleanup_workflow_orphans).
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
            help="Count only; never archive or delete.",
        )
        parser.add_argument(
            "--confirm-count",
            type=int,
            default=None,
            dest="confirm_count",
            help=(
                "Required for a real run: the exact total the dry run reported. "
                "A different current count aborts without changing anything."
            ),
        )

    def handle(self, *args, **options) -> None:
        if connection.vendor != "postgresql":
            raise CommandError(
                "cleanup_workspace_orphans requires PostgreSQL (row-level security)."
            )

        if not _current_role_can_bypass_rls():
            raise CommandError(
                "cleanup_workspace_orphans must run under a role with BYPASSRLS "
                "or superuser rights (the migrate service). Under an RLS-bound "
                "role it would count zero rows and report a clean database."
            )

        with transaction.atomic():
            counts = count_workspace_orphans(connection, DEFINITION_TABLES)
            total = sum(counts.values())

            if total and _workspace_count() == 0:
                raise CommandError(
                    "Refusing to run: no pl_workspace row is visible but "
                    f"{total} definition orphan(s) were counted. That is an RLS "
                    "visibility problem, not a database full of orphans."
                )

            self.stdout.write(_format(counts))

            if options["dry_run"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"--dry-run: {total} row(s) would be archived and "
                        "deleted; nothing was changed."
                    )
                )
                return

            if total == 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        "No definition orphans found — nothing to do."
                    )
                )
                return

            confirm_count = options["confirm_count"]
            if confirm_count is None:
                raise CommandError(
                    "Refusing to delete without --confirm-count=<n>. Run "
                    "--dry-run first and pass its total."
                )
            if confirm_count != total:
                raise CommandError(
                    f"Refusing to delete: --confirm-count={confirm_count} but the "
                    f"current total is {total}. Re-run --dry-run."
                )

            archived = archive_and_delete_workspace_orphans(
                connection, DEFINITION_TABLES
            )

        archived_total = sum(archived.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Archived and deleted {archived_total} definition orphan(s) "
                f"({_format(archived)}). Recoverable from the *_orphan_archive "
                "tables until their retention PR runs."
            )
        )
