"""Celery-beat liveness heartbeat.

Celery Beat schedules the periodic task
``admin_ops.record_celery_beat_heartbeat`` (see ``CELERY_BEAT_SCHEDULE`` in
``reqogniloom.settings``). That task calls :func:`record_heartbeat`, which
writes the current epoch timestamp into Django's default cache. The
system-health dashboard reads it back via
:func:`admin_ops.health_rest._check_celery_beat` and compares its age against
:data:`HEARTBEAT_STALE_AFTER_SECONDS`.

Why this proves liveness: the timestamp is only written when a scheduled run
actually reaches a worker, i.e. the full ``beat -> broker -> worker`` chain is
alive. That is exactly what the old ``PeriodicTask`` row-count could not show.
Combined with the existing ``celery_worker`` check an operator can distinguish
a dead *worker* (worker check down, heartbeat still fresh until it goes stale)
from a dead *beat* (worker check up, heartbeat stale).

Non-expiring by design (issue #822 acceptance): the cached timestamp is written
with ``timeout=None`` (Django caches such values forever). A finite TTL would
let a beat that stopped for longer than the TTL lose its cache key, so the
health check would read no value and report ``unknown`` with the "beat has not
started since deploy" wording — factually wrong, because a heartbeat *was*
recorded. The #822 acceptance criterion reserves ``unknown`` for the case where
no heartbeat has ever been recorded (or the cache is unreadable). A stopped beat
must therefore keep reading as ``down`` (stale) indefinitely, which is only
possible if the remembered value never expires.

The mechanism is deliberately cache-only (no DB access), bounded and
side-effect free from the web worker's perspective, which only reads.
"""
from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache

#: Cache key holding the last heartbeat epoch timestamp (seconds).
HEARTBEAT_CACHE_KEY = "reqogniloom:celery_beat:heartbeat"

#: How often the heartbeat task is scheduled to run, in seconds. Sourced from
#: the shared setting so the schedule and the staleness window cannot drift.
HEARTBEAT_INTERVAL_SECONDS: int = int(
    getattr(settings, "CELERY_BEAT_HEARTBEAT_INTERVAL_SECONDS", 60)
)

#: A heartbeat older than this is treated as stale ("down"). Deliberately a
#: small multiple (3x) of the interval: it tolerates a couple of consecutive
#: missed runs from transient hiccups without hiding a genuinely stopped beat
#: for long.
HEARTBEAT_STALE_AFTER_SECONDS: int = HEARTBEAT_INTERVAL_SECONDS * 3


def record_heartbeat() -> None:
    """Write the current epoch timestamp to Django's default cache.

    Called by the beat-scheduled task on every run. The value is stored with
    ``timeout=None`` (never expires) so that a stopped beat leaves a
    readable-but-stale value — reported as ``down`` forever — rather than
    letting the key expire into a misleading ``unknown`` ("beat has not started
    since deploy"). See the module docstring for the #822 acceptance rationale.
    """
    cache.set(HEARTBEAT_CACHE_KEY, time.time(), timeout=None)


def read_heartbeat_timestamp() -> float | None:
    """Return the last recorded heartbeat timestamp, or ``None`` if absent.

    May raise if the cache backend is unreachable; callers that must never
    raise (the health check) are responsible for guarding the call.
    """
    value = cache.get(HEARTBEAT_CACHE_KEY)
    if value is None:
        return None
    return float(value)


__all__ = [
    "HEARTBEAT_CACHE_KEY",
    "HEARTBEAT_INTERVAL_SECONDS",
    "HEARTBEAT_STALE_AFTER_SECONDS",
    "read_heartbeat_timestamp",
    "record_heartbeat",
]
