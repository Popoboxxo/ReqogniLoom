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
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover - import-only
    # Forward reference to avoid a circular import at module load time
    # (item_permission.py defines PermissionDecision and imports the cache).
    from .item_permission import PermissionDecision


# Default TTL: 60 seconds (REQ-L1-039, spec §"Permission-Cache").
DEFAULT_TTL_SECONDS: float = 60.0


@dataclass(frozen=True)
class CacheEntry:
    """A single cache entry: the decision + the monotonic-clock expiry timestamp."""

    decision: "PermissionDecision"
    expires_at: float


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

        Expired entries are removed as a side effect (lazy eviction).
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
        """Wipe the calling thread's entire cache (used after grant/revoke)."""
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
    "CacheEntry",
]
