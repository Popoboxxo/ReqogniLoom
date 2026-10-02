"""Bounded DNS resolution for the Redis cache client (RES-01 / finding AUD-2026-09-030).

Why this module exists
----------------------
``socket_connect_timeout`` (set in ``settings.CACHES``) bounds the TCP
handshake, but **not** the name resolution that precedes it:
``redis-py``'s ``Connection._connect`` calls ``socket.getaddrinfo(host, ...)``
first, and that call is a blocking C function with no timeout parameter. When
Redis is stopped in the Compose stack its service name stops resolving, so each
cache access stalled in the resolver's own retry schedule (~3.85 s in the live
audit) *times* every cache op of the request (~6) — ~23 s of blocked request
thread (REVIEW_LIVE_CRITICALS.md, AUD-030/N3). The documented fail-open branch
in ``rest_api.throttling`` only runs once an exception is raised, which is far
too late.

What this module does
---------------------
* :class:`_BoundedResolver` runs ``socket.getaddrinfo`` in a daemon thread and
  waits at most ``CACHE_DNS_TIMEOUT`` seconds. On expiry it raises
  ``socket.gaierror``, which redis-py wraps as ``redis.exceptions.ConnectionError``
  and the throttles' ``except Exception`` (fail-open) path handles.
* A failed resolution puts the target into a short cooldown
  (``CACHE_UNHEALTHY_COOLDOWN``): every later attempt during that window raises
  immediately instead of each paying the budget again. This, not the timeout
  alone, is what keeps one request's **total** cache time bounded even though it
  touches several keys (throttle history + runtime overrides).
* :class:`BoundedDnsConnection` uses the resolver and then lets redis-py do its
  normal socket setup, so no connection logic is duplicated. The resolved
  numeric address is pinned onto the connection only for the duration of the
  raw connect; the original hostname is restored so logging/reconnect and TLS
  SNI keep working.
* :class:`BoundedRedisConnectionPool` injects that connection class through the
  ``pool_class`` key Django's ``RedisCache`` forwards to redis-py. Adding one
  OPTIONS entry in ``settings.CACHES`` therefore covers *every* cache consumer
  centrally — the rate-limit throttles, ``admin_ops.rate_limits`` and
  ``mcp_server.throttling`` — rather than patching call sites.

Scope / known residual
----------------------
Only ``redis://`` (plain TCP) is intercepted. ``rediss://`` is left on
redis-py's default connection class on purpose: pinning the numeric address
would change the ``server_hostname`` used for the TLS handshake and break
certificate hostname verification. The shipped Compose stack uses ``redis://``
(``settings.REDIS_URL``); a TLS deployment keeps the pre-RES-01 behaviour and
would need a dedicated SNI-preserving variant. Read stalls from a *frozen*
(frozen process, port still listening) server are bounded per op by the existing
``socket_timeout``; this module does not add a post-connect breaker.

Budget reasoning (acceptance: MCP answers within 8 s while Redis is stopped)
---------------------------------------------------------------------------
The live failure is DNS (``Name or service not known``), so the first cache op
costs at most ``CACHE_DNS_TIMEOUT`` (default 1.5 s) and the remaining ops fail
fast through the cooldown. Measured against the live stack the endpoint answers
in well under 2 s, with headroom to the 8 s acceptance. Raising either value
above the acceptance is an explicit operator choice, not a default.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Any, Callable, Optional

import redis

logger = logging.getLogger(__name__)

__all__ = [
    "BoundedDnsConnection",
    "BoundedRedisConnectionPool",
    "reset_resolver_state",
    "resolve_host_bounded",
]

#: Conservative defaults; overridable via settings/env (see ``settings.CACHES``).
_DEFAULT_DNS_TIMEOUT = 1.5
_DEFAULT_UNHEALTHY_COOLDOWN = 2.0

_THREAD_NAME = "reqlo-cache-dns"


class _BoundedResolver:
    """Thread-bounded ``getaddrinfo`` with a short per-target failure cooldown.

    ``clock`` is injectable so tests can advance time without sleeping.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._down_until: dict[tuple[str, int], float] = {}

    def getaddrinfo(
        self,
        host: str,
        port: int,
        family: int,
        socktype: int,
        *,
        timeout: float,
        cooldown: float,
    ) -> list[tuple]:
        """Resolve *host* within *timeout* seconds, honouring the cooldown."""
        key = (str(host), int(port))
        with self._lock:
            down_until = self._down_until.get(key)
            if down_until is not None and self._clock() < down_until:
                raise socket.gaierror(
                    socket.EAI_AGAIN,
                    f"DNS resolution for Redis host {host!r} skipped: a previous "
                    f"lookup failed less than {cooldown:.1f}s ago (fail-open).",
                )
        try:
            infos = _run_bounded_getaddrinfo(host, port, family, socktype, timeout)
        except OSError:
            self.mark_down(host, port, cooldown=cooldown)
            raise
        with self._lock:
            self._down_until.pop(key, None)
        return infos

    def mark_down(self, host: str, port: int, *, cooldown: float) -> None:
        """Treat *host* as unhealthy for *cooldown* seconds.

        Called on a DNS timeout and on a failed TCP connect, so a blackholed
        connect cannot make every cache op pay ``socket_connect_timeout`` again.
        """
        with self._lock:
            self._down_until[(str(host), int(port))] = self._clock() + cooldown

    def reset(self) -> None:
        """Clear all cooldown state (tests / manual recovery)."""
        with self._lock:
            self._down_until.clear()


_RESOLVER = _BoundedResolver()


def _run_bounded_getaddrinfo(
    host: str,
    port: int,
    family: int,
    socktype: int,
    timeout: float,
) -> list[tuple]:
    """Run ``socket.getaddrinfo`` in a daemon thread, bounded by *timeout*.

    The worker is a daemon and is not joined: on timeout it is abandoned (it
    cannot be cancelled) and exits when the OS resolver gives up. The cooldown
    in :class:`_BoundedResolver` keeps a stuck resolver from being re-spawned on
    every subsequent cache op during the outage.
    """
    if timeout <= 0:
        timeout = _DEFAULT_DNS_TIMEOUT

    holder: dict[str, Any] = {}
    done = threading.Event()

    def _worker() -> None:
        try:
            holder["infos"] = socket.getaddrinfo(host, port, family, socktype)
        except BaseException as exc:  # noqa: BLE001 - relayed to the caller below
            holder["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_worker, name=_THREAD_NAME, daemon=True).start()
    if not done.wait(timeout):
        raise socket.gaierror(
            socket.EAI_AGAIN,
            f"DNS resolution for Redis host {host!r}:{port} exceeded the "
            f"{timeout:.2f}s budget; taking the cache fail-open path.",
        )
    if "error" in holder:
        raise holder["error"]
    infos = holder.get("infos")
    if not infos:
        raise socket.gaierror(
            socket.EAI_NONAME,
            f"DNS resolution for Redis host {host!r} returned no addresses.",
        )
    return infos


def _dns_timeout() -> float:
    return _setting("CACHE_DNS_TIMEOUT", _DEFAULT_DNS_TIMEOUT)


def _unhealthy_cooldown() -> float:
    return _setting("CACHE_UNHEALTHY_COOLDOWN", _DEFAULT_UNHEALTHY_COOLDOWN)


def _setting(name: str, default: float) -> float:
    """Read *name* lazily so importing this module never needs Django settings."""
    from django.conf import settings

    value = getattr(settings, name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_host_bounded(
    host: str,
    port: int,
    *,
    family: int = 0,
    socktype: int = socket.SOCK_STREAM,
    timeout: Optional[float] = None,
    cooldown: Optional[float] = None,
) -> list[tuple]:
    """Resolve *host* within a bounded budget; raise ``OSError`` on failure.

    Public entry point for the connection class and for tests. A negative
    cooldown window after a failure is intentional; see the module docstring.
    """
    return _RESOLVER.getaddrinfo(
        host,
        port,
        family,
        socktype,
        timeout=_dns_timeout() if timeout is None else timeout,
        cooldown=_unhealthy_cooldown() if cooldown is None else cooldown,
    )


def reset_resolver_state() -> None:
    """Clear the resolver cooldown state (used by tests and manual recovery)."""
    _RESOLVER.reset()


class _BoundedDnsMixin:
    """Mixin that replaces redis-py's unbounded ``getaddrinfo`` with a bounded one."""

    def _connect(self):  # type: ignore[override]
        original_host = self.host
        infos = resolve_host_bounded(
            original_host,
            self.port,
            family=getattr(self, "socket_type", 0),
            socktype=socket.SOCK_STREAM,
        )
        address = infos[0][4][0]
        try:
            # Pin the numeric address for the raw connect; redis-py's
            # ``_connect`` would otherwise resolve the hostname again (unbounded).
            self.host = address
            return super()._connect()
        except OSError:
            # A failed TCP connect (refused/blackholed) trips the same cooldown
            # as a DNS failure, so it is not re-paid by every following op.
            _RESOLVER.mark_down(
                original_host, self.port, cooldown=_unhealthy_cooldown()
            )
            raise
        finally:
            # Preserve the hostname for logging, reconnect and TLS SNI.
            self.host = original_host


class BoundedDnsConnection(_BoundedDnsMixin, redis.Connection):
    """Plain TCP connection whose connect-time DNS lookup is wall-clock bounded."""


class BoundedRedisConnectionPool(redis.ConnectionPool):
    """Connection pool that installs :class:`BoundedDnsConnection`.

    Referenced by dotted path from ``settings.CACHES['default']['OPTIONS']
    ['pool_class']`` — Django's ``RedisCache`` resolves it lazily, so importing
    redis does not happen at settings-import time. ``unix://`` URLs are left
    untouched (no DNS involved).
    """

    @classmethod
    def from_url(cls, url: str, **kwargs: Any):
        scheme = str(url).split("://", 1)[0].lower()
        if scheme == "redis" and "connection_class" not in kwargs:
            kwargs["connection_class"] = BoundedDnsConnection
        # ``rediss://`` is deliberately not intercepted: see the module docstring
        # on TLS SNI / hostname verification.
        return super().from_url(url, **kwargs)
