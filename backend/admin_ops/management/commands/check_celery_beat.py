"""Functional celery-beat liveness probe (ADR-010 §3, RES-05).

Exit code 0 only while the beat-scheduled heartbeat is fresh; non-zero
otherwise. Docker then marks the beat container unhealthy when beat stops
dispatching — a plain ``pgrep`` (the previous check) proves only that the
process exists, so a hung beat stayed "healthy".

The heartbeat is written by the periodic task
``admin_ops.record_celery_beat_heartbeat`` (see
:mod:`admin_ops.celery_beat_heartbeat`), which runs on its own 60s cadence
independent of any user schedule. A stale value therefore means beat is not
ticking — it does not false-red on a quiet business schedule.

This command reads the shared cache only; it performs no database access and
has no side effects.
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Fail unless the celery-beat heartbeat is fresh."""

    help = "Fail unless the celery-beat heartbeat is fresh (functional beat probe)."

    def handle(self, *args, **options):
        # Imported lazily so the command module can be collected without a
        # configured cache backend.
        from admin_ops import celery_beat_heartbeat as heartbeat

        try:
            timestamp = heartbeat.read_heartbeat_timestamp()
        except Exception as exc:  # noqa: BLE001 - an unreadable cache is a failure
            # Do not interpolate the exception: a cache/driver error can carry a
            # host/DSN. `raise ... from exc` keeps the cause for debugging while
            # manage.py prints only this message.
            raise CommandError("celery beat heartbeat unreadable") from exc

        if timestamp is None:
            raise CommandError(
                "no celery beat heartbeat recorded yet - beat has not dispatched "
                f"since deploy (expected every {heartbeat.HEARTBEAT_INTERVAL_SECONDS}s)"
            )

        age = time.time() - timestamp
        if age > heartbeat.HEARTBEAT_STALE_AFTER_SECONDS:
            raise CommandError(
                "celery beat heartbeat is stale: last dispatched "
                f"{age:.1f}s ago "
                f"(threshold {heartbeat.HEARTBEAT_STALE_AFTER_SECONDS}s)"
            )

        self.stdout.write(
            "celery beat heartbeat ok "
            f"({age:.1f}s old, interval {heartbeat.HEARTBEAT_INTERVAL_SECONDS}s)"
        )
