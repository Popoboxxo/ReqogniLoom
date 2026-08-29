"""SA-28 regression tests — cross-worker permission-cache invalidation.

SYSTEMAUDIT-2026-08-27 §4.1 #7: ``PermissionCache.invalidate_all`` only cleared
the calling thread's dict, so after an admin revoked a permission every *other*
request thread (and every other worker process) kept serving its cached
**allow** decision for the remainder of the 60s TTL.

A ``PermissionCache`` instance is a thin view over a process-wide
``threading.local()``, so "another worker" is simulated here by driving the cache
from a second thread — that thread has its own store and, before the fix, was
completely unaffected by an invalidation performed on the main thread.
"""
from __future__ import annotations

import threading
from uuid import uuid4

import pytest
from django.core.cache import cache

from auth_tenancy.services.item_permission import PermissionDecision
from auth_tenancy.services.permission_cache import (
    GENERATION_NAMESPACE,
    GENERATION_SCOPE,
    PermissionCache,
    bump_generation,
    current_generation,
)
from persistence import cache_generation as cache_generation_module


ALLOW = PermissionDecision(level="write", reason="workspace-wide rule")
DENY = PermissionDecision(level="deny", reason="closed-world default")

# Mirrors persistence.cache_generation._generation_key for the scope this
# module owns. Duplicated (not imported) on purpose: if the key layout ever
# changes, this test should fail loudly rather than silently follow along.
_GENERATION_KEY = f"reqogniloom:cachegen:{GENERATION_NAMESPACE}:{GENERATION_SCOPE}"


@pytest.fixture(autouse=True)
def _isolate_generation_state():
    """Reset the shared counter and every process memo between tests."""
    cache.delete(_GENERATION_KEY)
    cache_generation_module.reset_read_memo()
    PermissionCache.clear_thread()
    yield
    cache.delete(_GENERATION_KEY)
    cache_generation_module.reset_read_memo()
    PermissionCache.clear_thread()


@pytest.fixture(autouse=True)
def _probe_every_call(monkeypatch):
    """Drive the generation read TTL to 0 so tests observe bumps immediately.

    The 1s default is a latency optimisation, not part of the contract under
    test; keeping it here would only add a sleep. ``test_probe_interval_bounds_
    staleness`` covers the memo behaviour explicitly.
    """
    monkeypatch.setattr(
        cache_generation_module, "GENERATION_READ_TTL_SECONDS", 0.0
    )


def _key() -> dict:
    return {
        "user_id": uuid4(),
        "workspace_id": uuid4(),
        "artifact_id": None,
    }


class TestCrossThreadInvalidation:
    """The core SA-28 property."""

    def test_revoke_on_one_thread_invalidates_another_thread(self) -> None:
        key = _key()

        # Thread B caches an ALLOW decision in its own thread-local store.
        cached_in_b: list = []

        def _worker_b_prime() -> None:
            PermissionCache().set(**key, decision=ALLOW)
            cached_in_b.append(PermissionCache().get(**key))

        t = threading.Thread(target=_worker_b_prime)
        t.start()
        t.join()
        assert cached_in_b == [ALLOW], "thread B should have warmed its cache"

        # The admin's request lands on thread A and revokes the permission.
        PermissionCache().invalidate_all()

        # Thread B must NOT serve its stale allow any more.
        seen_after: list = []

        def _worker_b_reread() -> None:
            seen_after.append(PermissionCache().get(**key))

        t2 = threading.Thread(target=_worker_b_reread)
        t2.start()
        t2.join()

        assert seen_after == [None], (
            "SA-28: a revoke on another thread must invalidate this thread's "
            "cached allow instead of letting it live out the 60s TTL"
        )

    def test_writing_thread_is_immediately_consistent(self) -> None:
        cache_obj = PermissionCache()
        key = _key()
        cache_obj.set(**key, decision=ALLOW)
        assert cache_obj.get(**key) == ALLOW

        cache_obj.invalidate_all()
        assert cache_obj.get(**key) is None

    def test_entries_written_after_the_bump_survive(self) -> None:
        """Invalidation must not permanently poison the cache."""
        cache_obj = PermissionCache()
        key = _key()

        cache_obj.invalidate_all()
        cache_obj.set(**key, decision=DENY)
        assert cache_obj.get(**key) == DENY


class TestGenerationCounter:
    """Behaviour of the counter itself."""

    def test_generation_starts_at_zero(self) -> None:
        assert current_generation() == 0

    def test_bump_increments(self) -> None:
        before = current_generation()
        bump_generation()
        assert current_generation() == before + 1

    def test_entry_generation_mismatch_is_a_miss(self) -> None:
        cache_obj = PermissionCache()
        key = _key()
        cache_obj.set(**key, decision=ALLOW)

        # Simulate another process bumping the counter.
        bump_generation()
        cache_generation_module.reset_read_memo()

        assert cache_obj.get(**key) is None

    def test_read_memo_delays_a_foreign_bump(self, monkeypatch) -> None:
        """With a long read TTL a *foreign* bump is not observed immediately.

        Pins the documented trade-off honestly: the propagation window is the
        generation read TTL, not zero. It is still far below the 60s entry TTL,
        which is what SA-28 is about.
        """
        monkeypatch.setattr(
            cache_generation_module, "GENERATION_READ_TTL_SECONDS", 300.0
        )
        cache_obj = PermissionCache()
        key = _key()
        cache_obj.set(**key, decision=ALLOW)  # memoises generation 0

        # Another process bumps the shared counter directly. This process's
        # memo is untouched, so it keeps serving until the memo expires.
        cache.set(_GENERATION_KEY, 1, None)
        assert cache_obj.get(**key) == ALLOW

        # Once the memo expires the bump is observed and the entry is dropped.
        cache_generation_module.reset_read_memo()
        assert cache_obj.get(**key) is None


class TestBackendFailureIsFailSafe:
    """A cache outage must degrade, not break."""

    def test_bump_swallows_backend_errors(self, monkeypatch) -> None:
        def _boom(*args, **kwargs):
            raise RuntimeError("redis down")

        monkeypatch.setattr(cache_generation_module.cache, "add", _boom)
        monkeypatch.setattr(cache_generation_module.cache, "incr", _boom)
        monkeypatch.setattr(cache_generation_module.cache, "set", _boom)

        # Must not raise: invalidation may not roll back the grant/revoke.
        PermissionCache().invalidate_all()

    def test_read_failure_keeps_serving_the_local_cache(
        self, monkeypatch
    ) -> None:
        """Fail-safe: an unreachable cache degrades to the pre-SA-28 TTL bound."""
        cache_obj = PermissionCache()
        key = _key()
        cache_obj.set(**key, decision=ALLOW)

        def _boom(*args, **kwargs):
            raise RuntimeError("redis down")

        monkeypatch.setattr(cache_generation_module.cache, "get", _boom)
        cache_generation_module.reset_read_memo()

        # Generation falls back to 0, matching the entry — the decision is
        # still served, exactly as it was before this fix. The 60s entry TTL
        # remains the backstop.
        assert cache_obj.get(**key) == ALLOW
