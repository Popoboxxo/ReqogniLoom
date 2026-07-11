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
        assert body["error_code"] == "AUTH_FAILED"
        assert "message" in body
        assert "details" not in body

    def test_format_error_with_details(self):
        body = ErrorFormatter.format_error("VALIDATION_ERROR", details={"field": "id"})
        assert body["details"] == {"field": "id"}

    def test_format_jsonrpc_error(self):
        frame = ErrorFormatter.format_jsonrpc_error(42, "AUTH_FAILED")
        assert frame["jsonrpc"] == "2.0"
        assert frame["id"] == 42
        assert "error" in frame
        assert frame["error"]["error_code"] == "AUTH_FAILED"

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
        headers = {"HTTP_X_API_KEY": "rf_testkey"}
        adapter = HttpTransportAdapter(body=body, headers=headers)
        frame = adapter.read_request()
        assert adapter.extract_api_key(frame, headers) == "rf_testkey"

    def test_extract_api_key_from_params(self):
        body = json.dumps({
            "jsonrpc": "2.0", "method": "x", "id": 1,
            "params": {"api_key": "rf_fromparams"}
        }).encode()
        adapter = HttpTransportAdapter(body=body)
        frame = adapter.read_request()
        assert adapter.extract_api_key(frame, {}) == "rf_fromparams"


# ---------------------------------------------------------------------------
# ProtocolHandler tests
# ---------------------------------------------------------------------------


def _make_registry_mock(return_result: ToolResult) -> MagicMock:
    registry = MagicMock()
    registry.dispatch_request.return_value = return_result
    return registry


def _make_valid_body(method: str = "requirement.get", request_id: int = 1, extra_params: dict = None) -> bytes:
    params = {"api_key": "rf_validkey"}
    if extra_params:
        params.update(extra_params)
    frame = {"jsonrpc": "2.0", "method": method, "id": request_id, "params": params}
    return json.dumps(frame).encode()


class TestProtocolHandler:

    def test_parse_error_on_invalid_body(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        response = handler.handle_http_request(body=b"not-json")
        assert "error" in response
        assert response["error"]["error_code"] == "PARSE_ERROR"
        registry.dispatch_request.assert_not_called()

    def test_invalid_request_on_bad_frame(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        body = json.dumps({"method": "x", "id": 1}).encode()  # missing jsonrpc
        response = handler.handle_http_request(body=body)
        assert response["error"]["error_code"] == "INVALID_REQUEST"
        registry.dispatch_request.assert_not_called()

    def test_missing_api_key_returns_auth_failed(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        body = json.dumps({"jsonrpc": "2.0", "method": "requirement.get", "id": 1, "params": {}}).encode()
        response = handler.handle_http_request(body=body)
        assert response["error"]["error_code"] == "AUTH_FAILED"
        registry.dispatch_request.assert_not_called()

    def test_successful_dispatch_returns_result(self):
        registry = _make_registry_mock(ToolResult.ok({"requirement": {"id": "abc"}}))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body("requirement.get", request_id=99)
        response = handler.handle_http_request(body=body)
        assert "result" in response
        assert response["id"] == 99
        assert response["result"]["requirement"]["id"] == "abc"

    def test_tool_error_propagated_to_response(self):
        registry = _make_registry_mock(ToolResult.error("NOT_FOUND", "Requirement not found"))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body("requirement.get", request_id=3)
        response = handler.handle_http_request(body=body)
        assert "error" in response
        assert response["error"]["error_code"] == "NOT_FOUND"
        assert response["id"] == 3

    def test_api_key_stripped_from_params_before_dispatch(self):
        registry = _make_registry_mock(ToolResult.ok({}))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body("requirement.get", extra_params={"id": "some-uuid"})
        handler.handle_http_request(body=body)
        call_kwargs = registry.dispatch_request.call_args
        dispatched_params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert "api_key" not in dispatched_params

    def test_id_preserved_in_response(self):
        registry = _make_registry_mock(ToolResult.ok({"x": 1}))
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body(request_id="string-id-42")
        response = handler.handle_http_request(body=body)
        assert response["id"] == "string-id-42"

    def test_registry_exception_returns_internal_error(self):
        registry = MagicMock()
        registry.dispatch_request.side_effect = RuntimeError("DB down")
        handler = ProtocolHandler(tool_registry=registry)
        body = _make_valid_body()
        response = handler.handle_http_request(body=body)
        assert response["error"]["error_code"] == "INTERNAL_ERROR"
