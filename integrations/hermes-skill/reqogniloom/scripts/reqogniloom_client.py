#!/usr/bin/env python3
"""Command-line connector for ReqogniLoom over REST and MCP.

Loaded as a Hermes skill script and usable from any surface (TUI, web, CLI,
desktop). Standard library only, so it runs wherever Hermes runs.

Configuration is read exclusively from the environment:

* ``REQOGNILOOM_BASE_URL``     - server origin (default ``http://localhost:8001``)
* ``REQOGNILOOM_API_KEY``      - ``reqlo_...`` key, sent as the ``X-API-Key`` header
* ``REQOGNILOOM_WORKSPACE_ID`` - optional default workspace (informational only)

Examples::

    python scripts/reqogniloom_client.py list-workspaces
    python scripts/reqogniloom_client.py mcp --tool requirement_query \\
        --params '{"workspace_id": "00000000-0000-0000-0000-000000000000"}'

Every server error shape is normalised to a single ``code: message`` line on
stderr; the process exits with code 1 and never prints a traceback.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8001"
REQUEST_TIMEOUT_SECONDS = 10
WORKSPACES_PATH = "/api/v1/workspaces/"
MCP_PATH = "/mcp/"

EXIT_OK = 0
EXIT_ERROR = 1


class ReqogniLoomError(RuntimeError):
    """A transport failure or a server-reported error, already normalised."""


def _env(name: str, default: str = "") -> str:
    """Return a stripped environment value, or *default* when unset/blank."""
    return (os.environ.get(name) or default).strip()


def _join_error(code: Any, message: Any) -> str:
    """Join an error code and message into one readable line."""
    code_text = "" if code is None else str(code).strip()
    message_text = "" if message is None else str(message).strip()
    if code_text and message_text:
        return f"{code_text}: {message_text}"
    return code_text or message_text or "unknown server error"


def normalize_error(payload: Any) -> str | None:
    """Normalise either server error shape to ``code: message``, else ``None``.

    * nested: ``{"error": {"code": ..., "message": ...}}`` (REST envelope and
      JSON-RPC error frames)
    * flat:   ``{"error": "invalid_api_key", "message": ...}``
    """
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        if code is None and not message:
            return None
        return _join_error(code, message)
    if isinstance(error, str) and error:
        return _join_error(error, payload.get("message"))
    return None


def raise_for_error(payload: Any) -> None:
    """Raise :class:`ReqogniLoomError` when *payload* carries an error."""
    normalized = normalize_error(payload)
    if normalized is not None:
        raise ReqogniLoomError(normalized)


def _mcp_error_text(result: dict[str, Any]) -> str:
    """Extract the human-readable text from an MCP ``isError`` result."""
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text = block["text"].strip()
                if text.startswith("Error:"):
                    text = text[len("Error:"):].strip()
                return text or "tool reported an error"
    return "tool reported an error"


def extract_mcp_result(payload: Any) -> Any:
    """Return the printable ``result`` of a JSON-RPC response.

    Raises :class:`ReqogniLoomError` for JSON-RPC error frames and for MCP
    tool-execution errors. Tool-execution errors arrive as HTTP 200 with
    ``result.isError`` set, so they have to be detected inside the body rather
    than from the status.
    """
    if not isinstance(payload, dict):
        raise ReqogniLoomError("unexpected MCP response: expected a JSON object")
    raise_for_error(payload)
    if "result" not in payload:
        raise ReqogniLoomError("unexpected MCP response: no 'result' field")
    result = payload["result"]
    if isinstance(result, dict) and result.get("isError") is True:
        raise ReqogniLoomError(_mcp_error_text(result))
    return result


def parse_params(raw: str) -> dict[str, Any]:
    """Parse the ``--params`` argument into a JSON object."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReqogniLoomError(
            f"--params is not valid JSON: {getattr(exc, 'msg', exc)}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ReqogniLoomError("--params must be a JSON object")
    return parsed


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    """Read and normalise the body of an HTTP error response."""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - a broken body must not mask the status
        raw = ""
    payload: Any = None
    if raw:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            payload = None
    normalized = normalize_error(payload)
    if normalized is not None:
        return f"HTTP {exc.code}: {normalized}"
    detail = raw.strip() or str(exc.reason)
    return f"HTTP {exc.code}: {detail}"


def _decode_json(raw: str, url: str) -> Any:
    """Decode a response body, rejecting non-JSON output."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReqogniLoomError(f"non-JSON response from {url}") from exc


class ReqogniLoomClient:
    """Minimal REST/MCP client bound to environment configuration.

    ``base_url``, ``api_key`` and ``workspace_id`` may be passed explicitly
    (used by tests); otherwise they are read from the environment.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self.base_url = (
            base_url or _env("REQOGNILOOM_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else _env("REQOGNILOOM_API_KEY")
        self.workspace_id = (
            workspace_id if workspace_id is not None else _env("REQOGNILOOM_WORKSPACE_ID")
        )

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        """Perform one API call and return the decoded JSON payload."""
        if not self.api_key:
            raise ReqogniLoomError(
                "REQOGNILOOM_API_KEY is not set - export a 'reqlo_...' API key"
            )
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Must precede the URLError/OSError clauses: HTTPError subclasses both.
            raise ReqogniLoomError(_http_error_message(exc)) from exc
        except urllib.error.URLError as exc:
            raise ReqogniLoomError(f"could not reach {url}: {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:
            raise ReqogniLoomError(f"could not read {url}: {exc}") from exc
        return _decode_json(raw, url)

    def list_workspaces(self) -> Any:
        """GET /api/v1/workspaces/ using the ``X-API-Key`` header."""
        payload = self._request("GET", WORKSPACES_PATH)
        raise_for_error(payload)
        return payload

    def call_mcp(self, tool: str, params: dict[str, Any] | None = None) -> Any:
        """POST /mcp/ with a JSON-RPC 2.0 ``tools/call`` request.

        The frame matches ``backend/mcp_server/protocol_handler.py``, which
        reads the tool name from ``params.name`` and its arguments from
        ``params.arguments`` for the ``tools/call`` method.
        """
        frame = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": params or {}},
        }
        return self._request("POST", MCP_PATH, body=frame)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the command-line interface."""
    parser = argparse.ArgumentParser(
        prog="reqogniloom_client",
        description="Talk to ReqogniLoom over REST and MCP (stdlib only).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-workspaces", help="GET /api/v1/workspaces/")
    mcp_parser = subparsers.add_parser("mcp", help="Call an MCP tool via POST /mcp/")
    mcp_parser.add_argument("--tool", required=True, help="MCP tool name")
    mcp_parser.add_argument(
        "--params", default="{}", help="Tool arguments as a JSON object"
    )
    return parser


def print_result(result: Any) -> None:
    """Print the result to stdout in a stable, readable form."""
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main(argv: list | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        client = ReqogniLoomClient()
        if args.command == "list-workspaces":
            result = client.list_workspaces()
        else:
            result = extract_mcp_result(
                client.call_mcp(args.tool, parse_params(args.params))
            )
    except ReqogniLoomError as exc:
        print(f"reqogniloom: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - the host must never see a traceback
        print(f"reqogniloom: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print_result(result)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
