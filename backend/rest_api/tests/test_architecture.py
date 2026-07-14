"""Architecture guardrail — Service-Layer boundary enforcement (REQ-066).

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

Serializers (``serializers.py``) are intentionally out of scope: model access in
serializer validators / choice fields is permitted by the Option-B decision.

Baseline captured 2026-07-14 (pre-REQ-066):
    views.py 27, icd_views.py 7, diagram_views.py 4, settings_views.py 3,
    diagram_canvas_views.py 3, auth_views.py 2.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Directory holding the REST API view modules under guard.
_REST_API_DIR = Path(__file__).resolve().parent.parent

# Matches ``X.objects.`` and ``X.unscoped.`` manager access.
_ORM_RE = re.compile(r"\.(objects|unscoped)\.")
_MODEL_IMPORT_RE = re.compile(r"^\s*from persistence\.models import")

# Per-file ceiling of tolerated direct-ORM lines. Files not listed must be 0.
# NEVER raise a value here — REQ-066 only lowers them.
MAX_ORM_LINES: dict[str, int] = {
    "views.py": 2,
    "icd_views.py": 3,
    "diagram_views.py": 3,
    "diagram_canvas_views.py": 3,
}

# Files still permitted to ``from persistence.models import`` directly. Shrinks
# as service methods replace the last direct model references in each file.
MODEL_IMPORT_ALLOWLIST: set[str] = {
    "views.py",
    "icd_views.py",
    "diagram_views.py",
    "diagram_canvas_views.py",
}


def _view_files() -> list[Path]:
    """Return ``views.py`` and every ``*_views.py`` module in the REST API dir."""
    files = sorted(_REST_API_DIR.glob("*_views.py"))
    base = _REST_API_DIR / "views.py"
    if base.exists():
        files.append(base)
    return files


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
