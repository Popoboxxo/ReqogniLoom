"""SSRF guard for admin-configurable outbound LLM endpoints (SA-33).

SYSTEMAUDIT-2026-08-27 §4.6 F9: ``LlmSettings.base_url`` is admin-gated and
``URLField``-validated, but nothing stopped it from pointing at an internal
address. Because the backend then issues *server-side* requests to that URL
(``llm_adapter.providers``), a hostile or compromised admin account could turn
the LLM adapter into a proxy for the private network — cloud metadata
(``169.254.169.254``), the Postgres/Redis containers, or anything else reachable
from the app but not from the internet. That is the classic SSRF shape.

This module is the single place that answers "may the server be told to talk to
this URL?".

Policy
------
* Only ``http`` / ``https``.
* The host must resolve **exclusively** to public unicast addresses. A hostname
  is resolved first and *every* returned address is checked, so a DNS name that
  points at ``127.0.0.1`` is rejected just like the literal.
* Private / loopback / link-local / reserved / multicast / unspecified ranges
  are refused, in both IPv4 and IPv6, including IPv4-mapped IPv6 forms
  (``::ffff:10.0.0.1``) which ``ipaddress`` would otherwise classify as global.

Configuration
-------------
``LLM_ALLOW_PRIVATE_BASE_URL`` (bool) lifts the private-range restriction. It
defaults to **True outside production and False in production**
(``reqogniloom.settings``). The reason is that a self-hosted Ollama at
``http://ollama:11434`` or ``http://localhost:11434`` is a first-class supported
configuration and by definition lives on a private address — defaulting to deny
everywhere would break the documented local setup, while defaulting to allow
everywhere would not fix the finding. Operators who run Ollama in production set
the flag explicitly and thereby acknowledge the trade-off.

``LLM_BASE_URL_ALLOWED_HOSTS`` (comma-separated) is the narrower alternative:
it permits specific hosts on private addresses while everything else stays
blocked. Prefer it over the blanket flag.

KNOWN RESIDUAL RISK — DNS rebinding
-----------------------------------
The check resolves the hostname at *validation* time; the provider resolves it
again at *request* time. A DNS name whose record flips between the two
(TTL 0 pointing first at a public IP, then at ``169.254.169.254``) passes here
and still reaches the internal address. Closing that hole requires pinning the
validated IP into the HTTP connection itself — a custom
``socket``/``urllib3`` connection factory threaded through the Anthropic,
OpenAI and Ollama SDK clients, which is a materially larger change than this
finding warrants. Given the endpoint is admin-only and already audit-logged, the
gap is documented rather than closed. Anyone hardening this further should start
at :func:`resolved_addresses` and pin what it returns.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Iterable
from urllib.parse import urlsplit

from django.conf import settings

# Schemes the LLM adapter can actually speak. Anything else (file://, gopher://,
# ftp://) has no legitimate use here and is a known SSRF pivot.
ALLOWED_SCHEMES = ("http", "https")


class UnsafeOutboundUrlError(ValueError):
    """Raised when a configured outbound URL is not safe to request server-side.

    Subclasses ``ValueError`` so callers that already funnel configuration
    errors through ``ValueError`` keep working unchanged.
    """


def _normalise(address: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    """Unwrap IPv4-mapped/compatible IPv6 addresses to their IPv4 form.

    ``ipaddress.IPv6Address("::ffff:10.0.0.1").is_private`` is ``False`` — the
    private-range check has to run against the embedded IPv4 address or the
    mapped form becomes a trivial bypass.
    """
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped or getattr(address, "sixtofour", None)
        if mapped is not None:
            return mapped
    return address


def is_public_address(address: ipaddress._BaseAddress) -> bool:
    """Return whether *address* is a routable public unicast address."""
    addr = _normalise(address)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def resolved_addresses(host: str) -> list[ipaddress._BaseAddress]:
    """Return every IP *host* resolves to (the literal itself if it is an IP).

    Args:
        host: Hostname or IP literal taken from the URL's netloc.

    Returns:
        All distinct addresses the name resolves to. Every one of them must
        pass :func:`is_public_address` — checking only the first would let a
        multi-record name smuggle an internal address through.

    Raises:
        UnsafeOutboundUrlError: If the name does not resolve. An unresolvable
            host is rejected rather than allowed: it cannot be proven safe.
    """
    try:
        return [ipaddress.ip_address(host.strip("[]"))]
    except ValueError:
        pass  # not a literal — fall through to DNS

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeOutboundUrlError(
            f"Host '{host}' could not be resolved, so it cannot be verified "
            f"as a public endpoint."
        ) from exc

    seen: dict[str, ipaddress._BaseAddress] = {}
    for info in infos:
        raw = info[4][0]
        try:
            seen[raw] = ipaddress.ip_address(raw)
        except ValueError:  # pragma: no cover - getaddrinfo returned garbage
            continue
    return list(seen.values())


def _allowed_hosts() -> frozenset[str]:
    """Return the configured private-address host allowlist, lower-cased."""
    raw = getattr(settings, "LLM_BASE_URL_ALLOWED_HOSTS", "") or ""
    if isinstance(raw, str):
        entries: Iterable[str] = raw.split(",")
    else:
        entries = raw
    return frozenset(e.strip().lower() for e in entries if e and e.strip())


def validate_outbound_url(raw_url: str) -> None:
    """Raise unless *raw_url* is safe for the server to request (SA-33).

    An empty/blank value is accepted — it means "no override", not "an unsafe
    URL", and the provider then falls back to its own default endpoint.

    Args:
        raw_url: The candidate ``base_url``.

    Raises:
        UnsafeOutboundUrlError: On a non-HTTP(S) scheme, a missing host, an
            unresolvable host, or any address in a private/loopback/link-local/
            reserved/multicast range while private targets are not permitted.
    """
    if not raw_url or not raw_url.strip():
        return

    parts = urlsplit(raw_url.strip())
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeOutboundUrlError(
            f"Only {'/'.join(ALLOWED_SCHEMES)} URLs are allowed, got "
            f"'{parts.scheme or 'no scheme'}'."
        )

    host = parts.hostname
    if not host:
        raise UnsafeOutboundUrlError("The URL must contain a host.")

    if host.lower() in _allowed_hosts():
        return

    if getattr(settings, "LLM_ALLOW_PRIVATE_BASE_URL", False):
        return

    offending = [
        str(address)
        for address in resolved_addresses(host)
        if not is_public_address(address)
    ]
    if offending:
        raise UnsafeOutboundUrlError(
            f"Host '{host}' resolves to a non-public address "
            f"({', '.join(sorted(offending))}). Pointing the LLM adapter at an "
            f"internal address would let it be used to reach the private "
            f"network (SSRF). To run a self-hosted model on a private address, "
            f"add the host to LLM_BASE_URL_ALLOWED_HOSTS or set "
            f"LLM_ALLOW_PRIVATE_BASE_URL=True."
        )


__all__ = [
    "ALLOWED_SCHEMES",
    "UnsafeOutboundUrlError",
    "is_public_address",
    "resolved_addresses",
    "validate_outbound_url",
]
