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

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from asgiref.sync import sync_to_async
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
from mcp_server.protocol_handler import ProtocolHandler
from mcp_server.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

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
    """Extract relevant HTTP headers from Django META for API-key resolution."""
    headers = {
        "HTTP_X_API_KEY": request.META.get("HTTP_X_API_KEY", ""),
        "X-API-Key": request.META.get("HTTP_X_API_KEY", ""),
        "HTTP_AUTHORIZATION": request.META.get("HTTP_AUTHORIZATION", ""),
    }
    
    api_key_query = request.GET.get("api_key")
    if api_key_query and not headers["HTTP_AUTHORIZATION"] and not headers["HTTP_X_API_KEY"]:
        headers["HTTP_X_API_KEY"] = api_key_query

    return headers


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
    elif allowed_origins:
        # Default to the first configured origin for non-credentialed clients.
        response["Access-Control-Allow-Origin"] = allowed_origins[0]
        response["Vary"] = "Origin"
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

    API key: X-API-Key header or params.api_key in request body.
    """

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Handle a single MCP tool call over HTTP."""
        handler = _get_handler()
        headers = _extract_django_headers(request)

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

        # Determine HTTP status from JSON-RPC error code
        http_status = 200
        if "error" in response_frame:
            error_code = response_frame["error"].get("error_code", "")
            if error_code in ("AUTH_FAILED", "PARSE_ERROR", "INVALID_REQUEST"):
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

        return HttpResponse(
            json.dumps(response_frame),
            content_type="application/json",
            status=http_status,
        )

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Return server info / health check for HTTP GET."""
        return HttpResponse(
            json.dumps({
                "server": "ReqFlow MCP Server",
                "protocol": "JSON-RPC 2.0",
                "transports": ["http", "sse", "stdio"],
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
    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        session_id = request.GET.get("session_id")
        if not session_id:
            return HttpResponse("Missing session_id", status=400)

        from mcp_server.sse_pubsub import get_session_api_key, publish_mcp_message

        # Authorise by session: the API key was bound to this session at the
        # SSE handshake and is NEVER accepted from the URL here. An unknown
        # or expired session is rejected (REQ-018 / SYSTEM_AUDIT P-02).
        session_api_key = get_session_api_key(session_id)
        if not session_api_key:
            return HttpResponse("Invalid or expired session", status=401)

        handler = _get_handler()
        headers = _extract_django_headers(request)
        # Force the session-bound key and ignore any api_key present in the URL.
        headers["HTTP_X_API_KEY"] = session_api_key
        headers["X-API-Key"] = session_api_key
        headers["HTTP_AUTHORIZATION"] = f"Bearer {session_api_key}"

        # Capture the request body now: the executor runs the closure after
        # this view has returned, at which point the request may be closed.
        body = request.body

        # In a production system, this should be a Celery task. To avoid a
        # Celery dependency here we offload to a bounded thread pool
        # (REQ-086 / F8.4) instead of spawning one thread per message.
        def _process():
            try:
                response_frame = handler.handle_http_request(
                    body=body,
                    headers=headers,
                )
                publish_mcp_message(session_id, response_frame)
            except Exception:
                logger.exception("Error processing MCP message background task")
                publish_mcp_message(session_id, {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"error_code": "INTERNAL_ERROR", "message": "Internal server error."}
                })

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

        Prefers the ``Authorization`` / ``X-API-Key`` headers. The
        query-parameter fallback is retained only for backward
        compatibility with older clients; new clients MUST authenticate
        via header so the secret is not exposed in the URL (REQ-018).
        """
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        header_key = request.META.get("HTTP_X_API_KEY", "")
        if header_key:
            return header_key
        return request.GET.get("api_key", "")

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
        from mcp_server.sse_pubsub import async_sse_generator, store_session_api_key

        # Authenticate the handshake before allocating a streaming connection.
        api_key = self._resolve_api_key(request)
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

        session_id = str(uuid.uuid4())

        # Bind the authenticated key to the session server-side so the secret
        # never travels in the message-endpoint URL (REQ-018 / SYSTEM_AUDIT P-02).
        await sync_to_async(store_session_api_key)(session_id, api_key)

        # The message endpoint carries ONLY the session id — never the
        # api_key, which would otherwise leak into access/proxy logs and
        # browser history (REQ-018 / SYSTEM_AUDIT P-02).
        endpoint = f"/mcp/messages/?session_id={session_id}"

        response = StreamingHttpResponse(
            async_sse_generator(session_id, endpoint),
            content_type="text/event-stream",
            status=200,
        )
        _apply_cors_headers(request, response, methods=self._CORS_METHODS)
        response["Cache-Control"] = "no-cache"
        response["Connection"] = "keep-alive"
        return response

__all__ = [
    "McpHttpTransportView",
    "McpSseTransportView",
    "McpMessagesView",
]
