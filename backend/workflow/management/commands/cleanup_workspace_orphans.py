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
2. **Invisible-rows signal.** ``count(pl_workspace) = 0`` while definitions
   exist *can* mean the connection cannot see workspaces. It is also the
   legitimate state after every workspace was deleted, which is exactly the
   orphan case this command exists for (#1403 QA: 209 orphans) — so it is
   reported as a warning, not an abort. The hard protection against invisible
   rows is rail 1: a BYPASSRLS/superuser role cannot have rows hidden by RLS.
3. **``--confirm-count`` required.** The operator must pass the exact total the
   dry run reported; a differing count aborts before the first delete, so a
   concurrent workspace delete cannot silently widen the blast radius. This is
   also what keeps a suspected visibility problem from deleting anything: the
   operator has to confirm the very number the command counted.

Usage::

    python manage.py cleanup_workspace_orphans --dry-run
    python manage.py cleanup_workspace_orphans --confirm-count=232
"""

from __future__ import annotations

from typing import Any

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


def _validate_confirm_count(raw: Any) -> int | None:
    """Validate ``--confirm-count`` without touching the database.

    ``call_command`` forwards option values verbatim — the argparse
    ``type=int`` coercion only runs for a real CLI invocation — so the value
    can still be a string here. Validation happens before the first query so a
    malformed count can never be masked by a later, unrelated failure.
    """
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise CommandError(
            f"--confirm-count must be an integer, got {raw!r}."
        ) from None
    if value < 0:
        raise CommandError(f"--confirm-count must be >= 0, got {value}.")
    return value


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
        # 1. Pure argument validation — no database access, so a malformed
        #    invocation fails deterministically instead of being masked by a
        #    later, unrelated database error.
        confirm_count = _validate_confirm_count(options["confirm_count"])
        dry_run: bool = options["dry_run"]

        if connection.vendor != "postgresql":
            raise CommandError(
                "cleanup_workspace_orphans requires PostgreSQL (row-level security)."
            )

        # 2. Capability check before the first row is counted (fail-closed).
        if not _current_role_can_bypass_rls():
            raise CommandError(
                "cleanup_workspace_orphans must run under a role with BYPASSRLS "
                "or superuser rights (the migrate service). Under an RLS-bound "
                "role it would count zero rows and report a clean database."
            )

        # 3. Count, then compare the operator's confirmation, then mutate.
        with transaction.atomic():
            counts = count_workspace_orphans(connection, DEFINITION_TABLES)
            total = sum(counts.values())

            if total and _workspace_count() == 0:
                # Ambiguous but not fatal: an empty pl_workspace is either the
                # legitimate post-delete orphan state (#1403) or an invisible
                # row set. A BYPASSRLS/superuser role (checked above) cannot
                # hide rows, so this cannot be treated as a hard error without
                # blocking the very cleanup the command exists for. The exact
                # --confirm-count below stays the fail-closed safeguard.
                self.stderr.write(
                    self.style.WARNING(
                        f"WARNING: pl_workspace is empty while {total} definition "
                        "orphan(s) were counted. If that is not the expected "
                        "state, verify the connection's RLS visibility; nothing "
                        "is deleted without a matching --confirm-count."
                    )
                )

            self.stdout.write(_format(counts))

            if dry_run:
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
