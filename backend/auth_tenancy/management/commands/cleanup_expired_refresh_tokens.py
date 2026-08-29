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

from auth_tenancy.models import RefreshToken

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

        # unscoped: cross-tenant maintenance, not a request-scoped operation.
        stale = RefreshToken.unscoped.filter(expires_at__lt=cutoff)
        count = stale.count()

        if not options["apply"]:
            self.stdout.write(
                f"[dry-run] {count} expired refresh-token row(s) older than "
                f"{cutoff.isoformat()} would be deleted. Re-run with --apply."
            )
            return

        deleted, _ = stale.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} expired refresh-token row(s) older than "
                f"{cutoff.isoformat()}."
            )
        )
