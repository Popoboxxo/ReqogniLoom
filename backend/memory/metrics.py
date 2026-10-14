"""Consolidation counters for the AI-memory learning loop (issue #1300).

Before this module the only way to tell whether the memory pipeline was being
fed was to grep worker logs: the learning loop was fed exclusively by interview
events and produced no observable signal. These counters answer "is the loop
running, and from which trigger?" without a log grep.

The counter is **per trigger source** — the thing that asked for a
consolidation:

* a domain event type, e.g. ``InterviewChatTurn`` /
  ``InteractionCompleted`` (the values of
  ``application.models.DomainEventOutbox.EventType``); or
* a non-event source such as the MCP ``memory.remember_interaction`` tool, whose
  string is registered by that stream through
  :func:`increment_consolidation`.

The tally lives in the Django cache (Redis in production), mirroring
:mod:`memory.ratelimit`'s fixed-window counter and its fail-open policy: a cache
outage is logged and the increment is a no-op, because a counter is an
observability aid and must never break the pipeline it observes. It is a
monotonic total (no window), so ``invalidate_health_cache``-style resets do not
touch it and it survives process restarts wherever the cache does.

The set of sources seen is tracked separately (also in the cache) so the
``system/memory/consolidations`` endpoint can enumerate them portably — a cache
backend cannot list keys, so the registry is the explicit index.

The metric is intentionally named ``memory_consolidations_total`` (Prometheus
naming) even though it is exposed as JSON here: a future metrics exporter can
publish the same name without a rename. The JSON surface today is the
System-Admin ``GET /api/v1/system/memory/workspaces/`` overview
(``memory_consolidations_total`` + ``consolidation_total``), which any view that
already holds a ``consolidation_counts()``-shaped payload can serve unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Cache-key prefix for one source's monotonic counter.
COUNTER_KEY_PREFIX = "mem:consolidations:total:"

#: Cache key holding the list of sources seen so far (the portable index the
#: counter names cannot be recovered from on a key-based backend).
SOURCE_REGISTRY_KEY = "mem:consolidations:sources"

#: Label used when a caller passes no source (defensive; should not happen).
UNKNOWN_SOURCE = "unknown"


def _counter_key(source: str) -> str:
    return f"{COUNTER_KEY_PREFIX}{source}"


def _register_source(source: str) -> None:
    """Add *source* to the registry so :func:`consolidation_counts` can list it."""
    try:
        sources: List[str] = cache.get(SOURCE_REGISTRY_KEY) or []
        if source not in sources:
            cache.set(SOURCE_REGISTRY_KEY, [*sources, source], timeout=None)
    except Exception:  # noqa: BLE001 - registry is best-effort, see module docstring
        logger.debug("memory.metrics: could not register source %r", source, exc_info=True)


def increment_consolidation(source: Any, *, amount: int = 1) -> int:
    """Increment the consolidation counter for *source* and return its new value.

    Returns ``0`` when the cache is unavailable — never raises, see the module
    docstring. Mirrors :func:`memory.ratelimit.check_write_rate_limit`'s
    ``add``-then-``incr`` sequence (the first increment already reads 1) and its
    ``ValueError`` recovery for a key that expired between the two calls.
    """
    key_source = str(source or "").strip() or UNKNOWN_SOURCE
    try:
        key = _counter_key(key_source)
        cache.add(key, 0, timeout=None)
        count = cache.incr(key, amount)
    except ValueError:
        # The key vanished between add() and incr() (e.g. an eviction); seed it.
        try:
            cache.set(_counter_key(key_source), amount, timeout=None)
        except Exception:  # noqa: BLE001 - best-effort, mirrors the outer except
            return 0
        count = amount
    except Exception:  # noqa: BLE001 - a cache outage must not break the pipeline
        logger.warning(
            "memory.metrics: consolidation counter unavailable for source %r",
            key_source,
            exc_info=True,
        )
        return 0
    _register_source(key_source)
    return count


def consolidation_counts() -> Dict[str, int]:
    """Return ``{source: total}`` for every source seen; ``{}`` if none/unavailable."""
    try:
        sources = cache.get(SOURCE_REGISTRY_KEY) or []
    except Exception:  # noqa: BLE001 - a cache outage reads as "no sources"
        return {}
    counts: Dict[str, int] = {}
    for source in sources:
        try:
            counts[source] = int(cache.get(_counter_key(source)) or 0)
        except Exception:  # noqa: BLE001 - one unreadable key must not hide the rest
            counts[source] = 0
    return counts


def total_consolidations() -> int:
    """Return the sum across all sources."""
    return sum(consolidation_counts().values())


def reset_consolidation_counters() -> None:
    """Clear every counter and the source registry (test/admin helper)."""
    try:
        sources = cache.get(SOURCE_REGISTRY_KEY) or []
        for source in sources:
            cache.delete(_counter_key(source))
        cache.delete(SOURCE_REGISTRY_KEY)
    except Exception:  # noqa: BLE001 - best-effort, mirrors the read path
        logger.debug("memory.metrics: could not reset counters", exc_info=True)


__all__ = [
    "COUNTER_KEY_PREFIX",
    "SOURCE_REGISTRY_KEY",
    "UNKNOWN_SOURCE",
    "increment_consolidation",
    "consolidation_counts",
    "total_consolidations",
    "reset_consolidation_counters",
]
