"""
COMP-AT-005 ItemPermissionStore — thread-local TTL cache (REQ-L1-039).

``PermissionCache`` stores ``PermissionDecision`` instances keyed by the frozen
triple ``(user_id, workspace_id, artifact_id_or_None)``. The cache lives on
``threading.local()`` so each Django request thread owns its own dict, matching
the same pattern used by ``persistence.tenancy.TenantContext``.

MVP implementation: a plain ``dict`` with per-entry expiry timestamps. A cache
hit returns the stored decision if and only if ``now < expires_at``. Expired
entries are evicted lazily on read; the whole dict can be wiped with
:meth:`invalidate_all` (used after any ``grant``/``revoke`` write).

Worst-case footprint: bounded by the number of distinct
``(user, workspace, artifact)`` triples checked during a single request, which
is small in practice (the auth context carries one user; the request touches
at most a handful of artifacts). No eviction cap is needed at MVP scale.

Thread safety: each thread sees its own dict. No lock is taken on read/write.
A request that spans multiple threads (e.g. async views) will not share cache
state, which is the correct behaviour (different threads mean different
tenants/requests).

Cross-worker invalidation (SYSTEMAUDIT-2026-08-27 SA-28, §4.1 #7)
-----------------------------------------------------------------
``invalidate_all`` used to clear only the *calling* thread's dict. Every other
request thread — and every other Gunicorn/Celery worker process — kept serving
its own cached decisions for up to the full TTL. For an **allow** decision that
means a revoked permission stayed effective for up to 60 seconds after the
admin revoked it, which is a security property, not a latency detail.

The fix reuses the shared **generation counter** from
:mod:`persistence.cache_generation` (SA-29's cross-worker invalidation
primitive, backed by the Redis cache in ``settings.CACHES``). Every entry
records the generation it was computed under; a grant/revoke bumps the counter,
and every other worker's next read observes the new value and discards its own
entries. Correctness therefore no longer depends on which thread handled the
write.

Residual staleness: the counter is memoised per process for
``cache_generation.GENERATION_READ_TTL_SECONDS`` (default 1s) so a hot
permission loop costs at most one cache round trip per second rather than one
per check. The revoke propagation window therefore shrinks from the 60s TTL to
roughly that interval — bounded and documented, not eliminated. If the shared
cache is unreachable the helper is fail-safe (it keeps the last generation it
saw), which degrades to exactly the pre-fix behaviour: still bounded by the 60s
TTL, never worse than today.

Blast radius: the counter uses a single global scope rather than one per tenant
or workspace, so any grant/revoke invalidates every worker's permission cache.
Permission writes are rare admin operations, so the extra recomputation is
cheaper than the bookkeeping a finer-grained counter would need — and
``invalidate_all`` was already deliberately coarse (a workspace-wide default
rule change can affect artifact-scoped decisions).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from persistence.cache_generation import bump_cache_generation, cache_generation

if TYPE_CHECKING:  # pragma: no cover - import-only
    # Forward reference to avoid a circular import at module load time
    # (item_permission.py defines PermissionDecision and imports the cache).
    from .item_permission import PermissionDecision


# Default TTL: 60 seconds (REQ-L1-039, spec §"Permission-Cache").
DEFAULT_TTL_SECONDS: float = 60.0

# Generation-counter coordinates (SA-28). A single global scope: every
# grant/revoke invalidates every cached decision — see the module docstring for
# why the coarse blast radius is the right trade-off here.
GENERATION_NAMESPACE: str = "item-permission"
GENERATION_SCOPE: str = "all"


def current_generation() -> int:
    """Return the shared permission-cache generation (SA-28)."""
    return cache_generation(GENERATION_NAMESPACE, GENERATION_SCOPE)


def bump_generation() -> None:
    """Invalidate every worker's permission cache (SA-28).

    Never raises: a failed invalidation must not roll back the grant/revoke that
    triggered it — the local wipe plus the 60s TTL remain as backstops.
    """
    bump_cache_generation(GENERATION_NAMESPACE, GENERATION_SCOPE)


@dataclass(frozen=True)
class CacheEntry:
    """A single cache entry: the decision, its expiry and its generation.

    ``generation`` is the shared counter value observed when the entry was
    written. A mismatch against the current counter means some worker has
    changed permissions since, so the entry must not be served (SA-28).
    """

    decision: "PermissionDecision"
    expires_at: float
    generation: int = 0


class PermissionCache:
    """Thread-local TTL cache for :class:`PermissionDecision` values.

    The public surface is the four methods ``get`` / ``set`` / ``invalidate``
    / ``invalidate_all`` operating on the calling thread's dict.

    Cache key: ``(user_id: UUID, workspace_id: UUID, artifact_id: UUID | None)``.
    The literal ``None`` for ``artifact_id`` is part of the key and represents
    the workspace-wide check; it cannot collide with a real UUID.
    """

    def __init__(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl_seconds = float(ttl_seconds)
        # Local store is a process-wide thread-local; all instances share it.
        _ThreadLocalCacheStore.ensure()
        self._local = _ThreadLocalCacheStore._thread_local

    # -- Public API -------------------------------------------------------

    def get(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        artifact_id: Optional[UUID],
    ) -> Optional["PermissionDecision"]:
        """Return the cached decision for ``key`` or ``None`` if absent/expired.

        An entry is served only when it is (a) present, (b) still within its
        TTL and (c) written under the current shared generation (SA-28). Any of
        the three failing evicts the entry and reports a miss, so the caller
        recomputes from the database.
        """
        _ThreadLocalCacheStore.ensure()
        key = (user_id, workspace_id, artifact_id)
        entry = self._local.store.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            # Lazy evict
            self._local.store.pop(key, None)
            return None
        if entry.generation != current_generation():
            # SA-28: another worker granted/revoked since this entry was
            # written. Drop it rather than serving a decision that may now be
            # a stale "allow".
            self._local.store.pop(key, None)
            return None
        return entry.decision

    def set(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        artifact_id: Optional[UUID],
        decision: "PermissionDecision",
    ) -> None:
        """Store ``decision`` under the given key, with the configured TTL."""
        _ThreadLocalCacheStore.ensure()
        key = (user_id, workspace_id, artifact_id)
        self._local.store[key] = CacheEntry(
            decision=decision,
            expires_at=time.monotonic() + self._ttl_seconds,
            generation=current_generation(),
        )

    def invalidate(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        artifact_id: Optional[UUID],
    ) -> None:
        """Remove a single key from the calling thread's cache.

        Provided for completeness; the service layer currently uses
        :meth:`invalidate_all` because the resolution algorithm is sensitive
        to workspace-wide default changes that may not be the rule just
        touched.
        """
        _ThreadLocalCacheStore.ensure()
        key = (user_id, workspace_id, artifact_id)
        self._local.store.pop(key, None)

    def invalidate_all(self) -> None:
        """Invalidate the permission cache in **every** worker (SA-28).

        Two steps, in this order:

        1. Bump the shared generation counter so all other threads/processes
           discard their entries on their next read.
        2. Clear the calling thread's dict, so the thread that performed the
           write is consistent immediately and does not have to wait for its
           own generation probe to expire.
        """
        bump_generation()
        _ThreadLocalCacheStore.ensure()
        self._local.store.clear()

    @classmethod
    def clear_thread(cls) -> None:
        """Clear the current thread's cache. Used by test teardown."""
        _ThreadLocalCacheStore.ensure()
        store = getattr(_ThreadLocalCacheStore._thread_local, "store", None)
        if store is not None:
            store.clear()


class _ThreadLocalCacheStore:
    """Process-wide holder for the thread-local cache dict.

    A single ``threading.local()`` is used so all ``PermissionCache`` instances
    in the process share per-thread state. This mirrors the pattern in
    :mod:`persistence.tenancy` where :class:`TenantContext` also lives on a
    single thread-local namespace.
    """

    _thread_local = threading.local()

    @classmethod
    def ensure(cls) -> None:
        """Initialise the per-thread ``store`` dict if not yet present."""
        if not hasattr(cls._thread_local, "store"):
            cls._thread_local.store = {}


__all__ = [
    "PermissionCache",
    "DEFAULT_TTL_SECONDS",
    "GENERATION_NAMESPACE",
    "GENERATION_SCOPE",
    "CacheEntry",
    "bump_generation",
    "current_generation",
]
