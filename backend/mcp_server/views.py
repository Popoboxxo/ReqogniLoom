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

from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from mcp_server.protocol_handler import ProtocolHandler
from mcp_server.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# Module-level shared instances (singleton pattern for Django process lifetime)
_tool_registry: ToolRegistry | None = None
_protocol_handler: ProtocolHandler | None = None


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
        
    logger.error(f"DEBUG HEADERS META: {request.META.get('HTTP_AUTHORIZATION')} | {request.META.get('HTTP_X_API_KEY')}")
    logger.error(f"DEBUG QUERY: {api_key_query}")
    logger.error(f"DEBUG EXTRACTED: {headers}")
    return headers


class CorsMixin:
    """Mixin to add CORS headers to MCP responses."""
    def options(self, request, *args, **kwargs):
        response = HttpResponse()
        return self._add_cors_headers(request, response)

    def _add_cors_headers(self, request, response):
        origin = request.headers.get("Origin", "*")
        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Credentials"] = "true"
        response["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
        return response

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
            
        handler = _get_handler()
        headers = _extract_django_headers(request)
        
        # In a production system, this should be a Celery task.
        # For simplicity and to avoid Celery dependencies here, we use a thread.
        import threading
        from mcp_server.sse_pubsub import publish_mcp_message
        
        def _process():
            try:
                response_frame = handler.handle_http_request(
                    body=request.body,
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
                
        threading.Thread(target=_process).start()
        return HttpResponse(status=202)


@method_decorator(csrf_exempt, name="dispatch")
class McpSseTransportView(CorsMixin, View):
    """SSE transport endpoint — serves a continuous stream for MCP."""

    async def get(self, request: HttpRequest, *args, **kwargs) -> StreamingHttpResponse:
        """Standard MCP SSE connection establishment."""
        import uuid
        from mcp_server.sse_pubsub import async_sse_generator
        
        session_id = str(uuid.uuid4())
        
        # Retrieve the API key from the initial GET request headers or query
        api_key = request.GET.get("api_key", "")
        if not api_key:
            auth = request.META.get("HTTP_AUTHORIZATION", "")
            if auth.startswith("Bearer "):
                api_key = auth[7:]
            else:
                api_key = request.META.get("HTTP_X_API_KEY", "")

        # The POST endpoint for this session
        endpoint = f"/mcp/messages/?session_id={session_id}"
        if api_key:
            endpoint += f"&api_key={api_key}"

        response = StreamingHttpResponse(
            async_sse_generator(session_id, endpoint),
            content_type="text/event-stream",
            status=200,
        )
        # CorsMixin is synchronous, so we add headers manually here
        origin = request.headers.get("Origin", "*")
        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Credentials"] = "true"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
        response["Cache-Control"] = "no-cache"
        response["Connection"] = "keep-alive"
        return response

__all__ = [
    "McpHttpTransportView",
    "McpSseTransportView",
    "McpMessagesView",
]
