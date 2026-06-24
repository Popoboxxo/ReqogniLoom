"""
COMP-MC-001 ProtocolHandler — MCP transport and JSON-RPC frame handling.

leaf_id : COMP-MC-001
req_id  : REQ-L2-MC-005 (transport), REQ-L2-MC-006 (API-key extraction),
          REQ-L2-MC-011 (structured error response)

Responsibilities:
- Receive MCP requests over stdio, SSE and HTTP transports.
- Validate JSON-RPC 2.0 frames (method, id, syntax) before dispatch.
- Extract API key from the request (header or params).
- Serialise ToolResult objects back to transport-specific response frames.
- Return structured error responses (REQ-L2-MC-011 format) on failure.

Interface contracts implemented:
  IF-MC-EXT-IN-001  — inbound: MCP-Protocol (JSON-RPC) from AI-Agent
  IF-MC-INT-001     — outbound: dispatch_request(frame) -> ToolResult via ToolRegistry
  IF-MC-EXT-OUT-001 — outbound: serialised JSON response to AI-Agent

Architecture:
  docs/se/L1/Gesamtsystem/L2/McpServerSystem/Components/
    COMP-MC-001_ProtocolHandler/
      L3_COMP-MC-001_ProtocolHandler_Architecture.md

ADR-L3-MC001-01: TransportAdapter pattern — ProtocolHandler stays transport-agnostic.
ADR-L3-MC001-02: JSON-RPC validation before ToolRegistry invocation (fail-fast).
ADR-L3-MC001-03: API-key forwarded to ToolRegistry inside the dispatch frame.
"""
from __future__ import annotations

import json
import logging
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error codes (REQ-L2-MC-011)
# ---------------------------------------------------------------------------

ERROR_CODES = {
    "AUTH_FAILED": "Authentication failed. API key missing or invalid.",
    "PERMISSION_DENIED": "Insufficient permissions for this operation.",
    "FEATURE_NOT_ENABLED": "This tool is not available in the active workspace preset.",
    "UNKNOWN_TOOL": "The requested tool is not registered.",
    "VALIDATION_ERROR": "Request parameters failed schema validation.",
    "LLM_NOT_CONFIGURED": "This tool requires an LLM provider which is not configured.",
    "NOT_FOUND": "The requested resource was not found.",
    "INTERNAL_ERROR": "An internal server error occurred.",
    "PARSE_ERROR": "Failed to parse JSON-RPC request.",
    "INVALID_REQUEST": "Malformed JSON-RPC request frame.",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class ToolResult:
    """Wrapper for tool execution results (IF-MC-INT-006).

    Carries either a successful payload or an error code + message.
    """

    def __init__(
        self,
        *,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.success = success
        self.data = data or {}
        self.error_code = error_code
        self.message = message or (ERROR_CODES.get(error_code or "", "") if error_code else "")
        self.details = details

    @classmethod
    def ok(cls, data: Dict[str, Any]) -> "ToolResult":
        """Construct a successful ToolResult."""
        return cls(success=True, data=data)

    @classmethod
    def error(
        cls,
        error_code: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """Construct an error ToolResult."""
        return cls(
            success=False,
            error_code=error_code,
            message=message or ERROR_CODES.get(error_code, error_code),
            details=details,
        )


# ---------------------------------------------------------------------------
# JSON-RPC Validator (ADR-L3-MC001-02)
# ---------------------------------------------------------------------------


class JsonRpcValidator:
    """Validate JSON-RPC 2.0 frames before dispatch (REQ-L3-MC001-002)."""

    REQUIRED_FIELDS = ("jsonrpc", "method", "id")

    @classmethod
    def validate(cls, frame: Any) -> Optional[str]:
        """Return an error code string if the frame is invalid, else None."""
        if not isinstance(frame, dict):
            return "INVALID_REQUEST"
        if frame.get("jsonrpc") != "2.0":
            return "INVALID_REQUEST"
        if not isinstance(frame.get("method"), str) or not frame["method"]:
            return "INVALID_REQUEST"
        if "id" not in frame:
            return "INVALID_REQUEST"
        return None


# ---------------------------------------------------------------------------
# Error Formatter (REQ-L2-MC-011)
# ---------------------------------------------------------------------------


class ErrorFormatter:
    """Format structured error responses for MCP clients."""

    @staticmethod
    def format_error(
        error_code: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a structured error dict (REQ-L2-MC-011)."""
        body: Dict[str, Any] = {
            "error_code": error_code,
            "message": message or ERROR_CODES.get(error_code, error_code),
        }
        if details:
            body["details"] = details
        return body

    @staticmethod
    def format_jsonrpc_error(
        request_id: Any,
        error_code: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a JSON-RPC 2.0 error response frame."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": ErrorFormatter.format_error(error_code, message, details),
        }

    @staticmethod
    def format_jsonrpc_result(request_id: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return a JSON-RPC 2.0 success response frame."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": data,
        }


# ---------------------------------------------------------------------------
# Transport adapters (ADR-L3-MC001-01)
# ---------------------------------------------------------------------------


class TransportAdapter(ABC):
    """Abstract transport interface. Concrete adapters implement read/write."""

    @abstractmethod
    def read_request(self) -> Optional[Dict[str, Any]]:
        """Read and parse one JSON-RPC request from the transport."""

    @abstractmethod
    def write_response(self, response: Dict[str, Any]) -> None:
        """Serialise and write a JSON-RPC response frame to the transport."""

    @staticmethod
    def extract_api_key(frame: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Extract API key from request frame or headers (ADR-L3-MC001-03).

        Priority:
          1. X-API-Key HTTP header (HTTP/SSE transports)
          2. params.api_key (all transports — used by stdio clients)
        """
        if headers:
            key = headers.get("HTTP_X_API_KEY") or headers.get("X-API-Key")
            if key:
                return key
        params = frame.get("params") or {}
        return params.get("api_key")


class StdioTransportAdapter(TransportAdapter):
    """stdio transport — reads newline-delimited JSON from stdin."""

    def __init__(self, stdin=None, stdout=None) -> None:
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout

    def read_request(self) -> Optional[Dict[str, Any]]:
        line = self._stdin.readline()
        if not line:
            return None
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError:
            return {"_parse_error": True}

    def write_response(self, response: Dict[str, Any]) -> None:
        self._stdout.write(json.dumps(response) + "\n")
        self._stdout.flush()


class HttpTransportAdapter(TransportAdapter):
    """HTTP transport — reads from Django request body, writes to response dict."""

    def __init__(self, body: bytes, headers: Optional[Dict[str, str]] = None) -> None:
        self._body = body
        self._headers = headers or {}
        self._response: Optional[Dict[str, Any]] = None

    def read_request(self) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self._body)
        except (json.JSONDecodeError, ValueError):
            return {"_parse_error": True}

    def write_response(self, response: Dict[str, Any]) -> None:
        self._response = response

    def get_response(self) -> Optional[Dict[str, Any]]:
        """Return the response written by write_response()."""
        return self._response

    def get_headers(self) -> Dict[str, str]:
        """Return headers for API-key extraction."""
        return self._headers


class SseTransportAdapter(TransportAdapter):
    """SSE transport — same as HTTP for request reading; streaming on write.

    For this implementation the SSE stream is a single-request-per-connection
    pattern (no long-polling loop). Streaming multiplexing would require an
    async server and is out of scope for this synchronous Django implementation.
    """

    def __init__(self, body: bytes, headers: Optional[Dict[str, str]] = None) -> None:
        self._body = body
        self._headers = headers or {}
        self._events: list = []

    def read_request(self) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self._body)
        except (json.JSONDecodeError, ValueError):
            return {"_parse_error": True}

    def write_response(self, response: Dict[str, Any]) -> None:
        self._events.append(response)

    def get_events(self) -> list:
        """Return the list of SSE events produced."""
        return self._events

    def get_headers(self) -> Dict[str, str]:
        return self._headers


# ---------------------------------------------------------------------------
# ProtocolHandler (COMP-MC-001)
# ---------------------------------------------------------------------------


class ProtocolHandler:
    """Central request/response orchestration for MCP (COMP-MC-001).

    Coordinates JSON-RPC validation, API-key extraction, ToolRegistry dispatch
    and response serialisation. Remains transport-agnostic (ADR-L3-MC001-01).
    """

    def __init__(self, tool_registry: Any) -> None:
        """Initialise with a ToolRegistry instance (IF-MC-INT-001).

        Args:
            tool_registry: ToolRegistry instance used for dispatch.
        """
        self._registry = tool_registry

    def handle(
        self,
        adapter: TransportAdapter,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Handle one MCP request via *adapter* and return the response frame.

        Steps (ADR-L3-MC001-02):
          1. Read request from transport adapter.
          2. Detect parse errors early.
          3. Validate JSON-RPC frame structure.
          4. Extract API key (ADR-L3-MC001-03).
          5. Dispatch to ToolRegistry.
          6. Serialise response.

        Args:
            adapter: Transport adapter providing read/write primitives.
            headers: Optional HTTP headers dict for API-key extraction.

        Returns:
            A JSON-RPC 2.0 response frame (dict).
        """
        frame = adapter.read_request()

        # Parse error path (pre-validation)
        if frame is None or frame.get("_parse_error"):
            response = ErrorFormatter.format_jsonrpc_error(
                None, "PARSE_ERROR"
            )
            adapter.write_response(response)
            return response

        request_id = frame.get("id")

        # JSON-RPC structure validation (ADR-L3-MC001-02)
        validation_error = JsonRpcValidator.validate(frame)
        if validation_error:
            response = ErrorFormatter.format_jsonrpc_error(
                request_id, "INVALID_REQUEST",
                "Malformed JSON-RPC 2.0 request frame."
            )
            adapter.write_response(response)
            return response

        tool_name: str = frame["method"]
        params: Dict[str, Any] = frame.get("params") or {}

        # API-key extraction (ADR-L3-MC001-03 / REQ-L2-MC-006)
        # Try headers first, fall back to params
        effective_headers: Dict[str, str] = {}
        if headers:
            effective_headers = headers
        elif hasattr(adapter, "get_headers"):
            effective_headers = adapter.get_headers()  # type: ignore[attr-defined]

        api_key = adapter.extract_api_key(frame, effective_headers)

        if not api_key:
            response = ErrorFormatter.format_jsonrpc_error(
                request_id, "AUTH_FAILED",
                "API key is required. Provide X-API-Key header or params.api_key."
            )
            adapter.write_response(response)
            return response

        # Strip internal api_key from params before dispatching to tool group
        clean_params = {k: v for k, v in params.items() if k != "api_key"}

        # Dispatch to ToolRegistry (IF-MC-INT-001)
        try:
            result: ToolResult = self._registry.dispatch_request(
                tool_name=tool_name,
                params=clean_params,
                api_key=api_key,
            )
        except Exception as exc:
            logger.exception("Unhandled error during MCP dispatch for tool=%s", tool_name)
            response = ErrorFormatter.format_jsonrpc_error(
                request_id, "INTERNAL_ERROR", str(exc)
            )
            adapter.write_response(response)
            return response

        # Serialise ToolResult (IF-MC-EXT-OUT-001)
        if result.success:
            response = ErrorFormatter.format_jsonrpc_result(request_id, result.data)
        else:
            response = ErrorFormatter.format_jsonrpc_error(
                request_id,
                result.error_code or "INTERNAL_ERROR",
                result.message,
                result.details,
            )

        adapter.write_response(response)
        return response

    def handle_http_request(
        self,
        body: bytes,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Convenience wrapper for HTTP transport (Django view integration).

        Args:
            body: Raw request body bytes.
            headers: Django META-style or plain header dict.

        Returns:
            JSON-RPC 2.0 response frame.
        """
        adapter = HttpTransportAdapter(body=body, headers=headers or {})
        return self.handle(adapter, headers=headers)


__all__ = [
    "ProtocolHandler",
    "ToolResult",
    "JsonRpcValidator",
    "ErrorFormatter",
    "TransportAdapter",
    "StdioTransportAdapter",
    "HttpTransportAdapter",
    "SseTransportAdapter",
    "ERROR_CODES",
]
