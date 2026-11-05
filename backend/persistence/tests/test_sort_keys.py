"""Unit tests for the fractional sort-key helper (P1, Task 1.1)."""
from __future__ import annotations

import random

import pytest

from persistence.sort_keys import BASE_62_DIGITS, key_between, rebalance_keys


def test_between_is_strictly_ordered_under_random_inserts() -> None:
    """1000 random inserts keep the key list strictly ascending and unique."""
    rng = random.Random(20261104)
    keys: list[str] = [key_between(None, None)]

    for _ in range(1000):
        index = rng.randrange(len(keys) + 1)
        before = keys[index - 1] if index > 0 else None
        after = keys[index] if index < len(keys) else None
        new_key = key_between(before, after)

        if before is not None:
            assert before < new_key
        if after is not None:
            assert new_key < after
        keys.insert(index, new_key)

    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))


def test_open_ends() -> None:
    first = key_between(None, None)
    assert isinstance(first, str) and first

    before_first = key_between(None, first)
    assert before_first < first

    last = key_between(first, None)
    assert first < last

    # Repeated appends stay short instead of growing by one digit each time.
    current = first
    for _ in range(1000):
        current = key_between(current, None)
    assert first < current
    assert len(current) <= 8


def test_equal_keys_raise() -> None:
    key = key_between(None, None)
    with pytest.raises(ValueError):
        key_between(key, key)


def test_inverted_bounds_raise() -> None:
    low = key_between(None, None)
    high = key_between(low, None)
    with pytest.raises(ValueError):
        key_between(high, low)


def test_rebalance_sorted_and_unique() -> None:
    for n in (0, 1, 2, 3, 17, 250):
        keys = rebalance_keys(n)
        assert len(keys) == n
        assert keys == sorted(keys)
        assert len(keys) == len(set(keys))


def test_keys_use_ascii_only_and_sort_identically_under_c_collation() -> None:
    """C collation compares raw bytes; for pure ASCII that equals Python order."""
    rng = random.Random(7)
    keys: list[str] = []
    for _ in range(200):
        index = rng.randrange(len(keys) + 1)
        before = keys[index - 1] if index > 0 else None
        after = keys[index] if index < len(keys) else None
        keys.insert(index, key_between(before, after))

    for key in keys:
        assert set(key) <= set(BASE_62_DIGITS)
        assert key.isascii()

    assert sorted(keys) == sorted(keys, key=lambda value: value.encode("ascii"))
