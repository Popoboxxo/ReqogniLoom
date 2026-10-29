"""AST gate: every production ``build_memory_context`` call passes ``slot_name``.

Plan A T-A1-2 (QR-S06): ``slot_name`` is what makes the slot-level injection
policy apply. A caller that forgets it would silently bypass the workspace /
user switches, so the invariant is machine-checked instead of documented:
every call under ``backend/`` (excluding ``tests/`` and ``migrations/``) must
pass a ``slot_name`` keyword.

The scan is AST-based, not a grep: a comment or a docstring mentioning the
function is not a call, and ``**kwargs`` splicing a known dict would still be
visible as an omitted keyword.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_FUNCTION_NAME = "build_memory_context"
_KEYWORD = "slot_name"


def _is_production(path: Path) -> bool:
    parts = path.relative_to(_BACKEND).parts
    return "tests" not in parts and "migrations" not in parts and "testing" not in parts


def _iter_call_sites() -> list[tuple[str, int]]:
    offenders: list[tuple[str, int]] = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if not _is_production(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != _FUNCTION_NAME:
                continue
            if not any(kw.arg == _KEYWORD for kw in node.keywords):
                offenders.append((str(path.relative_to(_BACKEND)), node.lineno))
    return offenders


def test_all_callers_pass_slot_name():
    offenders = _iter_call_sites()
    assert offenders == [], (
        "build_memory_context() calls without the mandatory 'slot_name' keyword "
        f"(policy bypass, QR-S06): {offenders}"
    )


def test_the_scan_actually_sees_the_production_callers():
    """Guard against a silently empty scan (wrong root, over-eager exclusion)."""
    sites = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if not _is_production(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == _FUNCTION_NAME:
                sites.append(path.relative_to(_BACKEND).as_posix())
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == _FUNCTION_NAME:
                sites.append(path.relative_to(_BACKEND).as_posix())
    assert {
        "application/prompt_resolver.py",
        "application/interview_service.py",
        "application/ai_review_service.py",
    } <= set(sites)


@pytest.mark.parametrize(
    "source,should_fail",
    [
        ("build_memory_context(t, w, u, 'q', slot_name='x')", False),
        ("build_memory_context(t, w, u, 'q')", True),
        ("build_memory_context(t, w, u, 'q', **kwargs)", True),
        ("# build_memory_context(t, w, u, 'q')", False),
    ],
)
def test_scan_detects_missing_keyword(source, should_fail):
    """Pin the detector itself against false negatives / positives."""
    tree = ast.parse(source)
    missing = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == _FUNCTION_NAME:
            missing = not any(kw.arg == _KEYWORD for kw in node.keywords)
    assert missing is should_fail
