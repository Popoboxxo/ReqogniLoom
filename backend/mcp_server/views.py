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
    return {
        "HTTP_X_API_KEY": request.META.get("HTTP_X_API_KEY", ""),
        "X-API-Key": request.META.get("HTTP_X_API_KEY", ""),
    }


@method_decorator(csrf_exempt, name="dispatch")
class McpHttpTransportView(View):
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
        except Exception as exc:
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
class McpSseTransportView(View):
    """SSE transport endpoint — serves a single MCP response as a SSE event.

    Clients connecting to this endpoint POST a JSON-RPC request; the response
    is sent as a ``data:`` SSE event. Long-lived SSE streaming would require
    an async server (out of scope for synchronous Django).
    """

    def post(self, request: HttpRequest, *args, **kwargs) -> StreamingHttpResponse:
        """Handle a single MCP tool call over SSE."""
        handler = _get_handler()
        headers = _extract_django_headers(request)

        try:
            response_frame = handler.handle_http_request(
                body=request.body,
                headers=headers,
            )
        except Exception as exc:
            logger.exception("Unhandled exception in McpSseTransportView")
            response_frame = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"error_code": "INTERNAL_ERROR", "message": "Internal server error."},
            }

        def _sse_generator():
            yield f"data: {json.dumps(response_frame)}\n\n"

        return StreamingHttpResponse(
            _sse_generator(),
            content_type="text/event-stream",
            status=200,
        )


__all__ = [
    "McpHttpTransportView",
    "McpSseTransportView",
]
