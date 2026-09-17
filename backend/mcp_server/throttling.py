"""Rate limiting for the MCP transport endpoints (SYSTEMAUDIT-2026-08-27 finding A).

The views in :mod:`mcp_server.views` are plain Django ``View`` classes, not DRF
views, so ``REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]`` never applied to
``/mcp/*``: every MCP endpoint accepted an unbounded request rate. That left
three doors open — unbounded SSE session creation (each handshake allocates a
Redis binding plus a streaming connection), unbounded tool dispatch (LLM-backed
tools cost real money per call), and an unbounded number of credential
presentations against the handshake.

Rather than introduce a *second* rate-limiting mechanism, this module reuses the
one the project already runs: DRF's ``SimpleRateThrottle`` counting through
Django's default cache, which is Redis-backed (``settings.CACHES``, db 1). The
counters are therefore shared across processes and workers, they honour the same
``"<count>/<period>"`` rate syntax, an empty env value disables them, and
``override_settings`` reconfigures them in tests — exactly like
:mod:`rest_api.throttling`. ``SimpleRateThrottle`` only reads ``request.META``,
so it works unchanged on a plain ``HttpRequest``.

Two counters, mirroring the split :mod:`rest_api.throttling` settled on for
#269:

* :class:`McpApiKeyRateThrottle` — the primary per-credential budget, keyed on a
  digest of the presented API key (or, on the message endpoint, of the SSE
  session id that stands in for it). One noisy client therefore cannot spend
  another client's budget.
* :class:`McpIpRateThrottle` — a deliberately much looser per-IP backstop that
  also covers requests carrying no credential at all, or a different one each
  time, which the per-credential counter cannot see.

  This is explicitly **not** sold as a brute-force defence: a ``reqlo_`` key is
  40 characters drawn from ``secrets.choice`` (``generate_api_key_plaintext``),
  so guessing one is infeasible at any rate a throttle could permit. Its job is
  to bound the *cost* of a flood. It is kept loose on purpose because DRF's
  ``NUM_PROXIES`` is unset project-wide: behind a reverse proxy that does not
  forward ``X-Forwarded-For``, every caller collapses into a single bucket, and
  a tight per-IP limit would then be a self-inflicted outage rather than a
  defence.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional

from django.http import HttpRequest, HttpResponse, JsonResponse

from mcp_server.protocol_handler import ERROR_CODES
from rest_api.throttling import DynamicRateThrottle

__all__ = [
    "McpApiKeyRateThrottle",
    "McpIpRateThrottle",
    "api_key_from_request",
    "check_mcp_rate_limit",
    "rate_limited_jsonrpc_response",
    "rate_limited_plain_response",
]

#: Error code surfaced to the client on refusal. Defined in
#: :mod:`mcp_server.protocol_handler` so the message stays in the one map that
#: is the single source of truth for MCP error wording.
RATE_LIMITED = "RATE_LIMITED"


def api_key_from_request(request: HttpRequest) -> str:
    """Return the API key presented in the request headers, or ``""``.

    Header-only, matching every other key-resolution path on this transport: a
    query-string or body key would leak the long-lived ``reqlo_*`` secret into
    proxy/access logs (REQ-018 / SYSTEM_AUDIT P-05).
    """
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.META.get("HTTP_X_API_KEY", "")


def _credential_digest(credential: str) -> str:
    """Stable, cache-key-safe digest of a caller credential.

    Hashed rather than embedded verbatim for the same reason
    ``rest_api.throttling._username_digest`` hashes the login name: the value is
    a secret (an API key, or a session id bound to one), it must stay inside the
    character and length limits of every cache backend, and a cache dump must
    not read like a credential list.
    """
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()[:32]


class McpApiKeyRateThrottle(DynamicRateThrottle):
    """Per-credential cap for the MCP transport endpoints.

    The credential is passed in explicitly instead of being read off the
    request, because the three MCP endpoints identify a caller differently: the
    HTTP transport and the SSE handshake carry the API key in a header, while
    ``/mcp/messages/`` carries only a ``session_id`` whose server-side binding
    *is* the credential (REQ-018 / SYSTEM_AUDIT P-02). Both are secrets that
    identify one client, which is all this counter needs.
    """

    scope = "mcp_key"

    def __init__(self, credential: str = "") -> None:
        super().__init__()
        self._credential = credential

    def get_cache_key(self, request: HttpRequest, view: Any = None) -> Optional[str]:
        """Bucket key for this credential, or ``None`` when there is none.

        ``None`` means "not applicable" to ``SimpleRateThrottle`` — an
        anonymous request is then bounded by :class:`McpIpRateThrottle` alone.
        """
        if not self._credential:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": _credential_digest(self._credential),
        }


class McpIpRateThrottle(DynamicRateThrottle):
    """Looser per-IP backstop for the MCP transport endpoints.

    Applies to every request, credentialed or not — see the module docstring for
    why it is intentionally the weaker of the two counters.
    """

    scope = "mcp_ip"

    def get_cache_key(self, request: HttpRequest, view: Any = None) -> Optional[str]:
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


def check_mcp_rate_limit(
    request: HttpRequest, *, credential: Optional[str] = None
) -> Optional[float]:
    """Charge one MCP request against its buckets; return retry-after on refusal.

    Args:
        request: The inbound request (only ``META`` is read).
        credential: Explicit caller credential. ``None`` (the default) resolves
            the API key from the request headers; pass a session id on the
            message endpoint, or ``""`` to count against the per-IP bucket only.

    Returns:
        ``None`` when the request is within every limit — it has then been
        counted. Otherwise the number of seconds the caller should wait, never
        below ``1.0`` so a client can never read ``Retry-After: 0`` as
        "retry immediately".

    The per-credential bucket is checked first: a caller who has already blown
    their own budget is rejected without also consuming the shared per-IP one,
    which would otherwise let a single misbehaving client push everyone behind
    the same proxy towards the backstop limit.
    """
    if credential is None:
        credential = api_key_from_request(request)

    for throttle in (McpApiKeyRateThrottle(credential or ""), McpIpRateThrottle()):
        if not throttle.allow_request(request, None):
            # SimpleRateThrottle.wait() returns None when the history has
            # already overshot the bucket; treat that as "wait the minimum"
            # rather than omitting the hint entirely.
            return max(float(throttle.wait() or 1.0), 1.0)
    return None


def _retry_after_seconds(retry_after: float) -> int:
    """Whole seconds for the ``Retry-After`` header (RFC 9110 §10.2.3)."""
    return max(int(math.ceil(retry_after)), 1)


def rate_limited_jsonrpc_response(
    retry_after: float, *, request_id: Any = None
) -> HttpResponse:
    """429 in the transport-level JSON-RPC error envelope.

    Uses the string ``error_code`` shape (REQ-047) that the other transport-level
    rejections in :mod:`mcp_server.views` emit — ``McpMessagesView._error_response``
    and ``McpHttpTransportView``'s INTERNAL_ERROR body — rather than the numeric
    ``code`` shape ``ErrorFormatter`` produces for handler-level errors. This
    rejection happens before any handler runs, so it belongs to the former group.
    """
    seconds = _retry_after_seconds(retry_after)
    body = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "error_code": RATE_LIMITED,
            "message": ERROR_CODES[RATE_LIMITED],
            "data": {"retry_after_seconds": seconds, "retryable": True},
        },
    }
    response = HttpResponse(
        json.dumps(body),
        content_type="application/json",
        status=429,
    )
    response["Retry-After"] = str(seconds)
    return response


def rate_limited_plain_response(retry_after: float) -> JsonResponse:
    """429 in the SSE handshake's own ``{"error": "..."}`` error shape.

    ``GET /mcp/sse/`` is not a JSON-RPC call, and its existing 401/500 replies
    use this flat shape; answering a 429 in a third shape would only give
    clients one more thing to branch on.
    """
    seconds = _retry_after_seconds(retry_after)
    response = JsonResponse({"error": ERROR_CODES[RATE_LIMITED]}, status=429)
    response["Retry-After"] = str(seconds)
    return response
