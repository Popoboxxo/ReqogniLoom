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

Capability reporting (RFC #1002 F6)
-----------------------------------
The envelope also carries ``digest_available``: whether the active backend
implements the digest contract. It exists so a *client* can hide/disable a
digest surface instead of discovering an unimplemented capability by calling it
and rendering an empty panel — the shipped backends all implement it, so ``True``
is the normal answer and ``False`` means "the active backend could not be
resolved" (in which case ``degraded`` already says the backend is unusable). It
is probed and cached separately from the health *result*, because the health
cache holds a :class:`~memory.backends.MemoryHealth` (a different object) and
resolving a backend on every request would re-read ``SystemMemorySettings``.
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

#: Cache key for the ``digest_available`` capability probe. Separate from
#: :data:`HEALTH_CACHE_KEY` because it is a bool, not a ``MemoryHealth``; same
#: TTL, so a backend swap is reflected within one window on both.
DIGEST_CACHE_KEY = "mem:memory:digest_available"

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
    for key in (HEALTH_CACHE_KEY, DIGEST_CACHE_KEY):
        try:
            cache.delete(key)
        except Exception:  # noqa: BLE001 - best-effort, mirrors the read path
            pass


def _probe_digest_available() -> bool:
    """Whether the active backend exposes a callable ``digest``; never raises.

    Since ``MemoryBackend.digest`` is abstract, this is ``True`` for every
    backend that could be instantiated at all; the probe exists so a legacy or
    third-party backend that bypasses the ABC cannot make a digest surface
    advertise a capability it does not have.
    """
    try:
        return callable(getattr(get_memory_backend(), "digest", None))
    except Exception:  # noqa: BLE001 - an unresolvable backend has no digest
        return False


def digest_available(*, use_cache: bool = True) -> bool:
    """Return whether the active backend implements the digest contract.

    Cached for :data:`HEALTH_CACHE_TTL_SECONDS` for the same reason the health
    probe is: resolving a backend constructs it (and, for honcho, may read
    ``SystemMemorySettings``), which must not happen on every memory response.
    """
    if not use_cache:
        return _probe_digest_available()
    try:
        cached = cache.get(DIGEST_CACHE_KEY)
    except Exception:  # noqa: BLE001 - a cache outage must not fail the request
        return _probe_digest_available()
    if isinstance(cached, bool):
        return cached
    available = _probe_digest_available()
    try:
        cache.set(DIGEST_CACHE_KEY, available, HEALTH_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - see module docstring: best-effort cache
        pass
    return available


def is_degraded() -> bool:
    """Whether the active backend is currently unhealthy/degraded."""
    health = memory_health()
    return (not health.ok) or health.degraded


def envelope() -> Dict[str, Any]:
    """Return the response envelope: ``{backend, ok, detail, degraded, digest_available}``."""
    health = memory_health()
    return {
        "backend": health.backend,
        "ok": health.ok,
        "detail": health.detail,
        "degraded": (not health.ok) or health.degraded,
        "digest_available": digest_available(),
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
    "DIGEST_CACHE_KEY",
    "memory_health",
    "digest_available",
    "invalidate_health_cache",
    "is_degraded",
    "envelope",
    "health_view",
]
