"""Inbound Honcho webhooks -> memory cache invalidation (Plan A T-A4-7).

Why this exists
---------------
Every memory REST/MCP response carries the ``backend``/``degraded`` envelope, and
:mod:`memory.health` caches the four probes that build it (health, digest, ask,
derivation status) for :data:`~memory.health.HEALTH_CACHE_TTL_SECONDS`. That
staleness window is the honest trade-off — until the engine itself says "state
changed *now*". Honcho can say that: it ``POST``\\ s ``{type, data, timestamp}``
to every registered webhook URL (``queue.empty`` once the deriver drained its
queue, ``test.event`` for the registration smoke test). This module authenticates
that delivery; the view in :mod:`memory.memory_rest` turns a valid one into a
``204`` after dropping the caches (``deploy/README.md``, "SDK vs HTTP: the
v3.3.0 capability spike", documents the wire contract).

Security design — the reason this is a module and not four lines in the view
----------------------------------------------------------------------------
* **The signature is the credential.** Honcho has no ReqogniLoom JWT, so the
  receiver runs with ``authentication_classes = []`` and the only statement that
  must hold is "this body was produced by someone who knows
  ``HONCHO_WEBHOOK_SECRET``". The HMAC is therefore computed over the exact
  bytes that arrived (``request.body``) and **never** over a re-serialised parse
  of them: JSON has no canonical form, so parsing and re-encoding produces
  different bytes for the same document, and the check would degrade into "some
  semantically equal body" — which is not a signature.
* **Constant time.** :func:`hmac.compare_digest`, never ``==``. A byte-wise
  early-exit comparison leaks the length of the matching prefix, which is enough
  to forge a digest one byte at a time.
* **Never compare ``str`` to ``str``.** ``hmac.compare_digest`` raises
  ``TypeError`` on a non-ASCII ``str``, so a header containing e.g. ``ä`` would
  become an unhandled 500 (an exception oracle, and a 500 where a 401 belongs).
  Both sides are encoded to ``bytes`` first; a length mismatch just returns
  ``False``.
* **No secret, no receiver.** Without ``HONCHO_WEBHOOK_SECRET`` there is nothing
  to verify against, so the endpoint answers ``503`` rather than accepting
  unsigned deliveries. The message is the constant ``"webhooks disabled"`` and
  deliberately says nothing about which variable is unset, which deployment this
  is, or what would enable it.
* **Nothing about the request is echoed or logged.** The body carries memory
  content, so it is never parsed, never logged and never returned. A rejected
  delivery logs one WARNING carrying the peer address only — enough to notice
  forgery attempts, not enough to leak the payload or the secret.
* **Bounded, explicit body size.** :func:`body_size_problem` rejects an oversized
  or length-less POST *before* a byte is read (``413``/``400``), instead of
  relying on Django turning an excess into a 500. See that function for why the
  ``DATA_UPLOAD_MAX_MEMORY_SIZE`` argument alone is not a control.

Replay — accepted risk, and the bound on its cost
-------------------------------------------------
The signature covers the body only: there is **no timestamp or nonce in the
signed material**, so a captured delivery (``X-Honcho-Signature`` included) can be
replayed verbatim and will verify again, for as long as the shared secret lives.
That is accepted here because the *effect* of a replay is idempotent and
non-enumerating — one atomic drop of four deployment-global cache keys — and
because the only party who can observe a delivery is the receiver itself (or a
TLS-terminating proxy in front of it; the documented deployment is HTTPS). What a
replay *could* otherwise do is keep the cache permanently cold by re-dropping it
on every request, so :func:`invalidate_memory_caches` coalesces: at most one drop
per :data:`INVALIDATE_COALESCE_SECONDS`, which bounds the damage to "the cache
may be up to one coalescing window colder than the last legitimate event"
instead of "an attacker controls cache availability". Enforcing a timestamp or a
nonce would be required as soon as a delivery has a side effect that is not
idempotent (a write, a notification, a billable call), or once Honcho puts such a
value in the signed payload; until then it would buy a clock-skew failure mode
and a replay-cache to protect an operation that only costs four ``DEL``\\ s.

Wire format — accepted as-is
----------------------------
``X-Honcho-Signature`` is a **bare** lower-case hex SHA-256 digest (64 chars, no
``sha256=`` prefix), matched case-insensitively. That is what the pinned Honcho
server emits; a prefixed scheme (the ``sha256=<hex>`` convention of GitHub
webhooks) is deliberately *not* accepted, because accepting both would double the
accepted-header space for no security gain. The header is the only signature
location; there is no ``X-Honcho-Timestamp`` counterpart to cross-check.

Secret vs. the server side
--------------------------
``HONCHO_WEBHOOK_SECRET`` (this side, the HMAC key) is **not**
``WEBHOOK_SECRET`` (Honcho's own server-side variable, which *signs* the
delivery). Both must hold the same value for a delivery to verify; neither is
ever written to the database, a log line or a response. Delivery is best-effort
with a 30 s timeout and **no retries**, so a delivery this endpoint rejects is
simply gone — which is only ever a cache-staleness issue bounded by
:data:`~memory.health.HEALTH_CACHE_TTL_SECONDS`, never a correctness one.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

from django.core.cache import cache

from memory.health import invalidate_health_cache

logger = logging.getLogger(__name__)

#: Request header carrying the delivery signature (lower-case hex SHA-256).
SIGNATURE_HEADER = "X-Honcho-Signature"

#: Environment variable holding the shared HMAC key. Read on every delivery (a
#: plain ``os.environ`` lookup, same convention as the other ``HONCHO_*``
#: variables in :mod:`memory.honcho_backend`) so rotating the secret needs no
#: redeploy and no :class:`~django.conf.settings` reload.
SECRET_ENV_VAR = "HONCHO_WEBHOOK_SECRET"

#: Body returned with ``503`` when :data:`SECRET_ENV_VAR` is unset/empty.
#: Constant on purpose: it must not say *which* configuration is missing.
DISABLED_MESSAGE = "webhooks disabled"

#: Hard ceiling on the **declared** size of one delivery. Honcho's events are a
#: few hundred bytes; 256 KiB leaves room for a payload-bearing event without
#: giving an unauthenticated caller a memory amplifier.
MAX_BODY_BYTES = 256 * 1024

#: Shortest secret that is not warned about. 32 chars is the shortest value
#: ``secrets.token_urlsafe(24)`` produces and comfortably above offline-cracking
#: range for a random string; a shorter one is NOT rejected (an existing
#: deployment must keep working) but is reported once per process.
MIN_SECRET_LENGTH = 32

#: Coalescing window for :func:`invalidate_memory_caches`. Long enough that a
#: replay flood costs one drop per window instead of one per request, short
#: enough to stay far below :data:`memory.health.HEALTH_CACHE_TTL_SECONDS`.
INVALIDATE_COALESCE_SECONDS = 5

_INVALIDATE_COALESCE_KEY = "memory:webhooks:invalidate-coalesce"

#: Set once, so a short secret produces exactly one WARNING per process rather
#: than one per delivery (which would be a log-flooding vector of its own).
_short_secret_warned = False


def resolve_webhook_secret() -> str | None:
    """Return the shared HMAC key, or ``None`` when webhooks are disabled.

    An empty or whitespace-only variable is treated exactly like an unset one —
    copying ``.env.example`` (which ships the placeholder empty) must never
    enable a receiver whose key is ``""``, since ``HMAC("", body)`` is a
    perfectly predictable "signature".

    A configured but short secret (< :data:`MIN_SECRET_LENGTH` chars) is
    **accepted** — rejecting it would break a running deployment on upgrade —
    and logged once per process instead, because a guessable key silently turns
    the whole signature check into decoration. The value itself is never logged.
    """
    global _short_secret_warned

    raw = os.environ.get(SECRET_ENV_VAR, "")
    secret = (raw or "").strip()
    if secret and len(secret) < MIN_SECRET_LENGTH and not _short_secret_warned:
        _short_secret_warned = True
        logger.warning(
            "%s is shorter than %d characters; the webhook signature is only as "
            "strong as this key (value not logged). Generate one with: python -c "
            '"import secrets; print(secrets.token_urlsafe(48))"',
            SECRET_ENV_VAR,
            MIN_SECRET_LENGTH,
        )
    return secret or None


def body_size_problem(request: Any) -> str | None:
    """Classify a delivery's declared body size: ``None`` is acceptable.

    Returns ``"size"`` when the declared length exceeds :data:`MAX_BODY_BYTES`
    and ``"length"`` when a POST declares no usable ``Content-Length``.

    Why an explicit check and not just Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE``:
    that setting is enforced *while* the body is read, and only for a request
    whose size Django can see — i.e. it holds for the ASGI worker and for any
    request carrying a ``Content-Length``, and it surfaces as a bare
    ``RequestDataTooBig`` (an unhandled 500 on this route) at that point.
    Checking the declared length first turns the same condition into a cheap,
    documented ``413`` before anything is buffered, and makes the length-less
    case an explicit ``400`` instead of an unbounded read.
    """
    raw = request.META.get("CONTENT_LENGTH")
    if raw in (None, ""):
        return "length"
    try:
        declared = int(raw)
    except (TypeError, ValueError):
        return "length"
    if declared < 0:
        return "length"
    return "size" if declared > MAX_BODY_BYTES else None


def expected_signature(secret: str, raw_body: bytes) -> str:
    """Hex HMAC-SHA256 of *raw_body* under *secret* (what Honcho sends)."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_signature(*, secret: str, raw_body: bytes, provided: str | None) -> bool:
    """Whether *provided* is the signature of *raw_body* under *secret*.

    ``provided`` is the raw header value: a BARE hex digest, no ``sha256=``
    prefix (see the module docstring's "Wire format"). Hex is case-insensitive,
    so it is lower-cased before the comparison (this normalises the *hash*,
    never the body). A missing, empty or structurally different header is
    ``False`` — the caller maps that onto ``401``. Never raises: see the module
    docstring on why the comparison runs on ``bytes``.
    """
    if not provided:
        return False
    candidate = provided.strip().lower().encode("utf-8", errors="replace")
    return hmac.compare_digest(
        expected_signature(secret, raw_body).encode("ascii"), candidate
    )


def invalidate_memory_caches() -> bool:
    """Drop the cached memory-health envelope inputs (best-effort, coalesced).

    Delegates to :func:`memory.health.invalidate_health_cache`, which deletes
    the health probe **and** the three capability probes as one set
    (``digest_available`` / ``ask_available`` / ``derivation_status``) — a torn
    envelope would otherwise report a fresh health result next to a stale digest
    capability. This is that helper's first production caller; the set it drops
    is exactly the "Digest- und Health-Cache" of the T-A4-7 contract (the digest
    *text* is not cached anywhere in this app, it is answered by the engine on
    every read).

    **Coalesced** (see the module docstring on replay): at most one drop per
    :data:`INVALIDATE_COALESCE_SECONDS`, so a replayed delivery cannot hold the
    cache permanently cold. Returns whether this call actually dropped the set —
    ``False`` means "another delivery inside the window already did".

    Never raises: the delivery is fire-and-forget, so a cache outage must not
    turn a signed webhook into a 5xx that Honcho would (in any case) not retry.
    An unavailable cache cannot coalesce, so the failure mode is the old
    behaviour (drop anyway) rather than skipping the invalidation.
    """
    try:
        if not cache.add(_INVALIDATE_COALESCE_KEY, "1", INVALIDATE_COALESCE_SECONDS):
            return False
    except Exception:  # noqa: BLE001 - an unavailable cache must not fail the delivery
        logger.debug("webhook cache coalescing unavailable; invalidating anyway")
    invalidate_health_cache()
    return True


def log_rejected_delivery(peer: str | None, *, reason: str) -> None:
    """Log one rejected delivery without the body, the secret or the signature.

    ``peer`` is the transport address (``REMOTE_ADDR``), the only request
    attribute that is safe to record: it is not attacker-controlled content and
    it is what makes a forgery attempt traceable. ``reason`` is a constant from
    this module, never interpolated input.
    """
    logger.warning(
        "honcho webhook rejected (%s) from %s", reason, peer or "unknown peer"
    )


__all__ = [
    "DISABLED_MESSAGE",
    "INVALIDATE_COALESCE_SECONDS",
    "MAX_BODY_BYTES",
    "MIN_SECRET_LENGTH",
    "SECRET_ENV_VAR",
    "SIGNATURE_HEADER",
    "body_size_problem",
    "expected_signature",
    "invalidate_memory_caches",
    "log_rejected_delivery",
    "resolve_webhook_secret",
    "verify_signature",
]
