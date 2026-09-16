"""Guard: no raw exception text in a REST/MCP error response (#697, CWE-209).

The sweep in #697 removed the ``str(exc)``-into-the-response bodies that the
deep-dive review (C-1) had left behind in ``rest_api/`` and ``mcp_server/``.
Individually each site is a one-line mistake, so the realistic regression mode
is a *new* handler written in the old style. This module scans the transport
source for that style and fails.

Scope and precision:

* Only the two transport packages are scanned. ``application/`` legitimately
  puts ``str(exc)`` into log lines, audit rows and re-raised domain errors;
  what matters for CWE-209 is what reaches a *response builder*.
* A line is flagged only when it both interpolates an exception variable into
  a response builder (``build_error_response``, ``ToolResult.error``, ...) and
  sits inside a handler that catches ``Exception``/``BaseException`` or is
  bare. A typed handler (``except ValidationError as exc``) forwards a
  domain-authored message and is deliberately allowed — that is the pattern
  the whole codebase is built on.
* ``logger.*`` lines are skipped: logging the real cause server-side is the
  other half of the fix and must never be flagged.
* Statements spanning several lines are covered by looking at the start of the
  enclosing call, not just the line that carries ``str(exc)``.

Deliberately free of a database: this is a source scan.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_SCANNED_PACKAGES = ("rest_api", "mcp_server")

#: A call that ends up as the body of an HTTP or JSON-RPC error response.
_RESPONSE_BUILDER = re.compile(
    r"(build_error_response|ToolResult\.error|_error_response|"
    r"format_jsonrpc_error|_validation|_forbidden|_not_found|_err)\s*\("
)

#: The leak itself: an exception variable rendered into a string.
_RAW_DETAIL = re.compile(r"str\((?:exc|e|err)\)|\{(?:exc|e|err)[!:}]")

#: ``except`` clause; a trailing lint-suppression comment after the colon is
#: allowed (and is itself skipped further down, never flagged).
_EXCEPT = re.compile(r"^(\s*)except\b(.*?):\s*(#.*)?$")
_BROAD = re.compile(r"^(Exception|BaseException)\b")
_STOP = re.compile(r"^\s*(async def |def |class )")

#: How far back to look for the response builder that a ``str(exc)`` argument
#: belongs to (multi-line calls).
_LOOKBACK = 6


def _enclosing_except(lines: list[str], idx: int) -> str | None:
    """Return the caught type of the handler enclosing ``lines[idx]``."""
    match_indent = len(lines[idx]) - len(lines[idx].lstrip())
    min_indent = match_indent
    for j in range(idx - 1, -1, -1):
        line = lines[j]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent >= min_indent:
            continue
        m = _EXCEPT.match(line)
        if m:
            return m.group(2).split(" as ")[0].strip() or "Exception"
        if _STOP.match(line):
            return None
        min_indent = indent
    return None


def _offending_lines(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    offenders: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not _RAW_DETAIL.search(line):
            continue
        if "logger" in line or "logging" in line or line.lstrip().startswith("#"):
            continue
        # The builder may be on this line or open a multi-line call above it.
        window = lines[max(0, i - _LOOKBACK) : i + 1]
        if not any(_RESPONSE_BUILDER.search(candidate) for candidate in window):
            continue
        caught = _enclosing_except(lines, i)
        if caught is None or not _BROAD.match(caught):
            continue
        offenders.append((i + 1, line.strip()))
    return offenders


@pytest.mark.parametrize("package", _SCANNED_PACKAGES)
def test_no_raw_exception_text_reaches_a_response_builder(package: str) -> None:
    offenders: list[str] = []
    for path in sorted((_BACKEND / package).rglob("*.py")):
        parts = set(path.parts)
        if {"migrations", "tests"} & parts or path.name.startswith("test_"):
            continue
        for lineno, text in _offending_lines(path):
            rel = path.relative_to(_BACKEND.parent).as_posix()
            offenders.append(f"{rel}:{lineno}: {text}")

    assert not offenders, (
        "str(exc) is returned to the client from an unmapped exception "
        "(CWE-209, #697). Log the cause and return a static message:\n  "
        + "\n  ".join(offenders)
    )


def test_the_scan_actually_detects_the_old_pattern(tmp_path: Path) -> None:
    """Control: the detector must not silently degrade into a no-op."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def handler(request):\n"
        "    try:\n"
        "        return do_work()\n"
        "    except Exception as exc:  # noqa: BLE001\n"
        "        return ToolResult.error('INTERNAL_ERROR', str(exc))\n",
        encoding="utf-8",
    )

    assert _offending_lines(sample) == [
        (5, "return ToolResult.error('INTERNAL_ERROR', str(exc))")
    ]


def test_the_scan_allows_the_fixed_pattern_and_typed_handlers(tmp_path: Path) -> None:
    """Control: the two shapes the sweep relies on must stay unflagged."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def handler(request):\n"
        "    try:\n"
        "        return do_work()\n"
        "    except Exception:\n"
        "        logger.exception('handler failed')\n"
        "        return ToolResult.error('INTERNAL_ERROR', 'An internal error occurred.')\n"
        "    except ValidationError as exc:\n"
        "        return ToolResult.error('VALIDATION_ERROR', str(exc))\n",
        encoding="utf-8",
    )

    assert _offending_lines(sample) == []
