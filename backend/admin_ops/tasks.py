"""Celery tasks for the admin_ops app.

Currently hosts the Celery-beat heartbeat task that feeds the ``celery_beat``
row of the system-health dashboard (issue #822,
``admin_ops.health_rest._check_celery_beat``).
"""
from __future__ import annotations

import logging

from celery import shared_task

from admin_ops.celery_beat_heartbeat import record_heartbeat

logger = logging.getLogger(__name__)


@shared_task(name="admin_ops.record_celery_beat_heartbeat")
def record_celery_beat_heartbeat() -> None:
    """Record a beat heartbeat on every scheduled run.

    Registered as a periodic Celery-beat task (see ``CELERY_BEAT_SCHEDULE``).
    Any exception is logged and swallowed so a cache outage never crashes the
    beat loop — the next scheduled run simply retries.
    """
    try:
        record_heartbeat()
    except Exception:  # beat task must never crash the loop.
        logger.exception("record_celery_beat_heartbeat: failed to record heartbeat")
