"""
ARCH-L1-011 AuthAndTenancy — cleanup command for stale revoked API keys.

#606: revoked ``ApiKey`` rows are never deleted, only marked
``revoked_at``. In CI/CD environments where every agent/QA run provisions
its own key for isolation, revoked rows accumulate indefinitely (39
observed in the reported case) while the separate
``MAX_ACTIVE_API_KEYS_PER_USER`` cap only counts *active* keys — so this
accumulation is a DB-hygiene concern, not the actual cause of "max active
keys reached" errors, but cleaning it up is still worthwhile maintenance.

Usage:
    python manage.py cleanup_revoked_api_keys              # dry run, 30-day threshold
    python manage.py cleanup_revoked_api_keys --apply
    python manage.py cleanup_revoked_api_keys --apply --older-than-days=7
"""
from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from auth_tenancy.models import ApiKey

_DEFAULT_OLDER_THAN_DAYS = 30


class Command(BaseCommand):
    """Delete revoked API keys older than a threshold (dry-run by default)."""

    help = (
        "Delete ApiKey rows revoked more than N days ago (#606). Dry-run "
        "unless --apply is given; always reports the count either way."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=_DEFAULT_OLDER_THAN_DAYS,
            help=f"Age threshold in days (default: {_DEFAULT_OLDER_THAN_DAYS}).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete the matched rows (default: dry-run, report only).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        older_than_days = options["older_than_days"]
        cutoff = timezone.now() - timedelta(days=older_than_days)

        # unscoped: this is cross-tenant maintenance, not a request-scoped op.
        stale = ApiKey.unscoped.filter(
            revoked_at__isnull=False, revoked_at__lt=cutoff
        )
        count = stale.count()

        if not options["apply"]:
            self.stdout.write(
                f"Dry run: {count} revoked API key(s) older than "
                f"{older_than_days} day(s) would be deleted. Re-run with "
                "--apply to delete them."
            )
            return

        deleted, _ = stale.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} revoked API key(s) older than "
                f"{older_than_days} day(s)."
            )
        )
