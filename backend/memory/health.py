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

``ask_available`` is the natural-language sibling and is backend-specific: the
``ask`` contract is abstract and never raises, so every backend "has" it, but
only a dialectic backend (Honcho) can actually answer -- pgvector degrades by
design. Reporting that difference lets a client hide the surface instead of
calling it and always getting ``degraded=True``.

``derivation_status`` (AP-B5.1, #1155) is the deriver sibling: the envelope
answers the *scope-less capability* question (``unsupported`` for pgvector,
``unknown`` for a backend that can derive but has no scope to probe on this
surface), while the per-scope truth (``ok``/``none``/``failed``) travels on
the digest surface (``MemoryDigest.derivation_status``). This keeps "the
backend is healthy" from silently implying "it derives" -- the beta.18 Honcho
symptom where the Deriver never ran (Zen-Go quota, HTTP 429) while every
health read still said ``healthy``.
"""
from __future__ import annotations

from typing import Any, Dict

from django.core.cache import cache

from memory.backends import MemoryHealth, VALID_DERIVATION_STATUSES, get_memory_backend

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

#: Cache key for the ``ask_available`` capability probe -- the natural-language
#: sibling of :data:`DIGEST_CACHE_KEY`, cached separately for the same reason
#: (a bool, not a ``MemoryHealth``).
ASK_CACHE_KEY = "mem:memory:ask_available"

#: Cache key for the ``derivation_status`` capability probe (AP-B5.1, #1155) --
#: the deriver sibling of :data:`DIGEST_CACHE_KEY`/:data:`ASK_CACHE_KEY`,
#: cached separately for the same reason (a str, not a ``MemoryHealth``).
DERIVATION_CACHE_KEY = "mem:memory:derivation_status"

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
    """Drop every cached memory-health probe result.

    Called by the test suite today; there is deliberately NO production caller
    yet. A memory-settings write could use it to make a backend swap instant
    instead of within :data:`HEALTH_CACHE_TTL_SECONDS`, but the four probes are
    cached under four separate keys and would have to be invalidated as a set
    to avoid a torn envelope -- until that atomicity question is settled, the
    documented staleness window is the honest behaviour and an admin-write hook
    would only half-fix it.
    """
    for key in (HEALTH_CACHE_KEY, DIGEST_CACHE_KEY, ASK_CACHE_KEY, DERIVATION_CACHE_KEY):
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


def _probe_ask_available() -> bool:
    """Whether the active backend can answer a natural-language question.

    Unlike :func:`_probe_digest_available` (``True`` for every instantiable
    backend), this is backend-specific: ``ask`` is abstract and never raises,
    but only a backend with a generative dialectic surface can actually answer.
    ``PgvectorMemoryBackend`` declares ``ask_available = False`` -- it degrades
    by design -- so a client can hide the surface instead of invoking it and
    always getting ``degraded=True``. Never raises.
    """
    try:
        return bool(get_memory_backend().ask_available)
    except Exception:  # noqa: BLE001 - an unresolvable backend cannot answer
        return False


def ask_available(*, use_cache: bool = True) -> bool:
    """Return whether the active backend supports natural-language answers.

    Cached for :data:`HEALTH_CACHE_TTL_SECONDS` for the same reason the digest
    probe is: resolving a backend constructs it (and, for honcho, may read
    ``SystemMemorySettings``), which must not happen on every memory response.
    """
    if not use_cache:
        return _probe_ask_available()
    try:
        cached = cache.get(ASK_CACHE_KEY)
    except Exception:  # noqa: BLE001 - a cache outage must not fail the request
        return _probe_ask_available()
    if isinstance(cached, bool):
        return cached
    available = _probe_ask_available()
    try:
        cache.set(ASK_CACHE_KEY, available, HEALTH_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - see module docstring: best-effort cache
        pass
    return available


def _probe_derivation_status() -> str:
    """Scope-less derivation status of the active backend; never raises.

    The health surface has no scope to probe, so it can only answer the
    *capability* question (AP-B5.1, #1155): a backend with no deriver at all
    (``pgvector``) says ``unsupported``; a dialectic backend (``honcho``)
    keeps the base-class ``unknown``, which here reads as "derivation is
    possible, but this surface cannot tell whether it happened" -- the
    per-scope truth travels on the digest (``MemoryDigest.derivation_status``,
    surfaced by ``memory.digest``/REST digest). A rogue value that is not in
    ``VALID_DERIVATION_STATUSES`` normalises to ``unknown`` so the envelope
    vocabulary can never drift through a third-party backend.
    """
    try:
        raw = getattr(get_memory_backend(), "derivation_status", "unknown")
    except Exception:  # noqa: BLE001 - an unresolvable backend cannot derive either
        return "unknown"
    return raw if raw in VALID_DERIVATION_STATUSES else "unknown"


def derivation_status(*, use_cache: bool = True) -> str:
    """Return the active backend's scope-less derivation status.

    Cached for :data:`HEALTH_CACHE_TTL_SECONDS` for the same reason as the
    digest/ask probes: resolving a backend constructs it (and, for honcho, may
    read ``SystemMemorySettings``), which must not happen per memory response.
    """
    if not use_cache:
        return _probe_derivation_status()
    try:
        cached = cache.get(DERIVATION_CACHE_KEY)
    except Exception:  # noqa: BLE001 - a cache outage must not fail the request
        return _probe_derivation_status()
    if isinstance(cached, str) and cached in VALID_DERIVATION_STATUSES:
        return cached
    status = _probe_derivation_status()
    try:
        cache.set(DERIVATION_CACHE_KEY, status, HEALTH_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - see module docstring: best-effort cache
        pass
    return status


def envelope() -> Dict[str, Any]:
    """Return the response envelope.

    Shape: ``{backend, ok, detail, degraded, digest_available,
    ask_available, derivation_status}``.

    ``derivation_status`` (AP-B5.1, #1155) is the scope-less capability
    answer -- ``unsupported`` on backends without a deriver, ``unknown`` on
    backends that can derive but were not probed for a concrete scope here.
    The per-scope derivation truth lives on the digest surface
    (``MemoryDigest.derivation_status``), never on this cached envelope.
    """
    health = memory_health()
    return {
        "backend": health.backend,
        "ok": health.ok,
        "detail": health.detail,
        "degraded": (not health.ok) or health.degraded,
        "digest_available": digest_available(),
        "ask_available": ask_available(),
        "derivation_status": derivation_status(),
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
    "ASK_CACHE_KEY",
    "DERIVATION_CACHE_KEY",
    "memory_health",
    "digest_available",
    "ask_available",
    "derivation_status",
    "invalidate_health_cache",
    "is_degraded",
    "envelope",
    "health_view",
]
