"""Celery tasks for the application layer.

Currently hosts the outbox-consumer beat task that drains the domain-event
outbox (REQ-032, DEEP_SYSTEM_ANALYSIS.md BE-1). ``poll_and_dispatch`` already
claims each event with a ``SELECT FOR UPDATE (skip_locked)`` row-lock, so the
task is safe to run concurrently and on a fixed schedule (idempotent).
"""

from __future__ import annotations

import logging

from celery import shared_task

from application.event_bus import poll_and_dispatch

logger = logging.getLogger(__name__)


@shared_task(name="application.dispatch_outbox_events")
def dispatch_outbox_events() -> int:
    """Drain the domain-event outbox by dispatching unpublished events.

    Registered as a periodic Celery-beat task (see ``CELERY_BEAT_SCHEDULE``).
    Any exception is logged and swallowed so a transient failure never crashes
    the beat/worker loop — the next scheduled run retries the outstanding rows.

    Returns:
        Number of events processed in this cycle (0 on error).
    """
    try:
        processed = poll_and_dispatch()
        if processed:
            logger.info("dispatch_outbox_events: dispatched %d event(s)", processed)
        return processed
    except Exception:  # noqa: BLE001 — beat task must never crash the loop.
        logger.exception("dispatch_outbox_events: poll cycle failed")
        return 0
