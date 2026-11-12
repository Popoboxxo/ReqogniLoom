"""Tests for the stdlib MCP probe.

The probe's transport is injectable, so these tests drive the protocol logic
with a small fake instead of a socket: deterministic, fast, and independent of
the runner's socket policy. The real HTTP layer (`HttpTransport`) stays a thin
wrapper around `urllib`.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pytest

from mcp_probe import ProbeResult, _Response, endpoint_url, probe

Responder = Callable[[dict[str, Any]], tuple[int, Any, str]]


def _json(payload: dict[str, Any], status: int = 200) -> tuple[int, Any, str]:
    return status, payload, "application/json"


def _default_responder(frame: dict[str, Any]) -> tuple[int, Any, str]:
    method = frame.get("method")
    if method == "initialize":
        return _json(
            {
                "jsonrpc": "2.0",
                "id": frame.get("id"),
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "stub", "version": "0"},
                },
            }
        )
    if method == "notifications/initialized":
        return 202, None, "application/json"
    if method == "tools/list":
        return _json(
            {
                "jsonrpc": "2.0",
                "id": frame.get("id"),
                "result": {
                    "tools": [
                        {"name": "requirement.query"},
                        {"name": "artifact_search"},
                        {"name": "memory_search"},
                    ]
                },
            }
        )
    if method == "tools/call":
        return _json(
            {
                "jsonrpc": "2.0",
                "id": frame.get("id"),
                "result": {"items": [{"id": "REQ-1"}]},
            }
        )
    return 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600}}, "application/json"


class FakeTransport:
    def __init__(self, responder: Responder = _default_responder, discovery_status: int = 405):
        self.responder = responder
        self.discovery_status = discovery_status
        self.posted: list[dict[str, Any]] = []

    def post(self, frame: dict[str, Any], timeout: float | None = None) -> _Response:
        self.posted.append(frame)
        status, payload, content_type = self.responder(frame)
        if payload is None:
            body = b""
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = json.dumps(payload).encode("utf-8")
        return _Response(status, content_type, body)

    def get(self, timeout: float | None = None, *, sse: bool = False) -> _Response:
        return _Response(self.discovery_status, "text/event-stream", b"")


def _probe(transport: FakeTransport, **kwargs: Any) -> ProbeResult:
    return probe("http://stub/mcp/", "k", transport=transport, **kwargs)


def test_endpoint_url_accepts_a_base_or_the_full_endpoint() -> None:
    assert endpoint_url("http://host:8001") == "http://host:8001/mcp/"
    assert endpoint_url("http://host:8001/") == "http://host:8001/mcp/"
    assert endpoint_url("http://host:8001/mcp/") == "http://host:8001/mcp/"


def test_probe_ok_against_fake_transport() -> None:
    result = _probe(FakeTransport())

    assert result.ok()
    assert result.initialize_ok and result.initialized_ok and result.call_ok
    assert result.tool_count == 3 and result.has_tool
    assert result.call_result_count == 1
    assert result.errors == []
    assert result.latency_ms.keys() >= {
        "initialize",
        "initialized",
        "discovery_get",
        "tools_list",
        "tools_call",
    }


def test_probe_follows_tools_list_pagination() -> None:
    def responder(frame: dict[str, Any]) -> tuple[int, Any, str]:
        if frame.get("method") == "tools/list":
            cursor = (frame.get("params") or {}).get("cursor")
            if cursor is None:
                return _json(
                    {
                        "jsonrpc": "2.0",
                        "id": frame.get("id"),
                        "result": {
                            "tools": [{"name": "requirement.query"}],
                            "nextCursor": "page-2",
                        },
                    }
                )
            return _json(
                {
                    "jsonrpc": "2.0",
                    "id": frame.get("id"),
                    "result": {"tools": [{"name": "artifact_search"}]},
                }
            )
        return _default_responder(frame)

    transport = FakeTransport(responder)
    result = _probe(transport)

    assert result.tool_count == 2
    assert result.has_tool
    assert result.ok()
    assert any(
        frame.get("params", {}).get("cursor") == "page-2" for frame in transport.posted
    )


def test_probe_reports_401_without_crash() -> None:
    def responder(frame: dict[str, Any]) -> tuple[int, Any, str]:
        return (
            401,
            {
                "jsonrpc": "2.0",
                "id": frame.get("id"),
                "error": {"code": -32001, "error_code": "AUTH_FAILED"},
            },
            "application/json",
        )

    result = _probe(FakeTransport(responder))

    assert not result.initialize_ok
    assert not result.ok()
    assert any("401" in error for error in result.errors)
    # A bad key stops the probe: no catalogue or call is attempted afterwards.
    assert result.tool_count == 0


def test_probe_treats_405_on_sse_get_as_clean() -> None:
    """405 is the documented answer for an SSE GET (H1/H5.2), not a failure."""
    result = _probe(FakeTransport(discovery_status=405), sse_timeout=0.5)

    assert result.sse_status == 405
    assert result.errors == []
    assert result.ok()


def test_probe_tolerates_a_200_discovery_get() -> None:
    result = _probe(FakeTransport(discovery_status=200), sse_timeout=0.5)

    assert result.sse_status == 200
    assert result.errors == []


def test_probe_empty_data_is_separate_from_call_failure() -> None:
    def responder(frame: dict[str, Any]) -> tuple[int, Any, str]:
        if frame.get("method") == "tools/call":
            return _json(
                {"jsonrpc": "2.0", "id": frame.get("id"), "result": {"items": []}}
            )
        return _default_responder(frame)

    result = _probe(FakeTransport(responder))

    assert result.call_ok
    assert result.call_result_count == 0
    assert result.errors == []


def test_probe_reports_tool_call_error_as_error() -> None:
    def responder(frame: dict[str, Any]) -> tuple[int, Any, str]:
        if frame.get("method") == "tools/call":
            return _json(
                {
                    "jsonrpc": "2.0",
                    "id": frame.get("id"),
                    "error": {"code": -32602, "error_code": "VALIDATION_ERROR"},
                }
            )
        return _default_responder(frame)

    result = _probe(FakeTransport(responder))

    assert not result.call_ok
    assert not result.ok()
    assert any("tools/call error" in error for error in result.errors)


def test_probe_reads_sse_framed_bodies() -> None:
    def responder(frame: dict[str, Any]) -> tuple[int, Any, str]:
        if frame.get("method") == "tools/list":
            frame_json = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": frame.get("id"),
                    "result": {"tools": [{"name": "requirement.query"}]},
                }
            )
            return 200, f"data: {frame_json}\n\n", "text/event-stream"
        return _default_responder(frame)

    result = _probe(FakeTransport(responder))

    assert result.has_tool
    assert result.tool_count == 1


@pytest.mark.parametrize("body", [b"", b"   "])
def test_probe_handles_an_empty_body(body: bytes) -> None:
    transport = FakeTransport()
    response = _Response(200, "application/json", body)

    assert response.json() is None


def test_probe_cli_requires_url_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_probe import main

    monkeypatch.delenv("REQOGNILOOM_MCP_URL", raising=False)
    monkeypatch.delenv("REQOGNILOOM_API_KEY", raising=False)
    assert main([]) == 2

    monkeypatch.setenv("REQOGNILOOM_MCP_URL", "http://stub/mcp/")
    assert main([]) == 2  # still no key

    monkeypatch.setenv("REQOGNILOOM_API_KEY", "k")
    monkeypatch.setattr("mcp_probe.probe", lambda *a, **kw: ProbeResult())
    assert main(["--url", "http://stub/mcp/"]) == 1
