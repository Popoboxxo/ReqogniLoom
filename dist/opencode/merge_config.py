"""Safe merge of the OpenCode V2 MCP server entry into an existing config.

OpenCode V2 reads ``mcp.servers.<name>`` where V1 reads ``mcp.<name>``, so the
two configs cannot share one snippet. This module rewrites exactly that one key
in ``opencode.json`` and leaves everything else — other V2 servers, V1 entries
under ``mcp.<name>``, ``model``, unknown top-level keys — untouched.

The file is plain JSON, not JSONC: a config with comments is refused (exit 2)
rather than rewritten, because a JSON round-trip cannot preserve comments and
the user's file would silently lose content. The caller is then pointed at
``opencode.v2.json.snippet`` for a manual paste.

Writes are atomic (temp file in the target directory + ``os.replace``) and a
timestamped ``.bak-YYYYmmddHHMMSS`` copy is taken first — but only when the
file already exists and the merge actually changes the parsed config, so a
repeated install is a no-op with no backup churn.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from build_opencode_package import v2_server_entry

SERVER_NAME = "reqogniloom"
SNIPPET_HINT = "opencode.v2.json.snippet"
ENV_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
ENV_NAME_RE = re.compile(ENV_NAME_PATTERN)

EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_WRITE_ERROR = 3


def merge_v2(config: dict[str, Any], url: str, key_env: str) -> dict[str, Any]:
    """Return a copy of ``config`` carrying the V2 server entry.

    ``config`` is deep-copied, so callers can compare before/after and retry
    safely. ``url`` is the base URL without a path; ``key_env`` is the *name*
    of the env var holding the API key, never the key itself.

    Raises ``ValueError`` when ``mcp`` or ``mcp.servers`` exists but is not an
    object — merging into that would otherwise fail with an opaque
    ``AttributeError`` after a partially built result.
    """
    merged = copy.deepcopy(config)

    mcp = merged.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        raise ValueError("'mcp' must be a JSON object")

    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        raise ValueError("'mcp.servers' must be a JSON object")

    servers[SERVER_NAME] = v2_server_entry(url, key_env)
    return merged


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file in the same directory.

    Same-directory is required: ``os.replace`` is only atomic within one
    filesystem, and ``/tmp`` may well be a different one.
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _jsonc_error(path: Path, exc: json.JSONDecodeError) -> str:
    return (
        f"{path}: JSONC/Kommentare werden nicht unterstützt, Eintrag von Hand "
        f"einfügen — Snippet: {SNIPPET_HINT} (JSON-Fehler: {exc})"
    )


def _read_config(path: Path) -> tuple[dict[str, Any], bool]:
    """Return ``(config, existed)``.

    Raises ``ValueError`` with a user-facing message for anything that is not a
    JSON object (mapped to exit 2) and lets ``OSError`` propagate (mapped to
    exit 3 — a filesystem problem, not a bad argument).
    """
    if not path.exists():
        return {}, False

    raw = path.read_text(encoding="utf-8")

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(_jsonc_error(path, exc)) from exc

    if not isinstance(config, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")

    return config, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge the OpenCode V2 MCP server entry into an opencode.json "
            "without touching any other key."
        )
    )
    parser.add_argument("--config", required=True, type=Path, help="opencode.json path")
    parser.add_argument("--url", required=True, help="MCP base URL, without /mcp/")
    parser.add_argument(
        "--key-env",
        required=True,
        help="name of the env var holding the API key (never the key itself)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing or backing up anything",
    )
    args = parser.parse_args(argv)

    if not ENV_NAME_RE.match(args.key_env):
        print(
            f"error: --key-env {args.key_env!r} is not a valid environment "
            f"variable name (expected {ENV_NAME_PATTERN})",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    path: Path = args.config

    try:
        config, existed = _read_config(path)
        merged = merge_v2(config, args.url, args.key_env)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except OSError as exc:
        print(f"error: cannot read {path} ({exc})", file=sys.stderr)
        return EXIT_WRITE_ERROR

    changed = not existed or merged != config
    entry = merged["mcp"]["servers"][SERVER_NAME]

    if args.dry_run:
        if not existed:
            print(f"[dry-run] would create {path}")
        elif changed:
            print(f"[dry-run] would update {path} (timestamped backup first)")
        else:
            print(f"[dry-run] would leave {path} unchanged")
        print(f"[dry-run] server {SERVER_NAME} -> {entry['url']}")
        print(f"[dry-run] key from env var {args.key_env}")
        return EXIT_OK

    if not changed:
        print(f"{path}: already up to date, nothing written")
        return EXIT_OK

    rendered = json.dumps(merged, indent=2) + "\n"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup = path.with_name(f"{path.name}.bak-{stamp}")
            shutil.copy2(path, backup)
            print(f"{path}: backup written to {backup.name}")
        _atomic_write(path, rendered)
    except OSError as exc:
        print(f"error: cannot write {path} ({exc})", file=sys.stderr)
        return EXIT_WRITE_ERROR

    print(f"{path}: merged {SNIPPET_HINT} entry for server {SERVER_NAME}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
