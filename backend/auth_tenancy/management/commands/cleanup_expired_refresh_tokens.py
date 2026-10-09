"""
ARCH-L1-011 AuthAndTenancy — cleanup command for spent refresh-token rows.

SA-32 (SYSTEMAUDIT-2026-08-27 §4.6 F7) introduced ``at_refresh_token``: one row
per issued refresh JWT, so ``/auth/refresh/`` can detect a token being presented
twice. Rows are never deleted inline — deleting a row would make a replay
indistinguishable from an ordinary expiry, which is precisely the signal the
table exists to preserve.

Once a row's ``expires_at`` has passed the token is rejected by ``decode_jwt``
before rotation state is ever consulted, so the row carries no further security
value and can be dropped. Without this command the table grows by one row per
login and per refresh, forever.

A grace period beyond ``expires_at`` is applied so a row survives slightly
longer than the token it describes — cheap insurance against clock skew between
application servers and the database.

Issue #1182: the cross-tenant read/delete runs through the owner-privileged
``SECURITY DEFINER`` function ``public.auth_purge_expired_refresh_tokens`` (see
``auth_tenancy/migrations/0021_refresh_token_functions_and_rls.py``), not via
``RefreshToken.unscoped``. This is a tenant-context-free maintenance job; once
the staged policy on ``at_refresh_token`` is enforced, an unscoped ORM
read/delete would silently match zero rows and the command would report success
while deleting nothing. The function keeps the predicate identical and always
returns the affected row count.

Usage:
    python manage.py cleanup_expired_refresh_tokens              # dry run
    python manage.py cleanup_expired_refresh_tokens --apply
    python manage.py cleanup_expired_refresh_tokens --apply --grace-days=0
"""
from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from auth_tenancy.services.refresh_token_store import purge_expired_refresh_tokens

_DEFAULT_GRACE_DAYS = 1


class Command(BaseCommand):
    """Delete refresh-token rows whose token has expired (dry-run by default)."""

    help = (
        "Delete at_refresh_token rows past their expiry (SA-32). Dry-run "
        "unless --apply is given; always reports the count either way."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--grace-days",
            type=int,
            default=_DEFAULT_GRACE_DAYS,
            help=(
                "Extra days to keep a row after its token expired "
                f"(default: {_DEFAULT_GRACE_DAYS})."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete the matched rows (default: dry-run).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        grace_days = options["grace_days"]
        cutoff = timezone.now() - timedelta(days=grace_days)
        apply = options["apply"]

        # SECURITY DEFINER maintenance (issue #1182): cross-tenant and without a
        # tenant context, so a plain unscoped read/delete would be silently
        # reduced to zero rows once the staged policy on at_refresh_token is
        # enforced. The owner-privileged function counts (dry run) or deletes
        # (--apply) the same predicate and reports the affected row count, so
        # the command can never report success while doing nothing.
        affected = purge_expired_refresh_tokens(cutoff, apply=apply)

        if not apply:
            self.stdout.write(
                f"[dry-run] {affected} expired refresh-token row(s) older than "
                f"{cutoff.isoformat()} would be deleted. Re-run with --apply."
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {affected} expired refresh-token row(s) older than "
                f"{cutoff.isoformat()}."
            )
        )
