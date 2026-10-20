"""Counters for domain events published outside a transaction (issue #1438).

``DomainEventBus.publish()`` writes its outbox row inline, in the caller's
transaction (SA-02) — that is the whole point of the Transactional Outbox
pattern: the event and the mutation that produced it share one fate. The
binding only holds when the caller actually *has* a transaction open. A
service method that publishes without one (a missing ``@atomic_transaction``)
autocommits the outbox row: the event survives, but it is no longer bound to
anything, and a later rollback of the mutation cannot take it with it.

Issue #1438 was exactly that: ``TraceLinkService.create_trace_link`` was the
one event-producing service method without a transaction wrapper, so the
``seed_toothbrush`` run logged 1879 "publish() called outside a transaction"
warnings — one per created link.

Detecting the condition was never the problem; *observing* it was. The bus
warned once per occurrence, so a bulk producer produced thousands of warning
lines and the real signal was buried in the noise. This module provides the
counter that makes the condition measurable instead of merely noisy:

* :func:`increment_unbound_publish` — count one unbound publish (overall and
  per event type) and return the new count.
* :func:`unbound_publish_count` — the count within the current decay window.
* :func:`unbound_publish_counts_by_type` — the per-event-type breakdown.
* :func:`reset_unbound_publish_counters` — clear the counters (test/admin).

The tally lives in the Django cache (Redis in production), mirroring
:mod:`memory.metrics`' counter and its fail-open policy: a cache outage is
logged and the increment is a no-op, because a counter is an observability aid
and must never break the pipeline it observes.

The counter lives in a DECAYING WINDOW, not forever: the key is created with
the TTL of ``settings.OUTBOX_UNBOUND_COUNTER_TTL`` (default 24 h) when the
FIRST unbound publish of the window arrives and expires again TTL seconds
later. The window is FIXED, not sliding — the TTL is set once, at the start of
the window, and is not refreshed by later increments. Rationale: a monotonic
counter can never clear, so a single pre-fix publish would keep
``/health/ready`` at ``status: "warning"`` forever. That is alert fatigue, it
cannot be distinguished from "broken right now", and a dev/staging Redis that
saw one pre-fix seed would stay permanently unhealthy. With a window a
resolved defect clears the readiness signal BY ITSELF — no manual reset, no
stale alert. ``OUTBOX_UNBOUND_COUNTER_TTL = 0`` disables the decay and makes
the counter monotonic forever.

BACKEND NUANCE — the fixed window relies on ``cache.incr`` NOT touching the
TTL. Django's ``BaseCache.incr`` re-``set``s the value with the *backend's*
default timeout (300 s on LocMemCache), so on that backend the TTL of an
already-existing key is reset to the backend default. RedisCache overrides
``incr`` with a native ``INCR``, which preserves the TTL — and Redis is the
production backend. The window length is therefore exactly
``OUTBOX_UNBOUND_COUNTER_TTL`` in production; on LocMemCache (tests only) an
existing key decays with the backend default instead. Both decay, and both
clear the signal once the publishes stop.

A cache backend cannot list keys, so the per-type breakdown needs a registry
of the event types seen so far — mirroring ``memory.metrics``'s
``SOURCE_REGISTRY_KEY``.

Beside the shared counters this module keeps a small amount of
**process-local** state: the "have I already warned about this?" latch that
throttles the bus' warning flood, plus the per-run tally the process-exit
summary reports. Both are deliberately *not* derived from the cache counter:
the cache is shared between processes and outlives a restart, so "is this the
first unbound publish in THIS process?" cannot be answered from it.

The metric is intentionally named ``outbox_unbound_publish_count`` and
exposed as JSON and as an advisory entry of the readiness payload: a future
metrics exporter can publish the same name without a rename. It is a *count*,
not a *total* — the window bounds it.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Cache key of the unbound-publish count of the current decay window.
TOTAL_KEY = "outbox:unbound_publish:count"

#: Cache-key prefix for one event type's counter.
TYPE_KEY_PREFIX = "outbox:unbound_publish:type:"

#: Cache key holding the list of event types seen so far (the portable index
#: the per-type counters cannot be recovered from on a key-based backend).
TYPE_REGISTRY_KEY = "outbox:unbound_publish:types"

#: Label used when a caller passes no event type (defensive; should not happen).
UNKNOWN_EVENT_TYPE = "unknown"

#: Default decay window of the counters, in seconds (24 h). Overridden by
#: ``settings.OUTBOX_UNBOUND_COUNTER_TTL``; ``0`` means "no decay".
DEFAULT_UNBOUND_COUNTER_TTL_SECONDS = 24 * 60 * 60

#: Guards the process-local state below.
_process_lock = threading.Lock()

#: Whether this process already reported the first unbound publish. Process
#: local on purpose — see the module docstring.
_first_report_done = False

#: Unbound publishes seen in THIS process, by event type.
_run_counts: dict[str, int] = {}

#: Unbound publishes seen in THIS process, in total.
_run_total = 0


def _type_key(event_type: str) -> str:
    return f"{TYPE_KEY_PREFIX}{event_type}"


def counter_window_seconds() -> int:
    """Return the effective decay window of the counters, in seconds.

    ``0`` means "no decay" — the counter is then monotonic forever. Read at
    call time (not import time) so ``override_settings`` and an operational
    env override both take effect without a code change.
    """
    try:
        return max(
            0,
            int(
                getattr(
                    settings,
                    "OUTBOX_UNBOUND_COUNTER_TTL",
                    DEFAULT_UNBOUND_COUNTER_TTL_SECONDS,
                )
            ),
        )
    except Exception:  # noqa: BLE001 - a config problem must not break a publish
        logger.debug(
            "application.event_bus_metrics: unreadable OUTBOX_UNBOUND_COUNTER_TTL",
            exc_info=True,
        )
        return DEFAULT_UNBOUND_COUNTER_TTL_SECONDS


def _counter_timeout() -> int | None:
    """Return the cache timeout to use for a counter key.

    ``None`` means "never expires" (the cache's own no-timeout marker) and is
    used when the decay is disabled (``OUTBOX_UNBOUND_COUNTER_TTL = 0``).
    """
    window = counter_window_seconds()
    return window if window > 0 else None


def _bump(key: str, label: str) -> int | None:
    """Increment *key* and return its new value; ``None`` when the cache is down.

    Mirrors ``memory.metrics``' ``add``-then-``incr`` sequence (the first
    increment already reads 1) and its ``ValueError`` recovery for a key that
    expired between the two calls.

    The ``add`` carries the decay window: it creates the key with that TTL if
    the key is absent (which is exactly when the fixed window starts) and
    leaves an existing key — and its TTL — untouched.
    """
    timeout = _counter_timeout()
    try:
        cache.add(key, 0, timeout=timeout)
        return int(cache.incr(key))
    except ValueError:
        # The key vanished between add() and incr() (e.g. an eviction); seed it.
        try:
            cache.set(key, 1, timeout=timeout)
        except Exception:  # noqa: BLE001 - best-effort, mirrors the outer except
            logger.warning(
                "application.event_bus_metrics: %s counter unavailable",
                label,
                exc_info=True,
            )
            return None
        return 1
    except Exception:  # noqa: BLE001 - a cache outage must not break the pipeline
        logger.warning(
            "application.event_bus_metrics: %s counter unavailable",
            label,
            exc_info=True,
        )
        return None


def _register_type(event_type: str) -> None:
    """Add *event_type* to the registry so the breakdown can list it."""
    try:
        types: list[str] = cache.get(TYPE_REGISTRY_KEY) or []
        if event_type not in types:
            cache.set(
                TYPE_REGISTRY_KEY,
                [*types, event_type],
                timeout=_counter_timeout(),
            )
    except Exception:  # noqa: BLE001 - registry is best-effort, see module docstring
        logger.debug(
            "application.event_bus_metrics: could not register event type %r",
            event_type,
            exc_info=True,
        )


def _count_run(event_type: str) -> None:
    """Add one unbound publish to this process' own tally."""
    global _run_total
    with _process_lock:
        _run_total += 1
        _run_counts[event_type] = _run_counts.get(event_type, 0) + 1


def increment_unbound_publish(event_type: str) -> int:
    """Count one unbound publish and return the new count.

    Increments the overall counter *and* the per-event-type counter. Returns
    ``0`` when the cache is unavailable — never raises, see the module
    docstring.
    """
    key_type = str(event_type or "").strip() or UNKNOWN_EVENT_TYPE
    count = _bump(TOTAL_KEY, "unbound-publish")
    if count is None:
        return 0
    if _bump(_type_key(key_type), "unbound-publish per-type") is None:
        # The overall counter is the authoritative number; a broken per-type
        # counter only costs the breakdown, never the count.
        logger.debug(
            "application.event_bus_metrics: per-type counter unavailable for %r",
            key_type,
        )
    _register_type(key_type)
    _count_run(key_type)
    return count


def unbound_publish_count() -> int:
    """Return the number of unbound publishes in the current decay window.

    ``0`` once the window expired — a resolved defect therefore clears the
    readiness signal by itself (see the module docstring).
    """
    try:
        return int(cache.get(TOTAL_KEY) or 0)
    except Exception:  # noqa: BLE001 - a cache outage reads as "no publishes"
        logger.debug(
            "application.event_bus_metrics: could not read the count counter",
            exc_info=True,
        )
        return 0


def unbound_publish_counts_by_type() -> dict[str, int]:
    """Return ``{event_type: count}`` for every event type seen; ``{}`` if none."""
    try:
        types: list[str] = cache.get(TYPE_REGISTRY_KEY) or []
    except Exception:  # noqa: BLE001 - a cache outage reads as "no types"
        return {}
    counts: dict[str, int] = {}
    for event_type in types:
        try:
            counts[event_type] = int(cache.get(_type_key(event_type)) or 0)
        except Exception:  # noqa: BLE001 - one unreadable key must not hide the rest
            counts[event_type] = 0
    return counts


def reset_unbound_publish_counters() -> None:
    """Clear the count, the per-type counters and the type registry."""
    try:
        types: list[str] = cache.get(TYPE_REGISTRY_KEY) or []
        for event_type in types:
            cache.delete(_type_key(event_type))
        cache.delete(TYPE_REGISTRY_KEY)
        cache.delete(TOTAL_KEY)
    except Exception:  # noqa: BLE001 - best-effort, mirrors the read path
        logger.debug(
            "application.event_bus_metrics: could not reset counters",
            exc_info=True,
        )


def mark_unbound_publish_reported() -> bool:
    """Return ``True`` exactly once per process, until the state is reset.

    The latch behind the warning throttle: the first unbound publish of a
    process is reported in full, every later one is only counted. Deliberately
    process-local — the shared cache counter must not decide whether THIS
    process has already spoken.
    """
    global _first_report_done
    with _process_lock:
        if _first_report_done:
            return False
        _first_report_done = True
        return True


def unbound_publish_run_count() -> int:
    """Return how many unbound publishes THIS process has seen."""
    with _process_lock:
        return _run_total


def unbound_publish_run_counts_by_type() -> dict[str, int]:
    """Return this process' per-event-type tally of unbound publishes."""
    with _process_lock:
        return dict(_run_counts)


def reset_unbound_publish_state(*, clear_counters: bool = False) -> None:
    """Clear the process-local throttle state (test helper).

    Resets the "already reported" latch and this process' own tally, so a
    test can assert the first-warning behaviour deterministically. The shared
    cache counters are left alone unless *clear_counters* is set.
    """
    global _first_report_done, _run_total
    with _process_lock:
        _first_report_done = False
        _run_total = 0
        _run_counts.clear()
    if clear_counters:
        reset_unbound_publish_counters()


__all__ = [
    "DEFAULT_UNBOUND_COUNTER_TTL_SECONDS",
    "TOTAL_KEY",
    "TYPE_KEY_PREFIX",
    "TYPE_REGISTRY_KEY",
    "UNKNOWN_EVENT_TYPE",
    "counter_window_seconds",
    "increment_unbound_publish",
    "mark_unbound_publish_reported",
    "reset_unbound_publish_counters",
    "reset_unbound_publish_state",
    "unbound_publish_count",
    "unbound_publish_counts_by_type",
    "unbound_publish_run_count",
    "unbound_publish_run_counts_by_type",
]
