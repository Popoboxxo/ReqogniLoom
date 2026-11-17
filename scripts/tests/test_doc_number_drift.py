"""DOC-008 drift guard: the numbers written in the docs must match the code.

``scripts/generate_doc_counts.py`` is the single source of truth. This test
parses the numbers *actually written* in CODEBASE_OVERVIEW.md, project.yaml and
AGENTS.md and compares them to the freshly measured values. It checks the docs
instead of rewriting them, so CI can never silently "fix" a drifted claim.

Before the S6.1-C fix every assertion here failed: the docs claimed 16 L2
systems, 16+5 / 16+2 ViewSets, 1041 / 396 / 71 test files and 68 services /
70 E2E specs.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_doc_counts.py"
_SPEC = importlib.util.spec_from_file_location("doc_counts", _GENERATOR_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_doc_counts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_doc_counts)
COUNTS = _doc_counts.generate_counts()

OVERVIEW = REPO_ROOT / "docs" / "CODEBASE_OVERVIEW.md"
PROJECT_YAML = REPO_ROOT / ".meta-config" / "project.yaml"
AGENTS = REPO_ROOT / "AGENTS.md"


def _line(path: Path, *needles: str) -> str:
    """Return the unique line containing all ``needles`` (robust to line shifts)."""
    matches = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if all(needle in line for needle in needles)
    ]
    assert len(matches) == 1, (
        f"expected exactly one line with {needles!r} in {path.name}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _ints(line: str, pattern: str) -> tuple[int, ...]:
    """Extract all captured integers from ``line`` using ``pattern``."""
    match = re.search(pattern, line)
    assert match is not None, f"pattern {pattern!r} did not match: {line!r}"
    return tuple(int(group) for group in match.groups())


def test_overview_django_apps() -> None:
    assert _ints(_line(OVERVIEW, "`REQFLOW_APPS`) auf dem Backend"), r"mit (\d+) Django-Apps") == (
        COUNTS["django_apps"],
    )


def test_overview_viewset_header() -> None:
    line = _line(OVERVIEW, "**Exportierte API (", "ViewSets")
    assert _ints(
        line, r"Exportierte API \((\d+) ViewSets / (\d+) Router-Registrierungen\)"
    ) == (COUNTS["viewset_classes"], COUNTS["viewset_registrations"])


def test_overview_viewset_component_list() -> None:
    line = _line(OVERVIEW, "- `views.py` — ")
    assert _ints(
        line, r"- `views\.py` — (\d+) ViewSets / (\d+) Router-Registrierungen"
    ) == (COUNTS["viewset_classes"], COUNTS["viewset_registrations"])


def test_project_yaml_test_and_tool_counts() -> None:
    line = _line(PROJECT_YAML, "Backend-Testdateien")
    assert _ints(
        line,
        r"(\d+) Backend-Testdateien.*?(\d+) Frontend-Testdateien.*?"
        r"(\d+) E2E-Spec-Dateien.*?MCP-Katalog (\d+) Tools",
    ) == (
        COUNTS["backend_test_files"],
        COUNTS["frontend_test_files"],
        COUNTS["e2e_specs"],
        COUNTS["mcp_tools"],
    )


def test_agents_service_file_counts() -> None:
    expected = (COUNTS["service_files"],)
    assert _ints(
        _line(AGENTS, "Layer 2: application ("),
        r"application \((\d+) \*_service\.py\)",
    ) == expected
    assert _ints(
        _line(AGENTS, "Domain-Fassade ("),
        r"Domain-Fassade \((\d+) \*_service\.py\)",
    ) == expected


def test_agents_e2e_spec_count() -> None:
    assert _ints(
        _line(AGENTS, "Playwright/Chromium E2E-Tests"),
        r"E2E-Tests \((\d+) Spec-Dateien",
    ) == (COUNTS["e2e_specs"],)
