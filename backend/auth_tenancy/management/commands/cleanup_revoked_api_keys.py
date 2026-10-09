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

Cross-tenant RLS contract (issue #1184, residual R-3)
-----------------------------------------------------
``at_api_key`` carries the staged tenant-isolation policy
(``auth_tenancy/0017_preauth_staged_rls.py``, hardened against a session
``SET`` by ``auth_tenancy/0022_rls_hard_enforcement_policy.py``): with the
placeholder GUC ``app.rls_preauth_enforced`` armed, a row is visible only when
it matches ``app.current_tenant``. This command is CLI maintenance — there is no
request, hence no tenant context to arm — and it reads the whole table anyway.
Before the guard below, that combination was the single *dangerous* R-3 path
documented in ``docs/audit/2026-10/1136-r3-unscoped-inventory.md``: the
unscoped queryset collapsed to zero rows under an armed policy, so
``stale.count()`` reported "0 ... would be deleted" and ``--apply`` printed
"Deleted 0 ...". Silent no-op, reported as success.

The read therefore runs inside ``transaction.atomic()`` with
``SET LOCAL row_security = off``, exactly like the canon
``inventory_api_keys.collect_inventory`` uses for its cross-tenant read:

* on an operator/owner connection (owner or superuser) no policy is ever
  applied, so the guard is a no-op and the command behaves exactly as before;
* on the least-privilege app role (``reqogniloom_app``) the setting is accepted
  but the *read* is not: with ``row_security = off`` Postgres raises
  "query would be affected by row-level security policy" instead of quietly
  filtering rows away, so the run fails loudly with the data untouched rather
  than reporting a false success.

The atomic wrapper is load-bearing twice: ``SET LOCAL`` is scoped to a
transaction, and the count and the delete have to land together or not at all.
"""
from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from auth_tenancy.models import ApiKey

_DEFAULT_OLDER_THAN_DAYS = 30


class Command(BaseCommand):
    """Delete revoked API keys older than a threshold (dry-run by default)."""

    help = (
        "Delete ApiKey rows revoked more than N days ago (#606). Dry-run "
        "unless --apply is given; always reports the count either way. Reads "
        "cross-tenant under SET LOCAL row_security = off (#1184/R-3), so an "
        "RLS-blinded least-privilege connection fails loudly instead of "
        "reporting 'Deleted 0'."
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
        apply_changes = bool(options["apply"])

        # unscoped: this is cross-tenant maintenance, not a request-scoped op.
        stale = ApiKey.unscoped.filter(
            revoked_at__isnull=False, revoked_at__lt=cutoff
        )

        deleted = 0
        with transaction.atomic():
            with connection.cursor() as cursor:
                # R-3 (#1184): ``at_api_key`` has a staged tenant-isolation
                # policy and no tenant context is armed here, so without the
                # guard this read would be silently emptied. With it, the
                # read either sees every tenant's rows (owner/superuser CLI
                # connection) or raises "query would be affected by
                # row-level security policy" (least-privilege app role).
                cursor.execute("SET LOCAL row_security = off")
            # Counted in both modes: the dry run must report the number the
            # guarded read really sees, never a number an earlier, unguarded
            # run would have produced.
            count = stale.count()
            if apply_changes:
                deleted, _ = stale.delete()

        if not apply_changes:
            self.stdout.write(
                f"Dry run: {count} revoked API key(s) older than "
                f"{older_than_days} day(s) would be deleted. Re-run with "
                "--apply to delete them."
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} revoked API key(s) older than "
                f"{older_than_days} day(s)."
            )
        )
