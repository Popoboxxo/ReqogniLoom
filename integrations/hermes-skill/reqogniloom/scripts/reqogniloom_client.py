#!/usr/bin/env python3
"""Command-line connector for ReqogniLoom over REST and MCP.

Loaded as a Hermes skill script and usable from any surface (TUI, web, CLI,
desktop). Standard library only, so it runs wherever Hermes runs.

Configuration is read exclusively from the environment:

* ``REQOGNILOOM_BASE_URL``     - server origin (default ``http://localhost:8001``)
* ``REQOGNILOOM_API_KEY``      - ``reqlo_...`` key, sent as the ``X-API-Key`` header
* ``REQOGNILOOM_WORKSPACE_ID`` - default workspace UUID for the memory commands

Examples::

    python scripts/reqogniloom_client.py list-workspaces
    python scripts/reqogniloom_client.py mcp --tool requirement.query \\
        --params '{"workspace_id": "00000000-0000-0000-0000-000000000000"}'
    python scripts/reqogniloom_client.py memory-query --query "reviewer"
    python scripts/reqogniloom_client.py memory-digest --workspace-id <uuid>
    python scripts/reqogniloom_client.py memory-write --content "fact" --scope user

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

#: Memory scopes accepted by the ``memory.*`` MCP tools.
MEMORY_SCOPES = ("workspace", "user", "artifact")
#: Reasoning levels accepted by ``memory.ask``.
MEMORY_REASONING_LEVELS = ("minimal", "low", "medium", "high", "max")
#: CLI subcommand -> MCP tool name for the memory surface.
MEMORY_COMMAND_TOOLS = {
    "memory-query": "memory.query",
    "memory-digest": "memory.digest",
    "memory-ask": "memory.ask",
    "memory-write": "memory.write",
}


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


def _list_items(payload: Any) -> list[Any] | None:
    """Return the item list of a DRF page or bare array, else ``None``.

    ``None`` means the payload is not a collection shape, so callers should
    not try to paginate it.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return None


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
        """GET /api/v1/workspaces/ following DRF ``next`` to the last page.

        DRF paginates this collection, so a single request only ever sees the
        first page. A page-shaped response is merged back into one page dict
        (``results`` concatenated, ``next`` cleared, ``count``/``previous``
        kept); a bare array is concatenated into one list. A repeated ``next``
        ends the loop, so a misbehaving server cannot spin it forever.
        """
        seen: set[str] = set()
        next_ref: str | None = WORKSPACES_PATH
        items: list[Any] = []
        page: dict[str, Any] | None = None
        while next_ref:
            if next_ref in seen:
                break
            seen.add(next_ref)
            payload = self._request("GET", next_ref)
            raise_for_error(payload)
            page_items = _list_items(payload)
            if page_items is None:
                # Not a collection shape (single object or unexpected body):
                # return it untouched rather than fabricating a list.
                return payload
            if isinstance(payload, dict) and page is None:
                page = {key: value for key, value in payload.items() if key != "results"}
            items.extend(page_items)
            candidate = payload.get("next") if isinstance(payload, dict) else None
            next_ref = candidate if isinstance(candidate, str) and candidate else None
        if page is None:
            # Only bare arrays were seen (or nothing at all).
            return items
        page["next"] = None
        page["results"] = items
        return page

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


class _MarkExplicit(argparse.Action):
    """Store a value and flag it as explicitly supplied on the namespace.

    Needed to tell a user-typed ``--workspace-id`` apart from the top-level
    env default, so an incompatible combination can be rejected without
    tripping over an implicit configuration value.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, values)
        setattr(namespace, "_workspace_id_explicit", True)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the command-line interface."""
    parser = argparse.ArgumentParser(
        prog="reqogniloom_client",
        description="Talk to ReqogniLoom over REST and MCP (stdlib only).",
    )
    parser.add_argument(
        "--workspace-id",
        dest="workspace_id",
        default=_env("REQOGNILOOM_WORKSPACE_ID") or None,
        action=_MarkExplicit,
        help="Default workspace UUID (falls back to REQOGNILOOM_WORKSPACE_ID).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-workspaces", help="GET /api/v1/workspaces/")
    mcp_parser = subparsers.add_parser("mcp", help="Call an MCP tool via POST /mcp/")
    mcp_parser.add_argument("--tool", required=True, help="MCP tool name")
    mcp_parser.add_argument(
        "--params", default="{}", help="Tool arguments as a JSON object"
    )

    query_parser = subparsers.add_parser(
        "memory-query", help="Call MCP memory.query (semantic memory search)"
    )
    query_parser.add_argument("--query", required=True, help="Search text")
    query_parser.add_argument(
        "--scope",
        choices=MEMORY_SCOPES,
        help="Single memory scope to search (ignored when --scopes is given)",
    )
    query_parser.add_argument(
        "--scopes",
        action="append",
        default=None,
        help="Comma-separated memory scopes; repeatable",
    )
    _add_workspace_argument(query_parser)
    _add_artifact_argument(query_parser)
    _add_top_k_argument(query_parser)

    digest_parser = subparsers.add_parser(
        "memory-digest", help="Call MCP memory.digest (prompt-ready summary)"
    )
    _add_workspace_argument(digest_parser)
    _add_artifact_argument(digest_parser)

    ask_parser = subparsers.add_parser(
        "memory-ask", help="Call MCP memory.ask (natural-language answer)"
    )
    ask_parser.add_argument("--query", required=True, help="Question text")
    _add_workspace_argument(ask_parser)
    _add_artifact_argument(ask_parser)
    ask_parser.add_argument(
        "--reasoning-level",
        dest="reasoning_level",
        choices=MEMORY_REASONING_LEVELS,
        default=argparse.SUPPRESS,
        help="Optional reasoning depth for the answer",
    )

    write_parser = subparsers.add_parser(
        "memory-write", help="Call MCP memory.write (persist a memory fact)"
    )
    write_parser.add_argument("--content", required=True, help="Memory content")
    write_parser.add_argument(
        "--scope",
        required=True,
        choices=MEMORY_SCOPES,
        help="Memory scope (incompatible --workspace-id/--artifact-id are rejected)",
    )
    _add_workspace_argument(write_parser)
    _add_artifact_argument(write_parser)
    write_parser.add_argument(
        "--confidence",
        type=float,
        default=argparse.SUPPRESS,
        help="Confidence in [0, 1] (default 1.0 server-side)",
    )
    write_parser.add_argument(
        "--change-reason",
        dest="change_reason",
        default=argparse.SUPPRESS,
        help="Optional audit reason for the write",
    )
    return parser


def _add_workspace_argument(subparser: argparse.ArgumentParser) -> None:
    """Attach ``--workspace-id`` without clobbering the global default.

    ``SUPPRESS`` keeps the value supplied by the top-level flag (or its env
    default) when the subcommand flag is absent.
    """
    subparser.add_argument(
        "--workspace-id",
        dest="workspace_id",
        default=argparse.SUPPRESS,
        action=_MarkExplicit,
        help="Workspace UUID (falls back to the global flag / env)",
    )


def _add_artifact_argument(subparser: argparse.ArgumentParser) -> None:
    """Attach ``--artifact-id`` (only ever present when given)."""
    subparser.add_argument(
        "--artifact-id",
        dest="artifact_id",
        default=argparse.SUPPRESS,
        help="Artifact UUID for artifact-scoped memory",
    )


def _add_top_k_argument(subparser: argparse.ArgumentParser) -> None:
    """Attach ``--top-k`` (only ever present when given)."""
    subparser.add_argument(
        "--top-k",
        dest="top_k",
        type=int,
        default=argparse.SUPPRESS,
        help="Maximum number of results (default 5 server-side)",
    )


def _parse_scopes(values: list[str] | None) -> list[str] | None:
    """Flatten repeated comma-separated ``--scopes`` values, or ``None``."""
    if not values:
        return None
    scopes: list[str] = []
    for raw in values:
        for part in str(raw).split(","):
            token = part.strip()
            if token:
                scopes.append(token)
    return scopes or None


def _require_workspace(client: "ReqogniLoomClient") -> str:
    """Return the resolved workspace id or raise a clear configuration error."""
    workspace_id = client.workspace_id or ""
    if not workspace_id:
        raise ReqogniLoomError(
            "no workspace id: pass --workspace-id or set REQOGNILOOM_WORKSPACE_ID"
        )
    return workspace_id


def _memory_arguments(args: argparse.Namespace, client: "ReqogniLoomClient") -> dict[str, Any]:
    """Build the ``arguments`` object for a memory subcommand.

    Only keys the user (or the configured default) actually supplied are
    included, so no ``null`` values are sent to the backend.
    """
    command = args.command
    arguments: dict[str, Any] = {}
    artifact_id = getattr(args, "artifact_id", None)
    workspace_id_explicit = bool(getattr(args, "_workspace_id_explicit", False))

    if command == "memory-query":
        arguments["query"] = args.query
        scope = getattr(args, "scope", None)
        scopes = _parse_scopes(getattr(args, "scopes", None))
        # ``scopes`` wins over ``scope`` (same precedence as the backend), so
        # the injection decision is made from the effective scope set.
        if scopes:
            arguments["scopes"] = scopes
        elif scope:
            arguments["scope"] = scope
        effective = set(scopes if scopes else ([scope] if scope else []))
        if "workspace" in effective:
            arguments["workspace_id"] = _require_workspace(client)
        elif not effective and client.workspace_id:
            # No scope filter given: fall back to the configured default.
            arguments["workspace_id"] = client.workspace_id
        if "artifact" in effective:
            if not artifact_id:
                raise ReqogniLoomError(
                    "memory-query with scope=artifact requires --artifact-id"
                )
            arguments["artifact_id"] = artifact_id
        elif artifact_id:
            arguments["artifact_id"] = artifact_id
        top_k = getattr(args, "top_k", None)
        if top_k is not None:
            arguments["top_k"] = top_k
        return arguments

    if command == "memory-digest":
        arguments["workspace_id"] = _require_workspace(client)
        if artifact_id:
            arguments["artifact_id"] = artifact_id
        return arguments

    if command == "memory-ask":
        arguments["query"] = args.query
        arguments["workspace_id"] = _require_workspace(client)
        if artifact_id:
            arguments["artifact_id"] = artifact_id
        reasoning_level = getattr(args, "reasoning_level", None)
        if reasoning_level:
            arguments["reasoning_level"] = reasoning_level
        return arguments

    if command == "memory-write":
        scope = args.scope
        arguments["content"] = args.content
        arguments["scope"] = scope
        if scope == "workspace":
            if artifact_id:
                raise ReqogniLoomError(
                    "memory-write with scope=workspace cannot be combined "
                    "with --artifact-id"
                )
            arguments["workspace_id"] = _require_workspace(client)
        elif scope == "artifact":
            if not artifact_id:
                raise ReqogniLoomError(
                    "memory-write with scope=artifact requires --artifact-id"
                )
            if workspace_id_explicit:
                raise ReqogniLoomError(
                    "memory-write with scope=artifact cannot be combined "
                    "with --workspace-id"
                )
            arguments["artifact_id"] = artifact_id
        else:  # scope == "user"
            if workspace_id_explicit or artifact_id:
                raise ReqogniLoomError(
                    "memory-write with scope=user cannot be combined with "
                    "--workspace-id or --artifact-id"
                )
        # scope=user carries neither id, so the configured default is
        # deliberately not injected here.
        confidence = getattr(args, "confidence", None)
        if confidence is not None:
            arguments["confidence"] = confidence
        change_reason = getattr(args, "change_reason", None)
        if change_reason:
            arguments["change_reason"] = change_reason
        return arguments

    raise ReqogniLoomError(f"unknown memory command: {command}")


def print_result(result: Any) -> None:
    """Print the result to stdout in a stable, readable form."""
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main(argv: list | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        client = ReqogniLoomClient(workspace_id=args.workspace_id)
        if args.command == "list-workspaces":
            result = client.list_workspaces()
        elif args.command == "mcp":
            result = extract_mcp_result(
                client.call_mcp(args.tool, parse_params(args.params))
            )
        else:
            tool = MEMORY_COMMAND_TOOLS[args.command]
            result = extract_mcp_result(
                client.call_mcp(tool, _memory_arguments(args, client))
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
