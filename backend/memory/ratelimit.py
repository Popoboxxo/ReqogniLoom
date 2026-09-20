"""Fixed-window write ratelimit for ``memory.write`` (RFC #1002 PR B, §5).

The limit is admin-configurable and never hardcoded:

1. ``SystemMemorySettings.memory_write_rate_limit_per_hour`` (DB override) when
   not ``NULL``;
2. else ``MEMORY_WRITE_RATE_LIMIT_PER_HOUR`` from the environment;
3. else :data:`DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR` (60).

``0`` is an explicit "unlimited" override — both the DB value and the env value
resolve to ``None`` (no limit enforced). A negative or unparsable env value is
treated as the default rather than as "unlimited", so a typo can never silently
disable the guard.

Counting is a fixed-window counter in the Django cache (Redis in production),
keyed per ``(tenant, user)`` per calendar hour. The window is *fixed*, not
sliding: the counter resets at the top of each hour, so a caller can make up to
``2 * limit - 1`` writes around a window boundary. That is the documented
trade-off of this small guard — it bounds sustained abuse, not an exactly
enforced quota; a sliding window would cost an extra sorted-set per user for a
limit whose purpose is protecting an LLM/embedding budget, not billing.

Failure policy matches ``admin_ops.rate_limits``: a cache outage is logged and
treated as "no counter available" (fail-open) rather than turning a Redis blip
into a 500 on a legitimate write.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Environment variable consulted when no DB override is set.
RATE_LIMIT_ENV_VAR = "MEMORY_WRITE_RATE_LIMIT_PER_HOUR"

#: Fallback used when neither the DB override nor the env var is set.
DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR = 60

#: Counter window length in seconds (one hour).
WINDOW_SECONDS = 3600


class MemoryWriteRateLimitExceeded(RuntimeError):
    """Raised when a caller exceeds the configured ``memory.write`` limit.

    Carries the structured values the REST layer needs for a ``Retry-After``
    header and the MCP layer needs for a JSON-RPC error detail.
    """

    def __init__(self, *, limit: int, retry_after: int) -> None:
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(
            f"memory.write rate limit exceeded: {limit} writes per hour. "
            f"Retry after {retry_after} seconds."
        )


def _coerce_limit(value: Any) -> Optional[int]:
    """Return an int limit, or ``None`` for "unlimited"/unparsable-input default.

    ``0``/negative-int strings are "unlimited" only for ``0`` (an explicit
    opt-out); anything unparsable falls back to
    :data:`DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR`.
    """
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR
    return number


def resolve_write_rate_limit() -> Optional[int]:
    """Return the effective writes-per-hour limit, or ``None`` for unlimited.

    DB override wins over the environment; see the module docstring for the
    precedence and the ``0`` semantics.
    """
    try:
        from memory.models import SystemMemorySettings

        row = SystemMemorySettings.objects.first()
        if row is not None and row.memory_write_rate_limit_per_hour is not None:
            value = int(row.memory_write_rate_limit_per_hour)
            return value if value > 0 else None
    except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback
        pass

    raw = os.environ.get(RATE_LIMIT_ENV_VAR)
    if raw is None or not str(raw).strip():
        return DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR
    value = _coerce_limit(raw)
    if value is None:
        return None
    return value if value > 0 else None


def _window(now: Optional[float] = None) -> tuple[int, int]:
    """Return ``(window_index, seconds_until_reset)`` for the current hour."""
    timestamp = int(now if now is not None else time.time())
    window_index = timestamp // WINDOW_SECONDS
    seconds_until_reset = WINDOW_SECONDS - (timestamp % WINDOW_SECONDS)
    return window_index, seconds_until_reset


def _counter_key(ctx: Any, window_index: int) -> str:
    """Per-(tenant, user) counter key for one fixed window."""
    return f"mem:write:rl:{ctx.tenant_id}:{ctx.user_id}:{window_index}"


def check_write_rate_limit(ctx: Any, *, now: Optional[float] = None) -> int:
    """Increment and return the caller's write count for this window.

    Returns ``0`` when the limit is unlimited or the cache is unavailable (the
    caller then performs the write without a quota). Never raises for a cache
    failure — see the module docstring.
    """
    limit = resolve_write_rate_limit()
    if limit is None:
        return 0

    window_index, seconds_until_reset = _window(now)
    key = _counter_key(ctx, window_index)
    try:
        # add() is atomic and seeds the counter exactly once; incr() returns the
        # post-increment value, so the FIRST write already reads 1.
        cache.add(key, 0, timeout=seconds_until_reset)
        count = cache.incr(key)
    except ValueError:
        # The key expired between add() and incr() (only possible at a window
        # boundary); treat this write as the first of the new window.
        try:
            cache.set(key, 1, timeout=seconds_until_reset)
        except Exception:  # noqa: BLE001 - best-effort
            return 0
        count = 1
    except Exception:  # noqa: BLE001 - a cache outage must not block writes
        logger.warning(
            "memory.ratelimit: counter unavailable for user %s; allowing write",
            getattr(ctx, "user_id", None),
            exc_info=True,
        )
        return 0

    if count > limit:
        raise MemoryWriteRateLimitExceeded(limit=limit, retry_after=seconds_until_reset)
    return count


__all__ = [
    "RATE_LIMIT_ENV_VAR",
    "DEFAULT_MEMORY_WRITE_RATE_LIMIT_PER_HOUR",
    "WINDOW_SECONDS",
    "MemoryWriteRateLimitExceeded",
    "resolve_write_rate_limit",
    "check_write_rate_limit",
]
