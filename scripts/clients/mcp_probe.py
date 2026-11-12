#!/usr/bin/env python3
"""Probe the ReqogniLoom MCP endpoint over streamable HTTP.

Why this exists: the client smoke runs (`scripts/clients/verify.sh`) only prove
that a client can *list* the server. This probe talks the JSON-RPC protocol
directly, so the server side is verified independently of any client version.

Transport reality (checked against ``backend/mcp_server/views.py``):

- ``POST /mcp/`` speaks JSON-RPC 2.0 and answers ``application/json``; a
  notification (no ``id``) is acknowledged with an empty ``202``.
- ``GET /mcp/`` with ``Accept: text/event-stream`` answers **405 by design**
  (``McpHttpTransportView.get``, H1/H5.2): advertising a stream the app does not
  serve made MCP clients reconnect-loop. The probe therefore records the status
  and does not treat 405 as a failure.

The probe only performs read-only work: ``initialize``, ``initialized``,
``tools/list`` and one ``tools/call`` (``requirement_query`` by default). Every
exception becomes an entry in ``errors``; the probe never raises.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

MCP_PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "reqlo-mcp-probe", "version": "1.0.0"}


@dataclass
class ProbeResult:
    """Outcome of one probe run.

    ``call_ok`` means "the tool call returned a JSON-RPC result", not "the
    workspace has data". An empty workspace is a valid, successful call — the
    two are deliberately separate.
    """

    initialize_ok: bool = False
    initialized_ok: bool = False
    sse_status: int | None = None
    tool_count: int = 0
    has_tool: bool = False
    call_ok: bool = False
    call_result_count: int | None = None
    tool_names: list[str] = field(default_factory=list)
    latency_ms: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        """Exit-code truth: protocol handshake, catalogue and call worked."""
        return (
            self.initialize_ok
            and self.tool_count > 0
            and self.has_tool
            and self.call_ok
        )


class _Response:
    def __init__(self, status: int, content_type: str, body: bytes):
        self.status = status
        self.content_type = content_type
        self.body = body

    def json(self) -> Any:
        """Parse the body, tolerating SSE framing (``data: {...}``)."""
        text = self.body.decode("utf-8", "replace")
        if "text/event-stream" in self.content_type or text.lstrip().startswith("data:"):
            payloads = [
                line[len("data:") :].strip()
                for line in text.splitlines()
                if line.startswith("data:")
            ]
            for payload in payloads:
                if payload and payload != "[DONE]":
                    return json.loads(payload)
            return None
        return json.loads(text) if text.strip() else None


class HttpTransport:
    """Thin JSON-RPC-over-HTTP transport (urllib, stdlib only).

    The probe takes an instance of this by default; tests inject a fake with the
    same two methods, so the protocol logic is testable without a network.
    """

    def __init__(self, url: str, api_key: str, timeout: float = 15.0) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout = timeout

    def post(self, frame: dict[str, Any], timeout: float | None = None) -> "_Response":
        body = json.dumps(frame).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                # The server accepts X-API-Key or Authorization; header only.
                "X-API-Key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return _Response(
                    response.status,
                    response.headers.get("Content-Type", ""),
                    response.read(),
                )
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.headers.get("Content-Type", ""), exc.read())

    def get(self, timeout: float | None = None, *, sse: bool = False) -> "_Response":
        headers = {"X-API-Key": self.api_key}
        if sse:
            headers["Accept"] = "text/event-stream"
        request = urllib.request.Request(self.url, method="GET", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return _Response(
                    response.status,
                    response.headers.get("Content-Type", ""),
                    response.read(),
                )
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.headers.get("Content-Type", ""), exc.read())


def _result_count(result: Any) -> int | None:
    """Count rows in a tool result, without assuming one envelope shape."""
    if result is None:
        return None
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        for key in ("items", "results", "requirements", "entries"):
            value = result.get(key)
            if isinstance(value, list):
                return len(value)
        # Fall back to the first list-valued key, but never invent a number.
        for value in result.values():
            if isinstance(value, list):
                return len(value)
    return None


def probe(
    url: str,
    api_key: str,
    *,
    tool: str = "requirement_query",
    sse_timeout: float = 5.0,
    workspace_id: str | None = None,
    timeout: float = 15.0,
    transport: Any = None,
) -> ProbeResult:
    """Run the read-only probe against ``url`` (the ``/mcp/`` endpoint).

    ``transport`` is injectable for tests; it must provide ``post(frame,
    timeout)`` and ``get(timeout, sse=...)`` returning an object with
    ``status``, ``content_type`` and ``json()``.
    """
    client = transport or HttpTransport(url, api_key, timeout)
    result = ProbeResult()

    started = time.perf_counter()
    response = client.post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        },
        timeout,
    )
    result.latency_ms["initialize"] = round((time.perf_counter() - started) * 1000, 1)
    if response.status == 200:
        frame = response.json() or {}
        result.initialize_ok = "result" in frame
        if not result.initialize_ok:
            result.errors.append(f"initialize returned no result: {frame.get('error')}")
    else:
        result.errors.append(f"initialize failed with HTTP {response.status}")
        # A 401 is the expected answer for a bad key: report it and stop
        # cleanly instead of hammering the endpoint with the remaining steps.
        return result

    started = time.perf_counter()
    notification = client.post(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    result.latency_ms["initialized"] = round((time.perf_counter() - started) * 1000, 1)
    # The server acknowledges notifications with an empty 202 (REQ-108).
    result.initialized_ok = notification.status in (200, 202, 204)
    if not result.initialized_ok:
        result.errors.append(
            f"notifications/initialized failed with HTTP {notification.status}"
        )

    # Discovery GET: 405 is the documented, deliberate answer for an SSE accept.
    started = time.perf_counter()
    discovery = client.get(sse_timeout, sse=True)
    result.latency_ms["discovery_get"] = round((time.perf_counter() - started) * 1000, 1)
    result.sse_status = discovery.status
    if discovery.status not in (200, 405):
        result.errors.append(f"discovery GET returned HTTP {discovery.status}")

    # tools/list, following nextCursor until the catalogue is complete.
    cursor: str | None = None
    names: list[str] = []
    started = time.perf_counter()
    while True:
        params: dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        listing = client.post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": params}
        )
        if listing.status != 200:
            result.errors.append(f"tools/list failed with HTTP {listing.status}")
            break
        frame = listing.json() or {}
        payload = frame.get("result") or {}
        for entry in payload.get("tools", []) or []:
            name = entry.get("name")
            if isinstance(name, str):
                names.append(name)
        cursor = payload.get("nextCursor")
        if not cursor:
            break
    result.latency_ms["tools_list"] = round((time.perf_counter() - started) * 1000, 1)
    result.tool_names = names
    result.tool_count = len(names)
    result.has_tool = tool in names

    # tools/call — read-only by contract.
    arguments: dict[str, Any] = {}
    if workspace_id:
        arguments["workspace_id"] = workspace_id
    started = time.perf_counter()
    call = client.post(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
    )
    result.latency_ms["tools_call"] = round((time.perf_counter() - started) * 1000, 1)
    if call.status == 200:
        frame = call.json() or {}
        if "error" in frame and frame["error"]:
            result.errors.append(f"tools/call error: {frame['error']}")
        else:
            result.call_ok = "result" in frame
            result.call_result_count = _result_count(frame.get("result"))
            if not result.call_ok:
                result.errors.append("tools/call returned no result")
    else:
        result.errors.append(f"tools/call failed with HTTP {call.status}")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("REQOGNILOOM_MCP_URL", ""))
    parser.add_argument("--key-env", default="REQOGNILOOM_API_KEY")
    parser.add_argument("--tool", default="requirement_query")
    parser.add_argument("--workspace-id", default=None)
    parser.add_argument("--sse-timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if not args.url:
        print("--url or REQOGNILOOM_MCP_URL is required", file=sys.stderr)
        return 2
    api_key = os.environ.get(args.key_env, "")
    if not api_key:
        print(f"environment variable {args.key_env} is empty", file=sys.stderr)
        return 2

    result = probe(
        args.url,
        api_key,
        tool=args.tool,
        sse_timeout=args.sse_timeout,
        workspace_id=args.workspace_id,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok(),
                    "initialize_ok": result.initialize_ok,
                    "initialized_ok": result.initialized_ok,
                    "sse_status": result.sse_status,
                    "tool_count": result.tool_count,
                    "has_tool": result.has_tool,
                    "call_ok": result.call_ok,
                    "call_result_count": result.call_result_count,
                    "latency_ms": result.latency_ms,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
    else:
        print(f"initialize: {'ok' if result.initialize_ok else 'FAILED'}")
        print(f"initialized: {'ok' if result.initialized_ok else 'FAILED'}")
        print(f"discovery GET: HTTP {result.sse_status}")
        print(f"tools: {result.tool_count} (tool {args.tool!r}: {result.has_tool})")
        print(
            "call: "
            + ("ok" if result.call_ok else "FAILED")
            + (
                f", {result.call_result_count} row(s)"
                if result.call_result_count is not None
                else ""
            )
        )
        print("latency (ms): " + json.dumps(result.latency_ms))
        for error in result.errors:
            print(f"error: {error}")

    return 0 if result.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
