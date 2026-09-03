"""
COMP-MC-001 McpServer — Django HTTP transport view.

leaf_id : COMP-MC-001
req_id  : REQ-L2-MC-005 (HTTP transport), REQ-L2-MC-006 (API-key auth)

Provides the Django view that bridges incoming HTTP requests to the
ProtocolHandler / ToolRegistry pipeline. Supports both plain HTTP and
a simplified SSE transport (single-message response with event headers).

Interface: IF-MC-EXT-IN-001 (HTTP transport entry point)

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-001_ProtocolHandler/
      L3_COMP-MC-001_ProtocolHandler_Architecture.md
"""
from __future__ import annotations

import hmac
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.conf import settings
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.protocol_handler import ERROR_CODE_MAP, ERROR_CODES, ProtocolHandler
from mcp_server.throttling import (
    api_key_from_request,
    check_mcp_rate_limit,
    rate_limited_jsonrpc_response,
    rate_limited_plain_response,
)
from mcp_server.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# ErrorFormatter.format_error emits a numeric JSON-RPC "code" field, not a
# string "error_code" (REQ-047). Reverse the map to recover the string name
# for HTTP-status mapping below.
_NUMERIC_TO_ERROR_CODE: dict[int, str] = {v: k for k, v in ERROR_CODE_MAP.items()}


# ---------------------------------------------------------------------------
# CSRF-exemption invariant (SA-36, SYSTEMAUDIT-2026-08-27 §4.6 F15)
# ---------------------------------------------------------------------------
#
# The three transport views below are ``csrf_exempt``. That is correct *only*
# because this transport authenticates exclusively from request HEADERS
# (``Authorization: Bearer reqlo_…`` / ``X-API-Key``, see
# ``mcp_server.throttling.api_key_from_request`` and
# ``TransportAdapter.extract_api_key``). A browser does not attach headers to a
# cross-site request, so there is no ambient credential for an attacker to ride
# — which is the entire justification for skipping CSRF.
#
# The audit's point is that this was an *unguarded* invariant: nothing failed if
# someone later taught the MCP path to accept the ``reqogniloom_access`` cookie,
# and the CSRF hole would open silently. :func:`_reject_ambient_cookie_auth`
# turns the assumption into an enforced check.
_COOKIE_CREDENTIAL_NAMES = frozenset(
    {"reqogniloom_access", "reqogniloom_refresh", "sessionid"}
)


def _reject_ambient_cookie_auth(
    request: HttpRequest, *, explicit_credential: str | None = None
) -> HttpResponse | None:
    """Reject a request that could only be authenticated by an ambient cookie.

    Returns ``None`` (proceed) when either
      * the caller sent no cookie credential at all — nothing to ride on, or
      * the caller presented an explicit, non-ambient credential, which a
        cross-site attacker cannot supply: a header key needs a CORS preflight
        this server does not grant, and the ``session_id`` used by
        :class:`McpMessagesView` is an unguessable secret the browser never
        attaches on its own.

    Returns a 403 when a cookie credential is present but no explicit one is:
    exactly the shape of a browser-driven cross-site POST, and exactly the case
    the CSRF middleware would have caught if these views were not exempt.

    Legitimate MCP clients are unaffected — they always present an explicit
    credential and normally hold no cookies at all. A logged-in operator poking
    ``/mcp/`` from a browser tab without a key now gets a clear 403 instead of a
    confusing downstream auth error.

    Args:
        request: The inbound MCP transport request.
        explicit_credential: Credential resolved by the caller when it is not a
            header API key (``McpMessagesView`` authenticates by session id).
            ``None`` means "use the header key".

    Returns:
        ``None`` to proceed, or the rejection response to return immediately.
    """
    if not _COOKIE_CREDENTIAL_NAMES.intersection(request.COOKIES):
        return None
    credential = (
        explicit_credential
        if explicit_credential is not None
        else api_key_from_request(request)
    )
    if credential:
        return None

    logger.warning(
        "MCP transport rejected a cookie-only request to %s. These views are "
        "csrf_exempt on the premise that they authenticate from headers only; "
        "honouring an ambient cookie here would be a CSRF hole (SA-36).",
        request.path,
    )
    return JsonResponse(
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "error_code": "UNAUTHORIZED",
                "message": (
                    "The MCP transport authenticates from headers only. Send "
                    "the API key as 'Authorization: Bearer reqlo_…' or "
                    "'X-API-Key'; browser session cookies are never accepted "
                    "here."
                ),
            },
        },
        status=403,
    )

# Module-level shared instances (singleton pattern for Django process lifetime)
_tool_registry: ToolRegistry | None = None
_protocol_handler: ProtocolHandler | None = None
_auth_service: AuthenticationService | None = None

# Bounded worker pool for asynchronous SSE message processing (REQ-086 / F8.4).
# A single, process-wide pool caps the number of concurrent background threads
# so that a burst of messages can no longer spawn unbounded threads (OOM risk).
# Excess work queues instead of allocating a new OS thread per message.
_MESSAGE_POOL_MAX_WORKERS = 10
_message_executor = ThreadPoolExecutor(
    max_workers=_MESSAGE_POOL_MAX_WORKERS,
    thread_name_prefix="mcp-msg",
)


def _get_auth_service() -> AuthenticationService:
    """Return a shared AuthenticationService instance (lazy singleton)."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthenticationService()
    return _auth_service


def _get_handler() -> ProtocolHandler:
    """Return (or create) the shared ProtocolHandler instance."""
    global _tool_registry, _protocol_handler
    if _protocol_handler is None:
        _tool_registry = ToolRegistry()
        _protocol_handler = ProtocolHandler(tool_registry=_tool_registry)
    return _protocol_handler


def _extract_django_headers(request: HttpRequest) -> dict:
    """Extract relevant HTTP headers from Django META for API-key resolution.

    Only header-based authentication (``X-API-Key`` or ``Authorization:
    Bearer``) is accepted. A ``?api_key=`` query-parameter fallback is
    deliberately NOT supported: query strings are routinely written to proxy
    and web-server access logs, browser history and ``Referer`` headers,
    which would leak long-lived ``reqlo_*`` API keys (REQ-018 / SYSTEM_AUDIT
    P-05).
    """
    return {
        "HTTP_X_API_KEY": request.META.get("HTTP_X_API_KEY", ""),
        "X-API-Key": request.META.get("HTTP_X_API_KEY", ""),
        "HTTP_AUTHORIZATION": request.META.get("HTTP_AUTHORIZATION", ""),
    }


def _jsonrpc_request_id(body: bytes) -> object | None:
    """Return the JSON-RPC ``id`` of a request body, or None.

    Echoing the id back lets a client correlate a transport-level rejection
    with the call it made. A body that is absent, unparseable or not an
    object simply yields ``None`` — recovering the id must never be able to
    turn an error response into a second error.
    """
    try:
        frame = json.loads(body)
    except (ValueError, TypeError):
        return None
    return frame.get("id") if isinstance(frame, dict) else None


def _apply_cors_headers(request, response, *, methods: str = "POST, GET, OPTIONS"):
    """Add CORS headers to an MCP response (framework-agnostic helper).

    Extracted from :class:`CorsMixin` so that fully asynchronous views (which
    cannot mix in the synchronous ``dispatch`` override) can reuse the exact
    same CORS policy without inheriting the sync mixin.
    """
    # SECURITY (REQ-081): never reflect an arbitrary Origin alongside
    # Access-Control-Allow-Credentials. Only echo the Origin (and allow
    # credentials) when it is on the configured allowlist; otherwise omit the
    # credentials flag so browsers block credentialed cross-origin access.
    allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
    origin = request.headers.get("Origin", "")
    if origin and origin in allowed_origins:
        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Credentials"] = "true"
        response["Vary"] = "Origin"
    # Non-allowlisted (or missing) Origin: omit Access-Control-Allow-Origin
    # entirely rather than echoing an arbitrary allowlist entry, which would
    # be misleading metadata for an origin that was never actually allowed.
    response["Access-Control-Allow-Methods"] = methods
    response["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    return response


class CorsMixin:
    """Mixin to add CORS headers to MCP responses."""
    def options(self, request, *args, **kwargs):
        response = HttpResponse()
        return self._add_cors_headers(request, response)

    def _add_cors_headers(self, request, response):
        return _apply_cors_headers(request, response)

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return self._add_cors_headers(request, response)


@method_decorator(csrf_exempt, name="dispatch")
class McpHttpTransportView(CorsMixin, View):
    """HTTP transport endpoint for MCP JSON-RPC requests.

    Accepts POST application/json with a JSON-RPC 2.0 body.
    Returns application/json with a JSON-RPC 2.0 response.

    API key: Authorization: Bearer <key> or X-API-Key header only.
    ``params.api_key`` in the request body is intentionally not accepted
    on this transport — see ``TransportAdapter.extract_api_key`` /
    REQ-018 (body keys are as much a logging/proxy exposure risk as
    query-string keys, and stdio is the only transport without a header
    mechanism to fall back to).
    """

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Handle a single MCP tool call over HTTP."""
        # SA-36: enforce the premise of the csrf_exempt above — header-only auth.
        cookie_rejection = _reject_ambient_cookie_auth(request)
        if cookie_rejection is not None:
            return cookie_rejection

        # Rate limit before anything else (SYSTEMAUDIT-2026-08-27 finding A):
        # this is the endpoint that dispatches tools, so every request past
        # this point may cost a DB round trip or an LLM call.
        retry_after = check_mcp_rate_limit(request)
        if retry_after is not None:
            return rate_limited_jsonrpc_response(
                retry_after, request_id=_jsonrpc_request_id(request.body)
            )

        handler = _get_handler()
        headers = _extract_django_headers(request)

        # R3 (P0-soforthaertung task 12): a JSON-array (batch) body is not a
        # single JSON-RPC frame dict and would crash handle_http_request into
        # the generic 500 handler below. Batch dispatch is out of scope — no
        # client in this codebase's integration surface sends batched
        # requests, and the MCP spec treats batch support as optional. Reject
        # cleanly instead of forwarding it downstream.
        try:
            parsed_body = json.loads(request.body)
        except (ValueError, TypeError):
            parsed_body = None
        if isinstance(parsed_body, list):
            error_body = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "error_code": "INVALID_REQUEST",
                    "message": "Batch requests are not supported.",
                },
            }
            return HttpResponse(
                json.dumps(error_body),
                content_type="application/json",
                status=400,
            )

        try:
            response_frame = handler.handle_http_request(
                body=request.body,
                headers=headers,
            )
        except Exception:
            logger.exception("Unhandled exception in McpHttpTransportView")
            error_body = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "error_code": "INTERNAL_ERROR",
                    "message": "Internal server error.",
                },
            }
            return HttpResponse(
                json.dumps(error_body),
                content_type="application/json",
                status=500,
            )

        # Notifications carry no id and must not be answered (REQ-108). The
        # handler returns None; acknowledge with an empty 202 body.
        if response_frame is None:
            return HttpResponse(status=202)

        # Determine HTTP status from JSON-RPC error code
        http_status = 200
        if "error" in response_frame:
            numeric_code = response_frame["error"].get("code")
            error_code = _NUMERIC_TO_ERROR_CODE.get(numeric_code, "")
            if error_code in (
                "AUTH_FAILED",
                "PARSE_ERROR",
                "INVALID_REQUEST",
            ):
                http_status = 401
            elif error_code == "PERMISSION_DENIED":
                http_status = 403
            elif error_code in ("VALIDATION_ERROR", "UNKNOWN_TOOL"):
                http_status = 400
            elif error_code == "NOT_FOUND":
                http_status = 404
            elif error_code == "INTERNAL_ERROR":
                http_status = 500
            else:
                http_status = 400

        try:
            body = json.dumps(response_frame)
        except TypeError:
            # Issue #441: a tool handler's result contained a value
            # json.dumps() cannot encode (e.g. a raw UUID that slipped through
            # a service-layer dict instead of being stringified). Without this
            # guard the TypeError propagated out of this view entirely — past
            # the try/except around handle_http_request() above, which only
            # covers *that* call — so Django rendered its HTML debug page
            # instead of a JSON-RPC error envelope. Callers of a JSON-RPC API
            # must always get JSON back, even on an encoding failure that is
            # itself a server bug.
            logger.exception(
                "Unencodable JSON-RPC response frame in McpHttpTransportView"
            )
            error_body = {
                "jsonrpc": "2.0",
                "id": response_frame.get("id") if isinstance(response_frame, dict) else None,
                "error": {
                    "error_code": "INTERNAL_ERROR",
                    "message": "Internal server error.",
                },
            }
            return HttpResponse(
                json.dumps(error_body),
                content_type="application/json",
                status=500,
            )

        return HttpResponse(
            body,
            content_type="application/json",
            status=http_status,
        )

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Return server info / health check for HTTP GET."""
        # H1/H5.2 (systemaudit 2026-09-02): an MCP client using StreamableHTTP
        # opens a GET here expecting either a real event stream or a clean
        # 405 telling it none exists. Returning 200 info-JSON made the MCP
        # TypeScript SDK treat it as a stream that immediately closed, then
        # reconnect-loop against this endpoint until it hit the per-IP rate
        # limit.
        if "text/event-stream" in request.headers.get("Accept", ""):
            return HttpResponse(status=405)

        # Unauthenticated discovery endpoint — cheap per call, but there is no
        # reason to serve it at an unbounded rate either. In practice only the
        # per-IP backstop can fire here, since a discovery GET carries no key.
        retry_after = check_mcp_rate_limit(request)
        if retry_after is not None:
            return rate_limited_jsonrpc_response(retry_after)

        return HttpResponse(
            json.dumps({
                "server": "ReqogniLoom MCP Server",
                "protocol": "JSON-RPC 2.0",
                # REQ-131: advertise only implemented transports. SSE was
                # dropped from this list while `GET /mcp/sse/` answered 500 on
                # every request (issue #455 — a hop-by-hop `Connection` header
                # tripped wsgiref's PEP-3333 assertion under `runserver`).
                # Removing that header only fixed the 500; it did not make
                # `runserver` (WSGI) capable of streaming SSE — a WSGI server
                # can only serve an async iterator by buffering it in full,
                # which never terminates for an endless event stream. SSE only
                # works because the server now runs ASGI unconditionally, both
                # in production (`gunicorn -k uvicorn.workers.UvicornWorker`)
                # and in dev (`uvicorn --reload`, see
                # deploy/docker-compose.override.yml / reqogniloom/asgi.py). It is
                # the transport every distributed plugin config ships with
                # (`"type": "sse"` in dist/plugins/*), so it belongs here
                # again. Keep this list in sync with mcp_server/urls.py —
                # omitting a working transport misleads clients just as badly
                # as advertising a broken one. "stdio" is deliberately absent:
                # it is a separate, non-HTTP-routed transport (no path in
                # mcp_server/urls.py answers it), so listing it on this HTTP
                # discovery response would violate the very rule this comment
                # states (deep-dive review D-7a).
                "transports": ["http", "sse"],
                "version": "1.0.0",
            }),
            content_type="application/json",
            status=200,
        )


@method_decorator(csrf_exempt, name="dispatch")
class McpMessagesView(CorsMixin, View):
    """MCP standard HTTP POST endpoint for SSE sessions.
    
    Accepts JSON-RPC POST requests, returns 202 Accepted, and pushes the
    result to the SSE stream via Redis.
    """
    #: Path of the SSE handshake a client must re-open to obtain a fresh
    #: session. Surfaced in the SESSION_EXPIRED payload so the error itself
    #: tells the operator what to do (issue #427).
    _RECONNECT_ENDPOINT = "/mcp/sse/"

    #: Shared with :class:`McpHttpTransportView`, which needs the same id
    #: recovery for its own transport-level rejections.
    _request_id = staticmethod(_jsonrpc_request_id)

    @staticmethod
    def _error_response(
        *,
        status: int,
        error_code: str,
        message: str,
        request_id: object | None = None,
        data: dict | None = None,
    ) -> HttpResponse:
        """Build a JSON-RPC error envelope for a transport-level rejection.

        Mirrors the envelope shape used by :class:`McpHttpTransportView`
        (string ``error_code`` per REQ-047) so a client can branch on one
        machine-readable field regardless of which MCP endpoint rejected it —
        previously this view answered with a bare ``text/plain`` sentence that
        nothing could parse.
        """
        error: dict[str, object] = {"error_code": error_code, "message": message}
        if data:
            error["data"] = data
        return HttpResponse(
            json.dumps({"jsonrpc": "2.0", "id": request_id, "error": error}),
            content_type="application/json",
            status=status,
        )

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Accept a JSON-RPC message for an established SSE session."""
        # Read the body once: `request.body` is cached by Django, but the
        # background closure below must not touch the request after this
        # handler returns.
        body = request.body
        request_id = self._request_id(body)

        session_id = request.GET.get("session_id")

        # SA-36: enforce the premise of the csrf_exempt above. The credential on
        # this endpoint is the session id, not a header key, so it is passed in
        # explicitly — a cookie alone must never be enough to reach dispatch.
        cookie_rejection = _reject_ambient_cookie_auth(
            request, explicit_credential=session_id or ""
        )
        if cookie_rejection is not None:
            return cookie_rejection

        # Rate limit before the Redis session lookup and before dispatch
        # (SYSTEMAUDIT-2026-08-27 finding A). The session id is the credential
        # on this endpoint: the API key was bound to it at the SSE handshake and
        # is deliberately never present in this request, so it is what the
        # per-credential bucket has to key on. A request without one still gets
        # counted against the per-IP backstop.
        retry_after = check_mcp_rate_limit(request, credential=session_id or "")
        if retry_after is not None:
            return rate_limited_jsonrpc_response(retry_after, request_id=request_id)

        if not session_id:
            return self._error_response(
                status=400,
                error_code="INVALID_REQUEST",
                message=(
                    "Missing required query parameter 'session_id'. POST to the "
                    "endpoint URL delivered by the SSE 'endpoint' event."
                ),
                request_id=request_id,
            )

        # Imported lazily (as elsewhere in this module) so that importing the
        # URLConf never drags in the redis/cryptography stack.
        from mcp_server.sse_pubsub import (
            SESSION_TTL_SECONDS,
            get_session_api_key,
            publish_mcp_message,
        )

        # Authorise by session: the API key was bound to this session at the
        # SSE handshake and is NEVER accepted from the URL here. An unknown
        # or expired session is rejected (REQ-018 / SYSTEM_AUDIT P-02).
        session_api_key = get_session_api_key(session_id)
        if not session_api_key:
            # Issue #427: this is deliberately NOT reported as AUTH_FAILED.
            # The binding lives in Redis with a bounded TTL
            # (sse_pubsub.SESSION_TTL_SECONDS) and also disappears when Redis
            # is restarted or evicts the key, so a client whose API key is
            # entirely valid still lands here once its stream has outlived the
            # binding. The old bare `401 Invalid or expired session` surfaced in
            # clients as a generic auth error and sent operators looking for a
            # token problem; the actionable fix is always to re-open the SSE
            # stream. The HTTP status stays 401 (unchanged for clients that
            # branch on it) while the body now carries a distinct error_code
            # plus the endpoint to reconnect to.
            return self._error_response(
                status=401,
                error_code="SESSION_EXPIRED",
                # Built on top of the canonical SESSION_EXPIRED message
                # (protocol_handler.ERROR_CODES) rather than a second,
                # independently worded sentence — that message is the single
                # source of truth for what this error code means. Here it is
                # only extended with the request-specific reconnect detail
                # (session id, endpoint, retry hint).
                message=(
                    f"{ERROR_CODES['SESSION_EXPIRED']} Session "
                    f"'{session_id}' — re-open the SSE stream at "
                    f"{self._RECONNECT_ENDPOINT} to obtain a fresh session_id "
                    "and retry (in Claude Code: /mcp reconnect)."
                ),
                request_id=request_id,
                data={
                    "session_id": session_id,
                    "reconnect_endpoint": self._RECONNECT_ENDPOINT,
                    "session_ttl_seconds": SESSION_TTL_SECONDS,
                    "retryable": True,
                },
            )

        handler = _get_handler()
        headers = _extract_django_headers(request)
        # Force the session-bound key and ignore any api_key present in the URL.
        headers["HTTP_X_API_KEY"] = session_api_key
        headers["X-API-Key"] = session_api_key
        headers["HTTP_AUTHORIZATION"] = f"Bearer {session_api_key}"

        # `body` was captured at the top of this handler: the executor runs the
        # closure after this view has returned, at which point the request may
        # already be closed.

        # In a production system, this should be a Celery task. To avoid a
        # Celery dependency here we offload to a bounded thread pool
        # (REQ-086 / F8.4) instead of spawning one thread per message.
        def _process():
            # D-6: these bounded-pool threads live for the process lifetime and
            # are reused across many messages, so they never go through
            # Django's per-request connection-hygiene signals (request_started
            # / request_finished), which normally call close_old_connections()
            # for us. Without this, a connection that went stale (e.g. closed
            # by the DB server / a network blip) between two messages handled
            # on the same pool thread stays cached and every subsequent query
            # on it fails. Bookend the work explicitly to match the framework
            # convention this pool bypasses.
            close_old_connections()
            try:
                response_frame = handler.handle_http_request(
                    body=body,
                    headers=headers,
                )
                # Notifications (REQ-108) return None and must not be answered.
                if response_frame is not None:
                    publish_mcp_message(session_id, response_frame)
            except Exception:
                logger.exception("Error processing MCP message background task")
                publish_mcp_message(session_id, {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"error_code": "INTERNAL_ERROR", "message": "Internal server error."}
                })
            finally:
                close_old_connections()

        _message_executor.submit(_process)
        return HttpResponse(status=202)


@method_decorator(csrf_exempt, name="dispatch")
class McpSseTransportView(View):
    """SSE transport endpoint — serves a continuous stream for MCP.

    This view is **fully asynchronous** (all handlers are ``async def``). It
    deliberately does NOT mix in :class:`CorsMixin`, whose synchronous
    ``dispatch`` override is incompatible with async handlers and previously
    raised a ``TypeError`` on every ``GET /mcp/sse/`` (REQ-044). CORS headers
    are applied via the framework-agnostic :func:`_apply_cors_headers` helper.
    """

    _CORS_METHODS = "GET, OPTIONS"

    @staticmethod
    def _resolve_api_key(request: HttpRequest) -> str:
        """Resolve the API key from the SSE handshake request.

        Only the ``Authorization`` / ``X-API-Key`` headers are accepted.
        There is deliberately no ``?api_key=`` query-parameter fallback:
        query strings end up in proxy/access logs, browser history and
        ``Referer`` headers, which would leak the long-lived ``reqlo_*``
        secret (REQ-018 / SYSTEM_AUDIT P-05). Clients MUST authenticate via
        header.

        Delegates to :func:`mcp_server.throttling.api_key_from_request` so the
        throttle and the authentication path can never disagree about which
        credential a request presented — a second copy of this rule would
        eventually drift and silently bill one caller's requests to another's
        bucket.
        """
        return api_key_from_request(request)

    @staticmethod
    def _parse_last_event_id(request: HttpRequest) -> int | None:
        """Return the numeric ``Last-Event-ID`` header, or None if absent/invalid.

        EventSource clients resend the last id they received on reconnect
        (REQ-107). A missing or malformed value simply means "no replay" and
        must never break the handshake.
        """
        raw = request.META.get("HTTP_LAST_EVENT_ID", "")
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    async def _resolve_session_id(
        request: HttpRequest,
        api_key: str,
        get_session_api_key,
        store_session_api_key,
    ) -> str:
        """Resume a matching existing session or mint and bind a fresh one (REQ-107).

        A reconnecting client passes its ``session_id`` so it keeps the same
        replay buffer. The session is only reused when its server-side binding
        matches the authenticated key; this prevents a client from hijacking
        another session's stream (REQ-018). Any mismatch, unknown, or missing
        session falls back to a new, freshly bound session.
        """
        requested = request.GET.get("session_id", "")
        if requested:
            bound_key = await sync_to_async(get_session_api_key)(requested)
            # Constant-time compare (REQ-018 / SYSTEM_AUDIT P-02): a session's
            # bound key is a secret, same class of value as the API key it is
            # matched against, so it gets the same timing-safe treatment as
            # every other credential compare in this codebase. ``bound_key``
            # is legitimately ``None`` for an unknown/expired session — that
            # is not a match and must not reach ``compare_digest``, which
            # requires both arguments to be strings (or bytes) of matching type.
            if bound_key is not None and hmac.compare_digest(bound_key, api_key):
                return requested

        session_id = str(uuid.uuid4())
        # Bind the authenticated key to the session server-side so the secret
        # never travels in the message-endpoint URL (REQ-018 / SYSTEM_AUDIT P-02).
        await sync_to_async(store_session_api_key)(session_id, api_key)
        return session_id

    async def options(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Answer CORS preflight for the SSE endpoint."""
        return _apply_cors_headers(
            request, HttpResponse(), methods=self._CORS_METHODS
        )

    async def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Standard MCP SSE connection establishment.

        The handshake is authenticated (REQ-044): an SSE stream is only opened
        for a request carrying a valid API key. This closes the unauthenticated
        DoS vector where any client could hold a streaming connection open.
        """
        from mcp_server.sse_pubsub import (
            async_sse_generator,
            get_session_api_key,
            store_session_api_key,
        )

        api_key = self._resolve_api_key(request)

        # SA-36: enforce the premise of the csrf_exempt above — header-only auth.
        # Pure function, no DB/IO, so it is safe to call from this async handler.
        cookie_rejection = _reject_ambient_cookie_auth(
            request, explicit_credential=api_key
        )
        if cookie_rejection is not None:
            return _apply_cors_headers(
                request, cookie_rejection, methods=self._CORS_METHODS
            )

        # Rate limit BEFORE authenticating (SYSTEMAUDIT-2026-08-27 finding A).
        # Order matters: validate_api_key() is a DB round trip, and a rejected
        # handshake would otherwise still cost one per attempt. Throttling first
        # is also what bounds the "open unlimited SSE sessions" DoS, since every
        # accepted handshake allocates a Redis binding plus a held-open
        # streaming connection. Done via sync_to_async because the cache backend
        # is synchronous, matching how this async view already calls
        # validate_api_key / get_session_api_key.
        retry_after = await sync_to_async(check_mcp_rate_limit)(
            request, credential=api_key
        )
        if retry_after is not None:
            return _apply_cors_headers(
                request,
                rate_limited_plain_response(retry_after),
                methods=self._CORS_METHODS,
            )

        # Authenticate the handshake before allocating a streaming connection.
        if not api_key:
            return _apply_cors_headers(
                request,
                JsonResponse({"error": "Authentication required"}, status=401),
                methods=self._CORS_METHODS,
            )
        try:
            await sync_to_async(_get_auth_service().validate_api_key)(api_key)
        except AuthenticationFailed:
            return _apply_cors_headers(
                request,
                JsonResponse({"error": "Authentication required"}, status=401),
                methods=self._CORS_METHODS,
            )

        # Resume an existing session when the client reconnects with a known
        # session_id whose server-side binding matches the authenticated key
        # (REQ-107). Reusing the session keeps the same replay buffer/channel so
        # Last-Event-ID recovery can actually find the missed events. Any other
        # case (no session_id, unknown, or key mismatch) mints a fresh session.
        try:
            session_id = await self._resolve_session_id(
                request, api_key, get_session_api_key, store_session_api_key
            )
        except Exception:
            # store_session_api_key (D-5b) now raises on a Redis write failure
            # instead of silently returning a session id whose key binding
            # never landed — that session would only ever surface as a
            # confusing SESSION_EXPIRED on the very next message. Fail the
            # handshake honestly here instead.
            logger.exception("Failed to establish SSE session")
            return _apply_cors_headers(
                request,
                JsonResponse({"error": "Failed to establish session"}, status=500),
                methods=self._CORS_METHODS,
            )

        # A reconnecting EventSource replays from the last id it received; parse
        # it defensively so a malformed header just starts a fresh stream.
        last_event_id = self._parse_last_event_id(request)

        # The message endpoint carries ONLY the session id — never the
        # api_key, which would otherwise leak into access/proxy logs and
        # browser history (REQ-018 / SYSTEM_AUDIT P-02).
        prefix = ""
        path = request.path.strip("/")
        if path.count("/") > 1:
            prefix = "/" + "/".join(path.split("/")[:-2])
        endpoint = f"{prefix}/mcp/messages/?session_id={session_id}"

        response = StreamingHttpResponse(
            async_sse_generator(session_id, endpoint, last_event_id=last_event_id),
            content_type="text/event-stream",
            status=200,
        )
        _apply_cors_headers(request, response, methods=self._CORS_METHODS)
        response["Cache-Control"] = "no-cache"
        # NOTE (issue #455): do NOT set `Connection: keep-alive` here.
        # `Connection` is a hop-by-hop header (RFC 9110 §7.6.1) and belongs to
        # the server/proxy, not to the application. PEP 3333 forbids a WSGI
        # application from emitting one, and wsgiref enforces that with a bare
        # `assert not is_hop_by_hop(name)` in
        # `wsgiref.handlers.BaseHandler.start_response` — which turned every
        # `GET /mcp/sse/` under `manage.py runserver` into a 500. Persistent
        # connections are the HTTP/1.1 default anyway, so the header bought
        # nothing even on the ASGI stack that tolerated it.
        return response

__all__ = [
    "McpHttpTransportView",
    "McpSseTransportView",
    "McpMessagesView",
]
