r"""Architecture guardrail — Service-Layer boundary enforcement (REQ-066).

The REST API layer (``rest_api/*_views.py`` and ``rest_api/views.py``) must not
talk to the ORM directly. All persistence access belongs in the Application
service layer (``application/*``) or the domain-specific service modules
(``icd/services.py``, ``diagram/services.py``, ``auth_tenancy/services/*``).

This test is a *ratchet*: it caps the number of tolerated legacy violations per
file and fails if that number grows. As REQ-066 removes violations the caps are
lowered — they must never be raised. A cap of ``0`` (a file absent from the
allowlist) means the file is fully clean and must stay that way.

Two violation classes are tracked:

* ``.objects.`` / ``.unscoped.`` — direct ORM manager access (``MAX_ORM_LINES``).
* ``from persistence.models import`` — direct model import (``MODEL_IMPORT_ALLOWLIST``).

Serializers (``serializers.py``) are covered by the same ``.objects.``/
``.unscoped.`` ratchet as the ``*_views.py`` files (issue #132): a future
queryset access inside a serializer validator/choice field is exactly where
N+1 problems tend to creep in unnoticed, since ``_apply_query_optimization``
(``rest_api/serializers.py``) only operates at the ViewSet level. The
``ElementType`` enum import it already has is a deliberate, harmless
Option-B exception (an enum, not a queryset) and is allowlisted below like
the other legacy model imports.

Baseline captured 2026-07-14 (pre-REQ-066):
    views.py 27, icd_views.py 7, diagram_views.py 4, settings_views.py 3,
    diagram_canvas_views.py 3, auth_views.py 2.

Issue #124 (2026-07-28): the ratchet only scanned ``rest_api/*_views.py``,
leaving ``mcp_server/tools/*.py`` — which also violates ADR-01's
Single-Entry-Point rule — completely unguarded. The MCP-tools ceilings below
are a *frozen baseline*, not an endorsement: they exist only to stop further
regression while the actual migration into ``application/`` services (a
separate, larger refactor — REQ-066 follow-up) is scoped and executed.
Baseline captured 2026-07-29: cross_cutting.py 19, users.py 10,
prompt_template.py 4, review.py 2, diagram.py 2, needs.py 1 (38 total).

Issue #132 (2026-07-28): ``serializers.py`` was entirely exempt from both
checks above (see the historical note this replaced). Baseline captured
2026-07-31: 0 direct-ORM lines (verified via
``grep -c "\.objects\." rest_api/serializers.py``) — the ratchet starts at 0
and any new ``.objects.``/``.unscoped.`` access fails the build immediately,
same as any other file absent from ``MAX_ORM_LINES``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Directory holding the REST API view modules under guard.
_REST_API_DIR = Path(__file__).resolve().parent.parent
# Directory holding the MCP tool-group modules under guard (issue #124).
_MCP_TOOLS_DIR = _REST_API_DIR.parent / "mcp_server" / "tools"

# Matches ``X.objects.`` and ``X.unscoped.`` manager access.
_ORM_RE = re.compile(r"\.(objects|unscoped)\.")
_MODEL_IMPORT_RE = re.compile(r"^\s*from persistence\.models import")

# Per-file ceiling of tolerated direct-ORM lines. Files not listed must be 0.
# NEVER raise a value here — REQ-066 only lowers them.
MAX_ORM_LINES: dict[str, int] = {
    "icd_views.py": 3,
    "diagram_views.py": 3,
    "diagram_canvas_views.py": 3,
}

# Files still permitted to ``from persistence.models import`` directly. Shrinks
# as service methods replace the last direct model references in each file.
# views.py fully cleaned in REQ-066 Phase 2/3 — no longer allowlisted.
# serializers.py (#132): only ``ElementType``, an enum used in a choice field —
# not a queryset — per the Option-B decision; the direct-ORM ratchet above
# (MAX_ORM_LINES, defaulting to 0 for serializers.py) is what actually guards
# against a future N+1-prone queryset access sneaking in here.
MODEL_IMPORT_ALLOWLIST: set[str] = {
    "icd_views.py",
    "diagram_views.py",
    "diagram_canvas_views.py",
    "serializers.py",
}

# Issue #124: frozen baseline for mcp_server/tools/*.py — ADR-01 violations
# that pre-date this guard. NEVER raise a value here; only lower it as
# call-sites are migrated into application/ services.
MCP_TOOLS_MAX_ORM_LINES: dict[str, int] = {
    "cross_cutting.py": 19,
    "users.py": 10,
    "prompt_template.py": 4,
    "review.py": 2,
    "diagram.py": 2,
    "needs.py": 1,
}


def _view_files() -> list[Path]:
    """Return ``views.py``, every ``*_views.py`` module, and ``serializers.py``
    (#132) in the REST API dir — all guarded by the same ratchet."""
    files = sorted(_REST_API_DIR.glob("*_views.py"))
    base = _REST_API_DIR / "views.py"
    if base.exists():
        files.append(base)
    serializers = _REST_API_DIR / "serializers.py"
    if serializers.exists():
        files.append(serializers)
    return files


def _mcp_tool_files() -> list[Path]:
    """Return every ``*.py`` module in ``mcp_server/tools`` (issue #124)."""
    if not _MCP_TOOLS_DIR.exists():
        return []
    return sorted(
        p for p in _MCP_TOOLS_DIR.glob("*.py") if p.name != "__init__.py"
    )


def _count_orm_lines(path: Path) -> int:
    """Count non-comment source lines with direct ORM manager access."""
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        if _ORM_RE.search(raw):
            count += 1
    return count


def _has_model_import(path: Path) -> bool:
    """Return whether the module imports ``persistence.models`` directly."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        if _MODEL_IMPORT_RE.match(raw):
            return True
    return False


@pytest.mark.parametrize("path", _view_files(), ids=lambda p: p.name)
def test_no_new_direct_orm_access(path: Path) -> None:
    """No view file may exceed its ratchet ceiling of direct-ORM lines."""
    allowed = MAX_ORM_LINES.get(path.name, 0)
    actual = _count_orm_lines(path)
    assert actual <= allowed, (
        f"{path.name}: {actual} direct-ORM line(s) exceed the ratchet ceiling "
        f"of {allowed}. Move ORM access into an Application/domain service. "
        f"If you legitimately removed violations, LOWER the ceiling in "
        f"MAX_ORM_LINES — never raise it."
    )


@pytest.mark.parametrize("path", _view_files(), ids=lambda p: p.name)
def test_model_import_only_where_allowlisted(path: Path) -> None:
    """No view file may newly import ``persistence.models`` directly."""
    if _has_model_import(path):
        assert path.name in MODEL_IMPORT_ALLOWLIST, (
            f"{path.name}: imports persistence.models directly. Route model "
            f"access through a service and drop the import."
        )


def test_ratchet_is_monotonic() -> None:
    """Allowlisted files must actually still contain the violations they cap.

    Guards against a stale ceiling: if a file's real count drops below its cap,
    the cap should be lowered. This keeps the ratchet honest.
    """
    for name, cap in MAX_ORM_LINES.items():
        path = _REST_API_DIR / name
        actual = _count_orm_lines(path)
        assert actual == cap, (
            f"{name}: ratchet ceiling is {cap} but file now has {actual} "
            f"direct-ORM line(s). Lower MAX_ORM_LINES['{name}'] to {actual}."
        )


@pytest.mark.parametrize("path", _mcp_tool_files(), ids=lambda p: p.name)
def test_no_new_direct_orm_access_mcp_tools(path: Path) -> None:
    """No mcp_server/tools module may exceed its frozen ADR-01 ceiling (#124)."""
    allowed = MCP_TOOLS_MAX_ORM_LINES.get(path.name, 0)
    actual = _count_orm_lines(path)
    assert actual <= allowed, (
        f"{path.name}: {actual} direct-ORM line(s) exceed the ratchet ceiling "
        f"of {allowed}. Move ORM access into an Application service (ADR-01). "
        f"If you legitimately removed violations, LOWER the ceiling in "
        f"MCP_TOOLS_MAX_ORM_LINES — never raise it."
    )


def test_mcp_tools_ratchet_is_monotonic() -> None:
    """Frozen mcp_server/tools baselines must still reflect the real count.

    Guards against a stale ceiling: if a file's real count drops below its
    cap, the cap should be lowered. This keeps the ratchet honest.
    """
    for name, cap in MCP_TOOLS_MAX_ORM_LINES.items():
        path = _MCP_TOOLS_DIR / name
        actual = _count_orm_lines(path)
        assert actual == cap, (
            f"{name}: ratchet ceiling is {cap} but file now has {actual} "
            f"direct-ORM line(s). Lower MCP_TOOLS_MAX_ORM_LINES['{name}'] "
            f"to {actual}."
        )
