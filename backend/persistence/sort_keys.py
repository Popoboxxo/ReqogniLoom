"""Fractional sort keys for persistent sibling ordering.

Implements *fractional indexing* (David Greenspan, `Implementing Fractional
Indexing`, <https://observablehq.com/@dgreensp/implementing-fractional-indexing>)
as a small, dependency-free port of the CC0 reference implementation
(<https://github.com/rocicorp/fractional-indexing>). A key is a short ASCII
string; inserting between two existing keys only requires writing exactly one
row.

The alphabet is base-62 (``0-9A-Za-z`` in ascending character-code order), and
the integer part uses the classic ``A-Za-z`` head markers, so a fresh key looks
like ``a0``, ``a1``, ``a2``, ... Generated keys are pure ASCII and compare
identically under PostgreSQL collation ``C`` and Python's default string
comparison.
"""
from __future__ import annotations

from functools import cache
from math import floor

BASE_62_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
# Head markers for the variable-length integer part (the pre-0.2 "a0" form).
BASE_52_DIGITS = BASE_62_DIGITS[10:]

_DIGITS = BASE_62_DIGITS
_INT_DIGITS = BASE_52_DIGITS


@cache
def _digit_index(digits: str) -> dict[str, int]:
    return {c: i for i, c in enumerate(digits)}


@cache
def _smallest_integer() -> str:
    return _INT_DIGITS[0] + _DIGITS[0] * (len(_INT_DIGITS) // 2)


def _get_integer_length(head: str, lookup: dict[str, int]) -> int:
    i = lookup.get(head, 0)
    if i >= len(_INT_DIGITS) or _INT_DIGITS[i] != head:
        raise ValueError(f"invalid sort key head: {head!r}")
    half = len(_INT_DIGITS) // 2
    return half - i + 1 if i < half else i - half + 2


def _get_integer_part(key: str, lookup: dict[str, int]) -> str:
    length = _get_integer_length(key[0], lookup)
    if length > len(key):
        raise ValueError(f"invalid sort key: {key!r}")
    return key[:length]


def _validate_key(key: str, lookup: dict[str, int]) -> None:
    if key == _smallest_integer():
        raise ValueError(f"invalid sort key: {key!r}")
    integer_part = _get_integer_part(key, lookup)
    fraction = key[len(integer_part):]
    if fraction and fraction[-1] == _DIGITS[0]:
        raise ValueError(f"invalid sort key (trailing zero): {key!r}")


def _increment_integer(x: str, lookup: dict[str, int], int_lookup: dict[str, int]) -> str | None:
    if len(x) != _get_integer_length(x[0], int_lookup):
        raise ValueError(f"invalid integer part: {x!r}")
    head = x[0]
    zero = _DIGITS[0]
    trailing = ""
    for i in range(len(x) - 1, 0, -1):
        d = lookup.get(x[i], 0) + 1
        if d == len(_DIGITS):
            trailing = zero + trailing
        else:
            return x[:i] + _DIGITS[d] + trailing
    head_index = int_lookup.get(head, 0)
    if head_index >= len(_INT_DIGITS) - 1:
        return None
    new_head = _INT_DIGITS[head_index + 1]
    delta = _get_integer_length(new_head, int_lookup) - _get_integer_length(head, int_lookup)
    if delta > 0:
        return new_head + trailing + zero
    if delta < 0:
        return new_head + trailing[1:]
    return new_head + trailing


def _decrement_integer(x: str, lookup: dict[str, int], int_lookup: dict[str, int]) -> str | None:
    if len(x) != _get_integer_length(x[0], int_lookup):
        raise ValueError(f"invalid integer part: {x!r}")
    head = x[0]
    last = _DIGITS[-1]
    trailing = ""
    for i in range(len(x) - 1, 0, -1):
        d = lookup.get(x[i], 0) - 1
        if d == -1:
            trailing = last + trailing
        else:
            return x[:i] + _DIGITS[d] + trailing
    head_index = int_lookup.get(head, 0)
    if head_index == 0:
        return None
    new_head = _INT_DIGITS[head_index - 1]
    delta = _get_integer_length(new_head, int_lookup) - _get_integer_length(head, int_lookup)
    if delta > 0:
        return new_head + trailing + last
    if delta < 0:
        return new_head + trailing[1:]
    return new_head + trailing


def _midpoint(a: str, b: str | None, lookup: dict[str, int]) -> str:
    zero = _DIGITS[0]
    if b is not None and a >= b:
        raise ValueError(f"{a!r} >= {b!r}")
    if (a and a[-1] == zero) or (b is not None and b[-1] == zero):
        raise ValueError("trailing zero")
    if b:
        n = 0
        while n < len(b) and (a[n] if n < len(a) else zero) == b[n]:
            n += 1
        if n > 0:
            return b[:n] + _midpoint(a[n:], b[n:], lookup)
    digit_a = lookup.get(a[0], 0) if a else 0
    digit_b = lookup.get(b[0], 0) if b is not None else len(_DIGITS)
    if digit_b - digit_a > 1:
        return _DIGITS[(digit_a + digit_b + 1) // 2]
    if b is not None and len(b) > 1:
        return b[:1]
    return _DIGITS[digit_a] + _midpoint(a[1:], None, lookup)


def _generate_key_between(a: str | None, b: str | None) -> str:
    lookup = _digit_index(_DIGITS)
    int_lookup = _digit_index(_INT_DIGITS)
    if a is not None:
        _validate_key(a, int_lookup)
    if b is not None:
        _validate_key(b, int_lookup)

    if a is None:
        if b is None:
            return _INT_DIGITS[len(_INT_DIGITS) // 2] + _DIGITS[0]
        ib = _get_integer_part(b, int_lookup)
        fb = b[len(ib):]
        if ib == _smallest_integer():
            return ib + _midpoint("", fb, lookup)
        if ib < b:
            return ib
        result = _decrement_integer(ib, lookup, int_lookup)
        if result is None:
            raise ValueError("cannot decrement any more")
        return result

    if b is None:
        ia = _get_integer_part(a, int_lookup)
        fa = a[len(ia):]
        incremented = _increment_integer(ia, lookup, int_lookup)
        if incremented is None:
            return ia + _midpoint(fa, None, lookup)
        return incremented

    ia = _get_integer_part(a, int_lookup)
    fa = a[len(ia):]
    ib = _get_integer_part(b, int_lookup)
    fb = b[len(ib):]
    if ia == ib:
        return ia + _midpoint(fa, fb, lookup)
    incremented = _increment_integer(ia, lookup, int_lookup)
    if incremented is None:
        raise ValueError("cannot increment any more")
    if incremented < b:
        return incremented
    return ia + _midpoint(fa, None, lookup)


def key_between(before: str | None, after: str | None) -> str:
    """Return a key strictly between ``before`` and ``after``.

    ``None`` means an open end. Both bounds may be ``None`` (first element).
    Raises ``ValueError`` if both are given and ``before >= after``.
    """
    if before is not None and after is not None and before >= after:
        raise ValueError(f"before ({before!r}) must sort before after ({after!r})")
    return _generate_key_between(before, after)


def rebalance_keys(n: int) -> list[str]:
    """Return ``n`` ascending, distinct keys evenly spread over the key space.

    Used to (re)build a whole sibling block: backfill, import and rare
    rebalances. ``rebalance_keys(0)`` returns an empty list.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0: {n}")
    if n == 0:
        return []
    if n == 1:
        return [_generate_key_between(None, None)]

    mid = floor(n / 2)
    center = _generate_key_between(None, None)
    lower = _generate_n_keys_between(None, center, mid)
    upper = _generate_n_keys_between(center, None, n - mid - 1)
    return [*lower, center, *upper]


def _generate_n_keys_between(a: str | None, b: str | None, n: int) -> list[str]:
    if n == 0:
        return []
    if n == 1:
        return [_generate_key_between(a, b)]
    if b is None:
        current = _generate_key_between(a, None)
        result = [current]
        for _ in range(n - 1):
            current = _generate_key_between(current, None)
            result.append(current)
        return result
    if a is None:
        current = _generate_key_between(None, b)
        result = [current]
        for _ in range(n - 1):
            current = _generate_key_between(None, current)
            result.append(current)
        return list(reversed(result))
    mid = floor(n / 2)
    center = _generate_key_between(a, b)
    return [
        *_generate_n_keys_between(a, center, mid),
        center,
        *_generate_n_keys_between(center, b, n - mid - 1),
    ]
