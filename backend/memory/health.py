"""Health + ``degraded`` envelope for memory responses (RFC #1002 PR B, F9).

Every REST and MCP memory response must carry ``backend`` and ``degraded``. The
semantics are defined exactly once, here:

* ``backend`` is the active backend's identifier (``pgvector``/``honcho``/...);
* ``degraded`` is ``True`` whenever the active backend is not healthy — i.e.
  ``not health.ok or health.degraded`` (a backend can be reachable but unable
  to do its full job, e.g. an unconfigured embedding endpoint).

F9's whole point is that "the backend is down" must be distinguishable from
"nothing is remembered": a read that legitimately returns no rows still answers
``degraded=True`` when the backend is unhealthy, so an agent does not conclude
"no memory exists" from an outage.

Calling ``backend.health()`` on every request would be unacceptable — the honcho
probe performs a real HTTP round trip. The result is therefore cached in the
Django cache for :data:`HEALTH_CACHE_TTL_SECONDS`; a settings/backend change is
picked up within that TTL rather than instantly, which is the same
best-effort staleness trade-off ``admin_ops.rate_limits`` makes.
"""
from __future__ import annotations

from typing import Any, Dict

from django.core.cache import cache

from memory.backends import MemoryHealth, get_memory_backend

#: Short enough that a backend recovering (or going down) is reflected quickly,
#: long enough that the honcho network probe does not run per request.
HEALTH_CACHE_TTL_SECONDS = 20

#: Single cache key: the process has exactly one active memory backend, and the
#: resolved ``MemoryHealth`` carries its own ``backend`` name for the response.
HEALTH_CACHE_KEY = "mem:memory:health"

#: Fail-safe fallback used when the cache itself is unavailable. Reported as
#: degraded because "cannot confirm the backend" must never masquerade as
#: "healthy".
_UNKNOWN_HEALTH = MemoryHealth(
    ok=False,
    backend="unknown",
    detail="memory backend health could not be determined",
    degraded=True,
)


def _probe() -> MemoryHealth:
    """Call the active backend's ``health()``; never raises."""
    try:
        backend = get_memory_backend()
        return backend.health()
    except Exception as exc:  # noqa: BLE001 - any failure is a "down"/degraded detail
        return MemoryHealth(
            ok=False, backend="unknown", detail=str(exc), degraded=True
        )


def memory_health(*, use_cache: bool = True) -> MemoryHealth:
    """Return the active backend's health, cached for :data:`HEALTH_CACHE_TTL_SECONDS`."""
    if not use_cache:
        return _probe()
    try:
        cached = cache.get(HEALTH_CACHE_KEY)
    except Exception:  # noqa: BLE001 - a cache outage must not fail the request
        return _probe()
    if isinstance(cached, MemoryHealth):
        return cached
    health = _probe()
    try:
        cache.set(HEALTH_CACHE_KEY, health, HEALTH_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - see module docstring: best-effort cache
        pass
    return health


def invalidate_health_cache() -> None:
    """Drop the cached health result (called by tests and admin writes)."""
    try:
        cache.delete(HEALTH_CACHE_KEY)
    except Exception:  # noqa: BLE001 - best-effort, mirrors the read path
        pass


def is_degraded() -> bool:
    """Whether the active backend is currently unhealthy/degraded."""
    health = memory_health()
    return (not health.ok) or health.degraded


def envelope() -> Dict[str, Any]:
    """Return the ``{backend, ok, detail, degraded}`` envelope for responses."""
    health = memory_health()
    return {
        "backend": health.backend,
        "ok": health.ok,
        "detail": health.detail,
        "degraded": (not health.ok) or health.degraded,
    }


def health_view() -> Dict[str, Any]:
    """Return the shape used by the ``admin/health`` ``memory`` component.

    Same fields as :func:`envelope`, so REST/MCP/admin all describe the backend
    identically.
    """
    return envelope()


__all__ = [
    "HEALTH_CACHE_TTL_SECONDS",
    "HEALTH_CACHE_KEY",
    "memory_health",
    "invalidate_health_cache",
    "is_degraded",
    "envelope",
    "health_view",
]
