"""AST ratchet for documented-but-unused ``Args:`` entries (R2C-007).

A docstring that describes a parameter as if it were consumed while the body
never reads it misleads callers and AI agents reading the signature. This test
parses the R2C-007 audited files and collects such entries.

It is deliberately **count-based** (``count <= baseline``) rather than a hard
``count == 0`` gate: three stale ``Args:`` entries from the original finding
remain (R2C-007b ``include_deleted``; R2C-007d ``_change_reason`` ×2, now renamed
to ``_change_reason`` with an honest docstring but still no ``Args:`` entry).
Lower ``_BASELINE`` as those are cleaned up; never raise it. The two parameters
fixed here (``outdate.reason`` and ``export_pdf.artifact_id``) are guarded by an
explicit per-parameter assertion so the ratchet already protects this change.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]

# Files named in the R2C-007 finding. Read-only: this test never edits them.
_AUDITED_FILES = (
    "workflow/services.py",
    "application/export_service.py",
    "application/import_service.py",
    "application/architecture_service.py",
    "application/artifact_update_adapters.py",
)

# Ratchet boundary — lower only (see module docstring).
_BASELINE = 3

# A documented param marked with any of these is honest about being unused and
# is therefore not a lying docstring.
_HONEST_MARKERS = (
    "unused",
    "ignored",
    "no effect",
    "reserved for",
    "kept for signature",
    "kept for keyword",
)

_SECTION_RE = re.compile(r"^[A-Za-z][A-Za-z ]*:$")
_ARG_RE = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(.*)$")


def _docstring_args(doc: str) -> list[tuple[str, str]]:
    """Extract ``(name, description)`` pairs from a Google-style Args block."""
    header_indent: int | None = None
    arg_indent: int | None = None
    current: str | None = None
    entries: list[tuple[str, list[str]]] = []
    in_args = False

    for line in doc.splitlines():
        stripped = line.strip()
        if not in_args:
            if stripped == "Args:":
                in_args = True
                header_indent = len(line) - len(line.lstrip())
            continue
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if (
            header_indent is not None
            and indent <= header_indent
            and _SECTION_RE.match(stripped)
            and stripped != "Args:"
        ):
            break
        match = _ARG_RE.match(stripped)
        if match and (arg_indent is None or indent == arg_indent):
            if arg_indent is None:
                arg_indent = indent
            current = match.group(1)
            entries.append((current, [match.group(2)]))
        elif current is not None and arg_indent is not None and indent > arg_indent:
            entries[-1][1].append(stripped)

    return [(name, " ".join(parts)) for name, parts in entries]


def _body_names(node: ast.AST) -> set[str]:
    """Names actually read in a function body (including nested scopes)."""
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def _collect_stale_args() -> list[tuple[str, int, str, str]]:
    """Return ``(file, line, function, param)`` for each lying Args entry."""
    stale: list[tuple[str, int, str, str]] = []
    for rel in _AUDITED_FILES:
        tree = ast.parse((_BACKEND / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node) or ""
            if "Args:" not in doc:
                continue
            used = _body_names(node)
            for name, description in _docstring_args(doc):
                if name in used:
                    continue
                if any(marker in description.lower() for marker in _HONEST_MARKERS):
                    continue
                stale.append((rel, node.lineno, node.name, name))
    return stale


def test_documented_unused_args_stay_within_baseline():
    stale = _collect_stale_args()
    assert len(stale) <= _BASELINE, (
        "New documented-but-unused Args entry (lower _BASELINE only when "
        f"removing stale docs): {stale}"
    )


def test_r2c_007_fixed_params_are_not_stale():
    """The two params fixed by this change must stay honestly documented."""
    stale = {(file, function, param) for file, _line, function, param in _collect_stale_args()}
    assert ("workflow/services.py", "outdate", "reason") not in stale
    assert ("application/export_service.py", "export_pdf", "artifact_id") not in stale
