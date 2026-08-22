"""
Tests for COMP-MC-001 ProtocolHandler.

leaf_id : COMP-MC-001
req_id  : REQ-L2-MC-005 (transport), REQ-L2-MC-006 (API-key auth),
          REQ-L2-MC-011 (structured error response)

Covers:
- JSON-RPC frame validation (INVALID_REQUEST on malformed)
- Parse error detection
- API-key extraction from params and headers
- Missing API key → AUTH_FAILED
- Successful dispatch path (mocked ToolRegistry)
- Error from ToolRegistry propagated correctly
- Response ID matching
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock


from mcp_server.protocol_handler import (
    ErrorFormatter,
    HttpTransportAdapter,
    JsonRpcValidator,
    ProtocolHandler,
    SseTransportAdapter,
    StdioTransportAdapter,
    ToolResult,
)


# ---------------------------------------------------------------------------
# JsonRpcValidator tests
# ---------------------------------------------------------------------------


class TestJsonRpcValidator:
    def test_valid_frame_returns_none(self):
        frame = {"jsonrpc": "2.0", "method": "requirement.get", "id": 1, "params": {}}
        assert JsonRpcValidator.validate(frame) is None

    def test_missing_jsonrpc_key(self):
        frame = {"method": "requirement.get", "id": 1}
        assert JsonRpcValidator.validate(frame) == "INVALID_REQUEST"

    def test_wrong_jsonrpc_version(self):
        frame = {"jsonrpc": "1.0", "method": "requirement.get", "id": 1}
        assert JsonRpcValidator.validate(frame) == "INVALID_REQUEST"

    def test_missing_method(self):
        frame = {"jsonrpc": "2.0", "id": 1}
        assert JsonRpcValidator.validate(frame) == "INVALID_REQUEST"

    def test_empty_method(self):
        frame = {"jsonrpc": "2.0", "method": "", "id": 1}
        assert JsonRpcValidator.validate(frame) == "INVALID_REQUEST"

    def test_missing_id(self):
        frame = {"jsonrpc": "2.0", "method": "requirement.get"}
        assert JsonRpcValidator.validate(frame) == "INVALID_REQUEST"

    def test_non_dict_frame(self):
        assert JsonRpcValidator.validate("not a dict") == "INVALID_REQUEST"
        assert JsonRpcValidator.validate(None) == "INVALID_REQUEST"


# ---------------------------------------------------------------------------
# ErrorFormatter tests
# ---------------------------------------------------------------------------


class TestErrorFormatter:
    def test_format_error_known_code(self):
        body = ErrorFormatter.format_error("AUTH_FAILED")
        assert body["code"] == -32000  # JSON-RPC 2.0 error code for AUTH_FAILED
        assert isinstance(body["code"], int)
        assert "message" in body
        assert "details" not in body

    def test_format_error_with_details(self):
        body = ErrorFormatter.format_error("VALIDATION_ERROR", details={"field": "id"})
        assert body["code"] == -32602  # Invalid params
        assert body["details"] == {"field": "id"}

    def test_format_jsonrpc_error(self):
        frame = ErrorFormatter.format_jsonrpc_error(42, "AUTH_FAILED")
        assert frame["jsonrpc"] == "2.0"
        assert frame["id"] == 42
        assert "error" in frame
        assert frame["error"]["code"] == -32000  # JSON-RPC 2.0 error code
        assert isinstance(frame["error"]["code"], int)
        assert isinstance(frame["error"]["message"], str)

    def test_format_jsonrpc_result(self):
        frame = ErrorFormatter.format_jsonrpc_result(7, {"data": "ok"})
        assert frame["jsonrpc"] == "2.0"
        assert frame["id"] == 7
        assert frame["result"] == {"data": "ok"}


# ---------------------------------------------------------------------------
# HttpTransportAdapter tests
# ---------------------------------------------------------------------------


class TestHttpTransportAdapter:
    def test_read_valid_json(self):
        body = json.dumps({"jsonrpc": "2.0", "method": "tool", "id": 1}).encode()
        adapter = HttpTransportAdapter(body=body)
        frame = adapter.read_request()
        assert frame is not None
        assert frame["method"] == "tool"

    def test_read_invalid_json_returns_parse_error_marker(self):
        adapter = HttpTransportAdapter(body=b"not json")
        frame = adapter.read_request()
        assert frame.get("_parse_error") is True

    def test_write_response_stores_result(self):
        adapter = HttpTransportAdapter(body=b"{}")
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
        adapter.write_response(response)
        assert adapter.get_response() == response

    def test_extract_api_key_from_header(self):
        body = json.dumps({"jsonrpc": "2.0", "method": "x", "id": 1}).encode()
        headers = {"HTTP_X_API_KEY": "reqlo_testkey"}
        adapter = HttpTransportAdapter(body=body, headers=headers)
        frame = adapter.read_request()
        assert adapter.extract_api_key(frame, headers) == "reqlo_testkey"

    def test_extract_api_key_from_params_is_rejected_on_http(self):
        """HTTP transport must NOT honour ``params.api_key`` (D-1 / REQ-018).

        Accepting the key from the JSON-RPC body on a transport that has a
        header mechanism available exposes it to the same logging/proxy
        risk the ``?api_key=`` query-string fallback is already rejected
        for. Only stdio (no header channel) may use ``params.api_key``.
        """
        body = json.dumps({
            "jsonrpc": "2.0", "method": "x", "id": 1,
            "params": {"api_key": "reqlo_fromparams"}
        }).encode()
        adapter = HttpTransportAdapter(body=body)
        frame = adapter.read_request()
        assert adapter.extract_api_key(frame, {}) is None


# ---------------------------------------------------------------------------
# Transport restriction on ``params.api_key`` (D-1 / REQ-018)
# ---------------------------------------------------------------------------


class TestApiKeyTransportRestriction:
    """``params.api_key`` is a valid key source only on stdio.

    stdio has no header mechanism, so it legitimately needs the JSON-RPC
    body as its key channel (existing behaviour, preserved). HTTP and SSE
    both have a header mechanism (``Authorization`` / ``X-API-Key``), so a
    body-only key on those transports is now treated as absent — the same
    policy the query-string ``?api_key=`` fallback is already held to.
    """

    def test_stdio_extracts_key_from_params_without_header(self):
        frame = {
            "jsonrpc": "2.0", "method": "x", "id": 1,
            "params": {"api_key": "reqlo_stdiokey"},
        }
        adapter = StdioTransportAdapter()
        assert adapter.extract_api_key(frame, {}) == "reqlo_stdiokey"

    def test_http_does_not_extract_key_from_params_without_header(self):
        frame = {
            "jsonrpc": "2.0", "method": "x", "id": 1,
            "params": {"api_key": "reqlo_httpkey"},
        }
        adapter = HttpTransportAdapter(body=b"{}")
        assert adapter.extract_api_key(frame, {}) is None

    def test_sse_does_not_extract_key_from_params_without_header(self):
        frame = {
            "jsonrpc": "2.0", "method": "x", "id": 1,
            "params": {"api_key": "reqlo_ssekey"},
        }
        adapter = SseTransportAdapter(body=b"{}")
        assert adapter.extract_api_key(frame, {}) is None

    def test_http_request_with_only_params_api_key_fails_like_missing_key(self):
        """End-to-end: HTTP body-only key must fail the same way a
        genuinely-missing key does — no new error code (task constraint)."""
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)

        body_with_params_key = json.dumps({
            "jsonrpc": "2.0", "method": "requirement.get", "id": 1,
            "params": {"api_key": "reqlo_httpkey"},
        }).encode()
        body_missing_key = json.dumps({
            "jsonrpc": "2.0", "method": "requirement.get", "id": 1,
            "params": {},
        }).encode()

        response_with_params_key = handler.handle_http_request(body=body_with_params_key)
        response_missing_key = handler.handle_http_request(body=body_missing_key)

        assert response_with_params_key["error"]["code"] == response_missing_key["error"]["code"]
        assert response_with_params_key["error"]["code"] == -32000  # AUTH_FAILED
        registry.dispatch_request.assert_not_called()


# ---------------------------------------------------------------------------
# ProtocolHandler tests
# ---------------------------------------------------------------------------


def _make_registry_mock(return_result: ToolResult) -> MagicMock:
    registry = MagicMock()
    registry.dispatch_request.return_value = return_result
    return registry


def _make_valid_body(method: str = "requirement.get", request_id: int = 1, extra_params: dict = None) -> bytes:
    params = {"api_key": "reqlo_validkey"}
    if extra_params:
        params.update(extra_params)
    frame = {"jsonrpc": "2.0", "method": method, "id": request_id, "params": params}
    return json.dumps(frame).encode()


# HTTP transport no longer honours ``params.api_key`` (stdio-only, see
# TestApiKeyTransportRestriction below) — HTTP-based ProtocolHandler tests
# that exercise the post-auth dispatch path must supply the key via header.
_AUTH_HEADERS = {"HTTP_AUTHORIZATION": "Bearer reqlo_validkey"}


class TestProtocolHandler:

    def test_parse_error_on_invalid_body(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        response = handler.handle_http_request(body=b"not-json")
        assert "error" in response
        assert response["error"]["code"] == -32700  # JSON-RPC Parse error
        registry.dispatch_request.assert_not_called()

    def test_invalid_request_on_bad_frame(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        body = json.dumps({"method": "x", "id": 1}).encode()  # missing jsonrpc
        response = handler.handle_http_request(body=body)
        assert response["error"]["code"] == -32600  # JSON-RPC Invalid Request
        registry.dispatch_request.assert_not_called()

    def test_missing_api_key_returns_auth_failed(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        body = json.dumps({"jsonrpc": "2.0", "method": "requirement.get", "id": 1, "params": {}}).encode()
        response = handler.handle_http_request(body=body)
        assert response["error"]["code"] == -32000  # JSON-RPC server error: AUTH_FAILED
        registry.dispatch_request.assert_not_called()

    def test_successful_dispatch_returns_result(self):
        registry = _make_registry_mock(ToolResult.ok({"requirement": {"id": "abc"}}))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body("requirement.get", request_id=99)
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        assert "result" in response
        assert response["id"] == 99
        assert response["result"]["requirement"]["id"] == "abc"

    def test_tool_error_propagated_to_response(self):
        registry = _make_registry_mock(ToolResult.error("NOT_FOUND", "Requirement not found"))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body("requirement.get", request_id=3)
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        assert "error" in response
        assert response["error"]["code"] == -32004  # JSON-RPC server error: NOT_FOUND
        assert response["id"] == 3

    def test_api_key_stripped_from_params_before_dispatch(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body("requirement.get", extra_params={"id": "some-uuid"})
        handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        call_kwargs = registry.dispatch_request.call_args
        dispatched_params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert "api_key" not in dispatched_params

    def test_id_preserved_in_response(self):
        registry = _make_registry_mock(ToolResult.ok({"x": 1}))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body(request_id="string-id-42")
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        assert response["id"] == "string-id-42"

    def test_registry_exception_returns_internal_error(self):
        registry = MagicMock()
        registry.dispatch_request.side_effect = RuntimeError("DB down")
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body()
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        assert response["error"]["code"] == -32603  # JSON-RPC Internal error

    def test_tools_list_exception_masks_detail_but_logs_it(self, caplog):
        """CWE-209 regression: an unexpected exception from ``list_tools``
        must reach the client as the generic INTERNAL_ERROR message, never
        as ``str(exc)`` — the real exception must still be logged for
        operators (same pattern as Task 5's REST/MCP fixes elsewhere)."""
        sensitive_detail = (
            "psycopg2.OperationalError: FATAL: password authentication "
            "failed for user \"reqogniloom\" (host=10.0.0.5)"
        )
        registry = MagicMock()
        registry.list_tools.side_effect = RuntimeError(sensitive_detail)
        handler = ProtocolHandler(tool_registry=registry)
        body = json.dumps(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 5, "params": {}}
        ).encode()

        with caplog.at_level("ERROR"):
            response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)

        assert response["error"]["code"] == -32603  # JSON-RPC Internal error
        assert sensitive_detail not in response["error"]["message"]
        assert response["error"]["message"] == "An internal server error occurred."
        assert sensitive_detail in caplog.text


def _make_tools_call_body(
    tool_name: str, arguments: dict = None, request_id: int = 1
) -> bytes:
    """Build a standard MCP ``tools/call`` request body."""
    frame = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": request_id,
        "params": {
            "api_key": "reqlo_validkey",
            "name": tool_name,
            "arguments": arguments or {},
        },
    }
    return json.dumps(frame).encode()


class TestToolsCallIsError:
    """REQ-086 / F8.2: tool-execution errors surface as isError results."""

    def test_tool_execution_error_returned_as_iserror_result(self):
        registry = _make_registry_mock(
            ToolResult.error("NOT_FOUND", "Requirement not found")
        )
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_tools_call_body("requirement.get", {"id": "x"}, request_id=7)
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)

        # Successful JSON-RPC response, error carried inside the result.
        assert "error" not in response
        assert response["id"] == 7
        assert response["result"]["isError"] is True
        content = response["result"]["content"]
        assert content[0]["type"] == "text"
        assert "Requirement not found" in content[0]["text"]

    def test_validation_error_is_iserror_result_under_tools_call(self):
        registry = _make_registry_mock(
            ToolResult.error("VALIDATION_ERROR", "bad field")
        )
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_tools_call_body("requirement.create", {}, request_id=8)
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        assert "error" not in response
        assert response["result"]["isError"] is True

    def test_permission_denied_stays_jsonrpc_error_under_tools_call(self):
        registry = _make_registry_mock(
            ToolResult.error("PERMISSION_DENIED", "no access")
        )
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_tools_call_body("requirement.create", {}, request_id=9)
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        # Protocol-level error remains a JSON-RPC error.
        assert "result" not in response
        assert response["error"]["code"] == -32001  # PERMISSION_DENIED

    def test_success_under_tools_call_has_no_iserror_flag(self):
        registry = _make_registry_mock(ToolResult.ok({"requirement": {"id": "abc"}}))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_tools_call_body("requirement.get", {"id": "abc"}, request_id=10)
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        assert "error" not in response
        assert "isError" not in response["result"]

    def test_tool_error_direct_dispatch_stays_jsonrpc_error(self):
        # Direct-method dispatch (not tools/call) keeps the legacy contract.
        registry = _make_registry_mock(
            ToolResult.error("NOT_FOUND", "Requirement not found")
        )
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body("requirement.get", request_id=11)
        response = handler.handle_http_request(body=body, headers=_AUTH_HEADERS)
        assert "result" not in response
        assert response["error"]["code"] == -32004  # NOT_FOUND
