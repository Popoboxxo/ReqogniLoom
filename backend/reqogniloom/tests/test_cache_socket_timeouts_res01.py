"""RES-01 (audit finding 030) — bounded Redis cache socket timeouts.

The production ``CACHES["default"]`` backend is Django's built-in Redis cache
(``settings.py``). Before RES-01 it set no ``OPTIONS`` at all, so the
underlying ``redis-py`` client fell back to the operating-system TCP timeouts:
a connect to an unreachable host or a read from an unresponsive server could
block for minutes. Every cache consumer on the request path — most visibly the
rate-limiting ``DynamicRateThrottle``, whose ``allow_request`` is documented to
fail *open* on a cache outage — then hung instead of reaching its fail-open
branch.

These tests pin the *settings contract* only: the two socket timeouts must be
set and must be conservative (positive, bounded). The behavioural proof that a
stopped/frozen Redis then answers within the timeout is the live check recorded
in the RES-01 report; a unit test cannot exercise a real socket hang.

``reqogniloom.settings_test`` overrides ``CACHES`` to ``LocMemCache`` for the
suite, so the assertions read the base module's value directly — the test
settings module only rebinds its own ``CACHES`` name and leaves
``reqogniloom.settings.CACHES`` untouched.
"""
from __future__ import annotations

import reqogniloom.settings as base_settings


def _default_cache_options() -> dict:
    caches = base_settings.CACHES
    assert "default" in caches, "production settings must configure a default cache"
    options = caches["default"].get("OPTIONS")
    assert options is not None, (
        "RES-01/030: CACHES['default'] must set OPTIONS with explicit Redis "
        "socket timeouts; without them a dead/unresponsive Redis can block a "
        "request for the OS TCP timeout instead of the throttle's fail-open path."
    )
    return options


def test_default_cache_is_redis_backed():
    """Guard the RES-01 assumption: the timeouts only matter on the Redis backend."""
    assert (
        base_settings.CACHES["default"]["BACKEND"]
        == "django.core.cache.backends.redis.RedisCache"
    )


def test_cache_sets_connect_and_command_socket_timeouts():
    """Both timeouts must be present, positive and conservative (RES-01/030).

    ``socket_connect_timeout`` bounds the TCP handshake to a host whose packets
    are silently dropped; ``socket_timeout`` bounds a *connected* server that
    stops answering (e.g. a frozen process). They cover different failure modes,
    so setting only one is not sufficient.
    """
    options = _default_cache_options()

    for key in ("socket_connect_timeout", "socket_timeout"):
        assert key in options, f"OPTIONS must set {key}"
        value = options[key]
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"{key} must be a number, got {type(value).__name__}"
        )
        assert value > 0, f"{key} must be > 0"
        # Conservative: well above any healthy sibling-container round trip, yet
        # far below the OS TCP timeout it replaces. A value of 0 (or "no
        # timeout") is exactly the unbounded-hang defect RES-01 fixes.
        assert value <= 30, f"{key}={value}s is not conservative enough"


def test_socket_timeouts_are_configurable_via_settings():
    """The defaults are mirrored by env-overridable module-level settings.

    RES-01's rollback story (``plan/RESILIENCE_HEALTH.md``) is "conservative
    default, overridable per env". These two names are what ``config(...)``
    populates, so a deployment can tune them without editing code.
    """
    options = _default_cache_options()
    assert options["socket_connect_timeout"] == base_settings.CACHE_SOCKET_CONNECT_TIMEOUT
    assert options["socket_timeout"] == base_settings.CACHE_SOCKET_TIMEOUT
