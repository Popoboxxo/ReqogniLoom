"""RES-01 residual (AUD-2026-09-030 / N3) — bounded Redis cache DNS.

The prior RES-01 commit added ``socket_connect_timeout``/``socket_timeout`` to
``CACHES["default"]["OPTIONS"]``, but those bound the TCP handshake, not the
``socket.getaddrinfo`` call redis-py makes first. When Redis is stopped in the
Compose stack its service name stops resolving and every cache op blocked in the
resolver (~3.85 s each, ~6 ops) — the rate-limit fail-open branch never received
the exception it waits for (REVIEW_LIVE_CRITICALS.md, AUD-030/N3).

These tests pin the fix from ``reqogniloom.bounded_dns``:

* a blocking ``getaddrinfo`` is abandoned after the configured budget and raises
  (so the documented fail-open path runs);
* that failure opens a short cooldown, so a request's *remaining* cache ops fail
  fast instead of each paying the budget again;
* the production ``CACHES`` actually installs the bounded pool;
* end to end, ``check_mcp_ip_rate_limit`` (the MCP acceptance path) returns its
  fail-open result well inside the 8 s budget while DNS is hanging.

The first two are pure unit tests (no DB). The last one uses a real
``django.core.cache.backends.redis.RedisCache`` pointed at an unresolvable host
with ``getaddrinfo`` stubbed to hang, so it exercises Django -> redis-py -> our
connection class without needing a live Redis.
"""
from __future__ import annotations

import socket
import time
from typing import Callable, Optional

import pytest
import redis
from django.test import RequestFactory, override_settings

from reqogniloom import bounded_dns

#: Test-side budget/cooldown, deliberately below the shipped 1.5s/2.0s defaults
#: so a regression fails fast instead of adding 8s to every run.
_TEST_BUDGET = 0.3


@pytest.fixture(autouse=True)
def _reset_resolver_state():
    bounded_dns.reset_resolver_state()
    yield
    bounded_dns.reset_resolver_state()


def _blocking_getaddrinfo(
    sleep_seconds: float,
    calls: Optional[list] = None,
    block_host: Optional[str] = None,
) -> Callable[..., list]:
    """``socket.getaddrinfo`` replacement that blocks before resolving.

    ``block_host`` restricts the stall to one hostname, so a test can verify
    that the cooldown is keyed per target without also stalling an unrelated
    (e.g. ``localhost``) lookup.
    """
    real = socket.getaddrinfo

    def _fake(host, port, *args, **kwargs):
        if block_host is not None and host != block_host:
            return real(host, port, *args, **kwargs)
        if calls is not None:
            calls.append((host, port))
        time.sleep(sleep_seconds)
        return real(host, port, *args, **kwargs)

    return _fake


# ---------------------------------------------------------------------------
# Resolver unit contract
# ---------------------------------------------------------------------------


def test_blocking_getaddrinfo_is_abandoned_within_budget(monkeypatch):
    """A DNS resolution that would hang is cut off at the budget, not awaited."""
    monkeypatch.setattr(socket, "getaddrinfo", _blocking_getaddrinfo(2.0))

    start = time.monotonic()
    with pytest.raises(OSError):
        bounded_dns.resolve_host_bounded(
            "cache-dns-budget.invalid", 6379, timeout=_TEST_BUDGET, cooldown=1.0
        )
    elapsed = time.monotonic() - start

    # Raising is what redis-py turns into ConnectionError and the throttle
    # catches. The load-bearing part: it happens at the budget, not after the
    # 2.0s the (stubbed) resolver wanted.
    assert elapsed < 1.0, f"resolution blocked for {elapsed:.2f}s despite budget"


def test_failure_opens_fail_fast_cooldown(monkeypatch):
    """After one failed lookup, retries raise immediately — no second wait.

    This is what bounds the *total* time of a request, which touches several
    cache keys: without the cooldown each would pay the budget again.
    """
    calls: list = []
    monkeypatch.setattr(socket, "getaddrinfo", _blocking_getaddrinfo(2.0, calls))

    with pytest.raises(OSError):
        bounded_dns.resolve_host_bounded(
            "cache-dns-cooldown.invalid", 6379, timeout=_TEST_BUDGET, cooldown=5.0
        )
    assert calls, "the first attempt must have reached getaddrinfo"
    calls_after_first = len(calls)

    start = time.monotonic()
    with pytest.raises(OSError):
        bounded_dns.resolve_host_bounded(
            "cache-dns-cooldown.invalid", 6379, timeout=_TEST_BUDGET, cooldown=5.0
        )
    elapsed = time.monotonic() - start

    assert elapsed < 0.1, f"cooldown retry took {elapsed:.2f}s"
    assert len(calls) == calls_after_first, "no new resolver attempt during cooldown"


def test_cooldown_is_per_host(monkeypatch):
    """A down host must not poison an unrelated Redis target."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _blocking_getaddrinfo(2.0, block_host="cache-dns-a.invalid"),
    )

    with pytest.raises(OSError):
        bounded_dns.resolve_host_bounded(
            "cache-dns-a.invalid", 6379, timeout=_TEST_BUDGET, cooldown=5.0
        )

    # Different host: real resolution (localhost) must not be short-circuited.
    infos = bounded_dns.resolve_host_bounded(
        "localhost", 6379, timeout=1.0, cooldown=5.0
    )
    assert infos


# ---------------------------------------------------------------------------
# Settings contract — the production cache must install the bounded pool
# ---------------------------------------------------------------------------


def test_production_cache_installs_bounded_dns_pool():
    import reqogniloom.settings as base_settings

    options = base_settings.CACHES["default"]["OPTIONS"]
    assert options.get("pool_class") == (
        "reqogniloom.bounded_dns.BoundedRedisConnectionPool"
    )


def test_dns_budget_settings_are_conservative():
    import reqogniloom.settings as base_settings

    assert 0 < base_settings.CACHE_DNS_TIMEOUT <= 5
    assert 0 < base_settings.CACHE_UNHEALTHY_COOLDOWN <= 10
    # TOTAL budget must leave room inside the 8s MCP acceptance.
    assert (
        base_settings.CACHE_DNS_TIMEOUT + base_settings.CACHE_UNHEALTHY_COOLDOWN
    ) < 8


# ---------------------------------------------------------------------------
# rediss:// — TLS deployments must get the bounded DNS path, SNI intact
# ---------------------------------------------------------------------------


def test_from_url_installs_bounded_connection_for_redis_and_rediss():
    """Both TCP schemes must resolve through the bounded resolver.

    The prior fix only wired ``redis://``; a ``rediss://`` deployment silently
    kept redis-py's unbounded ``SSLConnection`` (AUD-030 residual).
    """
    plain = bounded_dns.BoundedRedisConnectionPool.from_url(
        "redis://cache-scheme.invalid:6379/1"
    )
    tls = bounded_dns.BoundedRedisConnectionPool.from_url(
        "rediss://cache-scheme.invalid:6379/1"
    )

    assert plain.connection_class is bounded_dns.BoundedDnsConnection
    assert tls.connection_class is bounded_dns.BoundedSslDnsConnection


def test_from_url_leaves_unix_socket_untouched():
    """``unix://`` involves no DNS, so it must not be replaced."""
    pool = bounded_dns.BoundedRedisConnectionPool.from_url("unix:///tmp/redis.sock")
    assert pool.connection_class is not bounded_dns.BoundedDnsConnection
    assert pool.connection_class is not bounded_dns.BoundedSslDnsConnection


def test_ssl_connect_pins_address_for_tcp_but_keeps_sni_hostname(monkeypatch):
    """The numeric address is pinned for the raw connect only.

    During the TLS handshake ``self.host`` must be the original hostname so
    redis-py's ``server_hostname`` (SNI / certificate verification) is correct.
    """
    from redis.connection import Connection

    pinned_hosts: list = []
    wrapped_hosts: list = []
    dummy_sock = object()

    def fake_tcp_connect(self):
        pinned_hosts.append(self.host)
        return dummy_sock

    def fake_wrap(self, sock):
        wrapped_hosts.append(self.host)
        return sock

    monkeypatch.setattr(
        bounded_dns,
        "resolve_host_bounded",
        lambda host, port, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
        ],
    )
    monkeypatch.setattr(Connection, "_connect", fake_tcp_connect)
    monkeypatch.setattr(redis.SSLConnection, "_wrap_socket_with_ssl", fake_wrap)

    conn = bounded_dns.BoundedSslDnsConnection(host="cache-tls.invalid", port=6379)
    result = conn._connect()

    assert result is dummy_sock
    assert pinned_hosts == ["127.0.0.1"], "raw TCP connect must use the pinned address"
    assert wrapped_hosts == ["cache-tls.invalid"], "TLS wrap must see the hostname (SNI)"
    assert conn.host == "cache-tls.invalid", "hostname must be restored after connect"


# ---------------------------------------------------------------------------
# Read-stall breaker — a frozen-but-listening server must fail fast
# ---------------------------------------------------------------------------


def test_read_timeout_opens_fail_fast_cooldown(monkeypatch):
    """A read timeout on a command must trip the same cooldown as DNS failures.

    A frozen Redis that still accepts TCP connects never fails in ``_connect``;
    without a read-failure breaker every following cache op pays
    ``socket_timeout`` again (AUD-030 residual #2).
    """
    conn = bounded_dns.BoundedDnsConnection(host="cache-read-stall.invalid", port=6379)
    monkeypatch.setattr(socket, "getaddrinfo", _blocking_getaddrinfo(2.0))

    def raise_timeout(*args, **kwargs):
        raise TimeoutError("simulated frozen server")

    monkeypatch.setattr(conn._parser, "read_response", raise_timeout)

    with pytest.raises(redis.exceptions.TimeoutError):
        conn.read_response(disconnect_on_error=False)

    # The read failure must have opened the cooldown: the next resolution for
    # the same target fails immediately instead of paying the DNS budget again.
    start = time.monotonic()
    with pytest.raises(OSError):
        bounded_dns.resolve_host_bounded(
            "cache-read-stall.invalid", 6379, timeout=_TEST_BUDGET, cooldown=5.0
        )
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, "read stall did not trip the fail-fast cooldown"


# ---------------------------------------------------------------------------
# End to end — the MCP throttle fails open inside the budget
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://cache-dns-throttle.invalid:6379/1",
            "OPTIONS": {
                "socket_connect_timeout": 0.5,
                "socket_timeout": 0.5,
                "pool_class": "reqogniloom.bounded_dns.BoundedRedisConnectionPool",
            },
        }
    },
    CACHE_DNS_TIMEOUT=_TEST_BUDGET,
    CACHE_UNHEALTHY_COOLDOWN=3.0,
)
def test_mcp_throttle_fails_open_within_budget_on_dns_hang(monkeypatch):
    """With DNS hanging, the MCP IP throttle answers (fail-open) inside budget.

    ``None`` is the throttle's "allowed, not limited" result — the documented
    fail-open contract on a cache outage. Before the fix this path paid the raw
    resolver stall once per cache op (multi-second), which is exactly the AUD-030
    hang; the cooldown + budget now cap it.
    """
    from mcp_server.throttling import check_mcp_ip_rate_limit

    monkeypatch.setattr(socket, "getaddrinfo", _blocking_getaddrinfo(2.0))
    request = RequestFactory().post("/mcp/", REMOTE_ADDR="10.10.0.1")

    start = time.monotonic()
    result = check_mcp_ip_rate_limit(request)
    elapsed = time.monotonic() - start

    assert result is None, "cache outage must fail open (allow the request)"
    assert elapsed < 1.5, (
        f"MCP throttle took {elapsed:.2f}s with Redis DNS hanging "
        f"(budget {_TEST_BUDGET}s); must fail open well inside 8s"
    )


@pytest.mark.django_db
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "rediss://cache-tls-throttle.invalid:6379/1",
            "OPTIONS": {
                "socket_connect_timeout": 0.5,
                "socket_timeout": 0.5,
                "pool_class": "reqogniloom.bounded_dns.BoundedRedisConnectionPool",
            },
        }
    },
    CACHE_DNS_TIMEOUT=_TEST_BUDGET,
    CACHE_UNHEALTHY_COOLDOWN=3.0,
)
def test_mcp_throttle_fails_open_within_budget_on_rediss_dns_hang(monkeypatch):
    """A TLS (``rediss://``) cache outage must fail open inside the budget too.

    Before the fix ``rediss://`` kept redis-py's default ``SSLConnection``, so
    this path paid the raw resolver stall per cache op — the same AUD-030 hang,
    just on the TLS deployment.
    """
    from mcp_server.throttling import check_mcp_ip_rate_limit

    monkeypatch.setattr(socket, "getaddrinfo", _blocking_getaddrinfo(2.0))
    request = RequestFactory().post("/mcp/", REMOTE_ADDR="10.10.0.2")

    start = time.monotonic()
    result = check_mcp_ip_rate_limit(request)
    elapsed = time.monotonic() - start

    assert result is None, "cache outage must fail open (allow the request)"
    assert elapsed < 1.5, (
        f"MCP throttle took {elapsed:.2f}s with rediss DNS hanging "
        f"(budget {_TEST_BUDGET}s); must fail open well inside 8s"
    )
