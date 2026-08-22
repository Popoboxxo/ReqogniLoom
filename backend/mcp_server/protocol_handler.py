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
# MCP protocol version (REQ-108)
# ---------------------------------------------------------------------------
# Single source of truth for the negotiated MCP protocol revision. Kept as a
# module-level constant instead of a scattered string literal so a version bump
# touches exactly one line. See https://modelcontextprotocol.io/specification.
MCP_PROTOCOL_VERSION = "2024-11-05"

# ---------------------------------------------------------------------------
# Error codes (REQ-L2-MC-011, JSON-RPC 2.0 compliant)
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
    # Distinct from AUTH_FAILED on purpose (issue #427): the credentials may be
    # perfectly valid while the SSE session they were bound to has expired or
    # been evicted. Collapsing both into AUTH_FAILED sent users hunting for a
    # token problem when the only fix is to re-open the SSE stream.
    "SESSION_EXPIRED": (
        "The MCP SSE session is unknown or has expired. This is not an "
        "authentication failure — reconnect to obtain a fresh session_id."
    ),
}

# Protocol-level error codes (REQ-086 / MCP spec).
# These are transport/JSON-RPC concerns — malformed frames, unknown tools,
# authentication, authorization and preset gating. They are always reported
# as JSON-RPC errors, even for a ``tools/call`` request. Every other error
# code originates from the tool actually executing and is therefore a
# tool-execution error, which the MCP spec requires to be returned as a
# successful JSON-RPC response carrying ``isError: true`` in its result.
_PROTOCOL_ERROR_CODES = frozenset({
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "UNKNOWN_TOOL",
    "AUTH_FAILED",
    "PERMISSION_DENIED",
    "FEATURE_NOT_ENABLED",
})

# JSON-RPC 2.0 Error Code Mapping
# See: https://www.jsonrpc.org/specification#error_object
# Standard codes: -32700 to -32603; Server-defined: -32000 to -32768
ERROR_CODE_MAP = {
    "PARSE_ERROR": -32700,           # JSON Parse error
    "INVALID_REQUEST": -32600,       # Invalid Request
    "UNKNOWN_TOOL": -32601,          # Method not found
    "VALIDATION_ERROR": -32602,      # Invalid params
    "INTERNAL_ERROR": -32603,        # Internal error
    "AUTH_FAILED": -32000,           # Server-defined: Authentication
    "PERMISSION_DENIED": -32001,     # Server-defined: Permission
    "FEATURE_NOT_ENABLED": -32002,   # Server-defined: Feature
    "LLM_NOT_CONFIGURED": -32003,    # Server-defined: LLM config
    "NOT_FOUND": -32004,             # Server-defined: Not found
    "SESSION_EXPIRED": -32005,       # Server-defined: SSE session gone (#427)
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
        # notifications don't have an id, but for our simple implementation we accept them
        # if method is notifications/initialized, id is not required
        if frame["method"] != "notifications/initialized" and "id" not in frame:
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
        """Return a structured error dict (REQ-L2-MC-011, JSON-RPC 2.0 compliant).

        Returns error object with 'code' (int) and 'message' (str) per
        https://www.jsonrpc.org/specification#error_object
        """
        # Map error_code string to JSON-RPC numeric code
        rpc_code = ERROR_CODE_MAP.get(error_code, -32603)  # Default to Internal Error

        body: Dict[str, Any] = {
            "code": rpc_code,
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

    def extract_api_key(self, frame: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Extract API key from request frame or headers (ADR-L3-MC001-03).

        Priority:
          1. Authorization: Bearer <key> header
          2. X-API-Key HTTP header (HTTP/SSE transports)
          3. params.api_key (stdio transport only — see below)

        ``params.api_key`` is only honoured on the stdio transport. stdio has
        no header mechanism, so it legitimately needs the JSON-RPC body as
        its key channel. HTTP/SSE transports *do* have a header mechanism,
        and accepting the key from the request body there would expose it to
        the same logging/proxy/tracing risk the query-string fallback is
        already rejected for (REQ-018 / SYSTEM_AUDIT P-05) — so for those
        transports a body-only key is treated as no key at all.
        """
        if headers:
            auth_header = headers.get("HTTP_AUTHORIZATION") or headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                return auth_header[7:]

            key = headers.get("HTTP_X_API_KEY") or headers.get("X-API-Key")
            if key:
                return key
        if isinstance(self, StdioTransportAdapter):
            params = frame.get("params") or {}
            return params.get("api_key")
        return None


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
    ) -> Optional[Dict[str, Any]]:
        """Handle one MCP request via *adapter* and return the response frame.

        Returns ``None`` for JSON-RPC notifications, which must not be
        answered (REQ-108).

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

        method: str = frame["method"]
        params: Dict[str, Any] = frame.get("params") or {}
        
        # 1. Handle MCP lifecycle methods without API key validation (ping, initialize)
        if method == "ping":
            response = ErrorFormatter.format_jsonrpc_result(request_id, {})
            adapter.write_response(response)
            return response
            
        if method == "initialize":
            response = ErrorFormatter.format_jsonrpc_result(request_id, {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "ReqogniLoom",
                    "version": "1.0.0"
                }
            })
            adapter.write_response(response)
            return response
            
        # JSON-RPC notifications (method prefix "notifications/") carry no id and
        # MUST NOT receive a response (MCP spec / JSON-RPC 2.0, REQ-108). We
        # acknowledge them by returning ``None`` — the transport layer maps this
        # to an empty 202 body and never writes a JSON-RPC frame back.
        if method.startswith("notifications/"):
            return None

        # API-key extraction (ADR-L3-MC001-03 / REQ-L2-MC-006)
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

        # Strip internal api_key from params before dispatching
        clean_params = {k: v for k, v in params.items() if k != "api_key"}

        # 2. Handle standard MCP methods (tools/list, tools/call)
        if method == "tools/list":
            from mcp_server.tool_registry import McpAuthenticationError

            try:
                tools_list = self._registry.list_tools(
                    api_key=api_key,
                    workspace_id=clean_params.get("workspace_id"),
                )
                response = ErrorFormatter.format_jsonrpc_result(request_id, {"tools": tools_list})
            except McpAuthenticationError as exc:
                response = ErrorFormatter.format_jsonrpc_error(request_id, "AUTH_FAILED", str(exc))
            except Exception as exc:
                logger.exception("Error listing tools")
                response = ErrorFormatter.format_jsonrpc_error(request_id, "INTERNAL_ERROR", str(exc))
            adapter.write_response(response)
            return response

        tool_name = method
        tool_args = clean_params

        if method == "tools/call":
            tool_name = clean_params.get("name", "")
            tool_args = clean_params.get("arguments", {})
            if not tool_name:
                response = ErrorFormatter.format_jsonrpc_error(request_id, "INVALID_REQUEST", "Missing tool name in tools/call")
                adapter.write_response(response)
                return response

        # Dispatch to ToolRegistry (IF-MC-INT-001)
        try:
            result: ToolResult = self._registry.dispatch_request(
                tool_name=tool_name,
                params=tool_args,
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
            # Wrap the result in MCP standard content blocks if it was a standard call
            if method == "tools/call":
                import json
                text_content = result.data if isinstance(result.data, str) else json.dumps(result.data, indent=2)
                response_data = {
                    "content": [
                        {"type": "text", "text": text_content}
                    ]
                }
            else:
                response_data = result.data
            response = ErrorFormatter.format_jsonrpc_result(request_id, response_data)
        else:
            error_code = result.error_code or "INTERNAL_ERROR"
            # MCP spec (REQ-086 / F8.2): a tool-execution error must be
            # returned as a *successful* JSON-RPC response whose result
            # carries ``isError: true``. Protocol-level errors (auth,
            # unknown tool, malformed request, RBAC/preset gating) stay
            # JSON-RPC errors. The isError shape only applies to the
            # standard ``tools/call`` surface; direct-method dispatch keeps
            # the legacy JSON-RPC-error contract.
            if method == "tools/call" and error_code not in _PROTOCOL_ERROR_CODES:
                error_text = result.message or ERROR_CODES.get(error_code, error_code)
                response = ErrorFormatter.format_jsonrpc_result(
                    request_id,
                    {
                        "content": [
                            {"type": "text", "text": f"Error: {error_text}"}
                        ],
                        "isError": True,
                    },
                )
            else:
                response = ErrorFormatter.format_jsonrpc_error(
                    request_id,
                    error_code,
                    result.message,
                    result.details,
                )

        adapter.write_response(response)
        return response

    def handle_http_request(
        self,
        body: bytes,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Convenience wrapper for HTTP transport (Django view integration).

        Args:
            body: Raw request body bytes.
            headers: Django META-style or plain header dict.

        Returns:
            JSON-RPC 2.0 response frame, or ``None`` for notifications (REQ-108).
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
