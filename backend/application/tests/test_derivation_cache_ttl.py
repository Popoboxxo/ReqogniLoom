"""PERF-009 / S2.2-01 — derivation cache counters need a bounded, refreshed TTL.

The version counter used to be written with ``cache.set(key, value, None)``:
Redis runs with ``noeviction``, so every artifact that ever had a derivation
left a key in the cache forever. A TTL alone is not enough, though — if the
counter expired while a result it namespaced were still alive, a fresh read
would recreate it at generation 1 and resurrect that stale result. These tests
pin both halves of the fix: the counter's TTL is longer than the result TTL,
and it is renewed on every read and every invalidation.

S2.2-01 (TOCTOU): renewing the TTL with ``cache.set(key, value, ttl)`` on every
read is itself unsafe — a read that observed v1 could write v1 back *after* a
concurrent invalidation bumped the counter to v2, resurrecting v1 results. The
renewal must use ``cache.touch`` (value untouched); ``cache.set`` is reserved
for creating an absent counter. The interleaving tests at the bottom pin this.
"""
from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from freezegun import freeze_time

from application import ai_derivation_service as ds
from application.ai_derivation_service import invalidate_derivation_cache

_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "derivation-cache-ttl-test",
        }
    }
)


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Fresh, Redis-free cache per test; time is controlled by freezegun."""
    with _CACHE_OVERRIDE:
        cache.clear()
        try:
            yield
        finally:
            cache.clear()


def test_version_ttl_is_longer_than_result_ttl() -> None:
    """24h counter vs 1h result: a counter cannot die before its results."""
    assert ds.DERIVATION_VERSION_TTL_SECONDS > ds.DERIVATION_CACHE_TTL_SECONDS

    with patch.object(ds, "cache") as mocked:
        mocked.get.return_value = None
        assert ds._derivation_version("art-ttl-1") == 1

    version_key, version, ttl = mocked.set.call_args.args
    assert version_key == "llm_derivation_ver:art-ttl-1"
    assert version == 1
    assert ttl == ds.DERIVATION_VERSION_TTL_SECONDS
    assert ttl is not None, "version keys must not be immortal (PERF-009)"

    # The result path still uses the shorter TTL; keep both sides of the
    # invariant pinned so a future edit cannot silently invert them.
    assert "cache.set(cache_key, result, DERIVATION_CACHE_TTL_SECONDS)" in (
        inspect.getsource(ds.AiDerivationService._complete)
    )


def test_repeated_reads_renew_the_version_ttl() -> None:
    """A read at 18h pushes expiry past the counter's original 24h deadline."""
    with freeze_time("2026-01-01 00:00:00"):
        assert ds._derivation_version("art-ttl-2") == 1

    with freeze_time("2026-01-01 18:00:00"):
        assert ds._derivation_version("art-ttl-2") == 1

    # Original expiry was 2026-01-02 00:00; the 18:00 read moved it to 18:00
    # the next day, so the counter is still alive here.
    with freeze_time("2026-01-02 12:00:00"):
        assert ds._derivation_version("art-ttl-2") == 1


def test_invalidate_renews_ttl_and_orphans_the_old_result_key() -> None:
    """After invalidation the old result key is unreachable via a new key."""
    with freeze_time("2026-01-01 23:30:00"):
        old_key = ds._derivation_cache_key("mock", "need_to_sysreq", "art-ttl-3", "prompt")
        cache.set(old_key, "stale-result", ds.DERIVATION_CACHE_TTL_SECONDS)
        assert cache.get(old_key) == "stale-result"

        invalidate_derivation_cache("art-ttl-3")

    # The counter written at 23:30 would have expired at 00:30 on 01-02 if the
    # invalidation had used no TTL, or had not renewed it. It is still there.
    with freeze_time("2026-01-02 12:00:00"):
        new_key = ds._derivation_cache_key("mock", "need_to_sysreq", "art-ttl-3", "prompt")
        assert new_key != old_key
        assert cache.get(new_key) is None, "stale result must be unreachable"


def test_invalidate_sets_counter_with_a_finite_ttl() -> None:
    """Both the incr and absent-counter paths give the counter a finite TTL.

    S2.2-01: on the existing-counter path the TTL is renewed with ``touch``
    (never ``set`` with the incr result), so concurrent invalidations cannot
    land out of order and leave the lower value. ``set`` is used only for the
    absent-counter fallback.
    """
    with patch.object(ds, "cache") as mocked:
        mocked.incr.return_value = 7
        invalidate_derivation_cache("art-ttl-4")
        mocked.touch.assert_called_once_with(
            "llm_derivation_ver:art-ttl-4",
            ds.DERIVATION_VERSION_TTL_SECONDS,
        )
        mocked.set.assert_not_called()

    with patch.object(ds, "cache") as mocked:
        mocked.incr.side_effect = ValueError("missing")
        invalidate_derivation_cache("art-ttl-5")
        assert mocked.set.call_args.args == (
            "llm_derivation_ver:art-ttl-5",
            2,
            ds.DERIVATION_VERSION_TTL_SECONDS,
        )
        mocked.touch.assert_not_called()


def test_read_renews_existing_counter_with_touch_not_set() -> None:
    """A read that finds a counter must renew via touch, never rewrite it."""
    with patch.object(ds, "cache") as mocked:
        mocked.get.return_value = 5
        assert ds._derivation_version("art-ttl-6") == 5
        mocked.touch.assert_called_once_with(
            "llm_derivation_ver:art-ttl-6",
            ds.DERIVATION_VERSION_TTL_SECONDS,
        )
        mocked.set.assert_not_called()


def test_stale_read_cannot_roll_back_counter_after_invalidate() -> None:
    """S2.2-01 TOCTOU: a read that observed v1 must never write v1 back.

    Deterministic interleaving: the reader's ``get()`` observes v1, then the
    concurrent invalidate bumps the counter to v2 *before* the reader renews
    the TTL. With the old ``set()``-based renewal the reader wrote its stale v1
    back and resurrected v1 results; ``touch()`` leaves the bumped value intact.
    """
    version_key = "llm_derivation_ver:art-race"

    class _InterleavingCache:
        def __init__(self) -> None:
            self.value = 1
            self.bumped = False
            self.set_calls: list[tuple[str, int, int]] = []

        def get(self, key, *args, **kwargs):
            assert key == version_key
            return self.value

        def incr(self, key, *args, **kwargs):
            assert key == version_key
            self.value += 1
            return self.value

        def touch(self, key, timeout, *args, **kwargs):
            assert key == version_key
            # Land the invalidate after get() saw v1 but before the reader
            # renews. A set()-based renewal would write the stale v1 here.
            if not self.bumped:
                self.bumped = True
                self.value = self.incr(key)  # concurrent invalidate: v1 -> v2
            return True

        def set(self, key, value, timeout, *args, **kwargs):
            self.set_calls.append((key, value, timeout))
            self.value = value
            return True

    fake = _InterleavingCache()
    with patch.object(ds, "cache", fake):
        # The reader observed v1; the invalidate bumped to v2 during renewal.
        assert ds._derivation_version("art-race") == 1
        assert fake.value == 2
        # A read never writes the counter value, so v1 cannot be resurrected.
        assert fake.set_calls == [], "a stale read wrote the counter via cache.set"
        # The very next read sees v2.
        assert ds._derivation_version("art-race") == 2

    assert fake.value == 2


def test_concurrent_invalidates_never_write_a_lower_counter() -> None:
    """S2.2-01: two interleaved invalidations cannot undo one another.

    The old ``incr()`` + ``set(incr_result)`` pattern let a slower invalidation
    write a lower counter after a faster one. With ``touch()`` the atomic
    ``incr()`` result is the single source of truth and no value is written
    back, so the counter advances monotonically.
    """
    version_key = "llm_derivation_ver:art-race-2"

    class _OutOfOrderCache:
        def __init__(self) -> None:
            self.value = 5
            self.set_calls: list[int] = []

        def incr(self, key, *args, **kwargs):
            assert key == version_key
            self.value += 1
            return self.value

        def touch(self, key, timeout, *args, **kwargs):
            assert key == version_key
            return True

        def set(self, key, value, timeout, *args, **kwargs):
            self.set_calls.append(value)
            self.value = value
            return True

    fake = _OutOfOrderCache()
    with patch.object(ds, "cache", fake):
        invalidate_derivation_cache("art-race-2")
        invalidate_derivation_cache("art-race-2")

    assert fake.value == 7, "counter did not advance monotonically"
    assert fake.set_calls == [], "an invalidate rewrote the counter via cache.set"
