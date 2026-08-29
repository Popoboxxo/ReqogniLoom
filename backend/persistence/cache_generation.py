"""Cross-worker cache generation counters (SA-29, Systemaudit 2026-08-27 §4.1 #8).

Problem
-------
Several modules keep module-level dicts as configuration caches
(``presets.gate._tier_cache`` / ``_profile_cache``,
``auth_tenancy.services.permission_cache``, ``workflow.transition_validator``).
Those caches are *process*-local. ``application.cache_invalidation`` already
clears them, but only inside the worker that handled the write — every other
Gunicorn/Celery process keeps serving the pre-write value until it restarts.
For preset/tier data that means a workspace downgraded to ``minimal`` on worker
A keeps offering Extended-only features on workers B..N, indefinitely.

Approach
--------
A monotonically increasing integer per (namespace, scope) lives in the shared
Redis cache (``django.core.cache``, REQ-033 — the one thing every worker
genuinely agrees on). Writers call :func:`bump_cache_generation`; readers tag
each cached value with the generation it was computed under and discard the
entry when the shared counter has moved on.

This is deliberately *not* "store the value itself in Redis": the cached objects
(``PresetConfig``, ``TerminologyMapping``) stay in-process, so the hot read path
keeps its sub-millisecond latency budget (REQ-L2-PC-013) and the shared store
carries a single small integer instead of a pickled config per workspace.

Read amplification is bounded by a short process-local memo
(:data:`GENERATION_READ_TTL_SECONDS`): a hot loop performs at most one cache
round trip per scope per interval, which caps worst-case staleness at
``TTL + replication`` instead of the current *unbounded* staleness.

Failure behaviour
-----------------
Every function is fail-safe. A cache backend that is down or missing must never
break the request that consulted it, so reads fall back to the last known
generation (or 0) and bumps are logged and swallowed. Degrading to today's
process-local behaviour is acceptable; raising is not.

If the counter key is evicted or expires, it restarts at 0. Readers holding a
higher generation then see a mismatch, discard their entry and recompute — a
spurious cache miss, never a stale read.

req_id : REQ-033, REQ-038, REQ-L2-PC-013
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Shared-cache key namespace. Kept distinct from
# ``application.cache_invalidation._KEY_PREFIX``-derived value keys so a
# ``delete_pattern`` sweep over cached *values* never wipes the counters that
# tell readers those values are gone.
_KEY_PREFIX = "reqogniloom:cachegen"

# How long a process may reuse a generation it has already read. Trades a
# bounded staleness window for a bounded number of cache round trips on hot
# read paths. Module-level so tests can drive it to 0.
GENERATION_READ_TTL_SECONDS = 1.0

# Counters are long-lived but not immortal: an unbounded set of never-expiring
# keys would accumulate one entry per deleted workspace forever. Expiry is safe
# (see module docstring — it costs a recompute, not a stale read), and the
# window is far longer than any process lifetime.
_GENERATION_KEY_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

# (namespace, scope_id) -> (generation, monotonic timestamp of the read)
_read_memo: Dict[Tuple[str, str], Tuple[int, float]] = {}
_read_memo_lock = threading.Lock()


def _generation_key(namespace: str, scope_id: str) -> str:
    """Return the shared-cache key holding the counter for a scope."""
    return f"{_KEY_PREFIX}:{namespace}:{scope_id}"


def cache_generation(namespace: str, scope_id: str) -> int:
    """Return the current shared generation for ``(namespace, scope_id)``.

    Args:
        namespace: Logical cache family, e.g. ``"preset"``.
        scope_id: Scope the cache is keyed by, typically a workspace UUID string.

    Returns:
        The current generation, or 0 when no bump has been recorded yet.
        Never raises — a cache failure yields the last value this process saw
        (or 0), which degrades to the pre-SA-29 process-local behaviour.
    """
    memo_key = (namespace, scope_id)
    now = time.monotonic()

    with _read_memo_lock:
        memo = _read_memo.get(memo_key)
    if memo is not None and (now - memo[1]) < GENERATION_READ_TTL_SECONDS:
        return memo[0]

    try:
        generation = cache.get(_generation_key(namespace, scope_id), 0)
    except Exception:  # pragma: no cover - defensive; cache backend down
        logger.warning(
            "cache_generation: read failed ns=%s scope=%s",
            namespace,
            scope_id,
            exc_info=True,
        )
        return memo[0] if memo is not None else 0

    if not isinstance(generation, int):  # pragma: no cover - defensive
        generation = 0

    with _read_memo_lock:
        _read_memo[memo_key] = (generation, now)
    return generation


def bump_cache_generation(namespace: str, scope_id: str) -> None:
    """Invalidate every worker's cached values for ``(namespace, scope_id)``.

    Increments the shared counter so that other processes observe a mismatch on
    their next read and recompute. The calling process's own memo is refreshed
    eagerly, so the worker that performed the write is immediately consistent
    regardless of :data:`GENERATION_READ_TTL_SECONDS`.

    Args:
        namespace: Logical cache family, e.g. ``"preset"``.
        scope_id: Scope the cache is keyed by, typically a workspace UUID string.

    Never raises: invalidation must not break the write that triggered it.
    """
    key = _generation_key(namespace, scope_id)
    generation = 0
    try:
        # ``add`` is a no-op when the key exists, so this is the standard
        # initialise-then-increment pattern. Two concurrent bumps on a missing
        # key may both land on 1 — harmless, since they represent invalidations
        # at the same instant and readers only compare for inequality.
        cache.add(key, 0, _GENERATION_KEY_TTL_SECONDS)
        generation = cache.incr(key)
    except ValueError:
        # ``incr`` raises ValueError when the key vanished between add and incr
        # (eviction/expiry). Re-seed rather than retry-loop: a counter that
        # restarts costs a recompute, not correctness.
        try:
            cache.set(key, 1, _GENERATION_KEY_TTL_SECONDS)
            generation = 1
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "cache_generation: re-seed failed ns=%s scope=%s",
                namespace,
                scope_id,
                exc_info=True,
            )
            return
    except Exception:  # pragma: no cover - defensive; cache backend down
        logger.warning(
            "cache_generation: bump failed ns=%s scope=%s",
            namespace,
            scope_id,
            exc_info=True,
        )
        return

    with _read_memo_lock:
        _read_memo[(namespace, scope_id)] = (generation, time.monotonic())


def reset_read_memo() -> None:
    """Drop this process's memoised generations (test hook / process reset)."""
    with _read_memo_lock:
        _read_memo.clear()


__all__ = [
    "GENERATION_READ_TTL_SECONDS",
    "bump_cache_generation",
    "cache_generation",
    "reset_read_memo",
]
