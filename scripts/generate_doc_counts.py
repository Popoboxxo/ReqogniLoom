"""Single source of truth for the inventory counts quoted in project docs (DOC-008).

``generate_counts()`` measures the seven counts directly from the repository at
HEAD and returns a stable mapping. Run this module as a script to emit that
mapping as JSON; ``--commands`` adds the canonical shell command for each value
so any single number can be re-measured by hand.

Consumers must import :func:`generate_counts` instead of hard-coding numbers.
The drift guard in ``scripts/tests/test_doc_number_drift.py`` parses the values
actually written in CODEBASE_OVERVIEW.md, project.yaml and AGENTS.md and checks
them against this mapping. CI checks those files; it never rewrites them.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Callable

# scripts/generate_doc_counts.py -> parents[1] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[1]

# Canonical measurement commands. Each one reproduces the value of its key
# when run from REPO_ROOT (verified at base commit aac32bb2).
COUNT_COMMANDS: dict[str, str] = {
    "django_apps": r"""sed -n '/^REQFLOW_APPS = \[/,/^\]/p' backend/reqogniloom/settings.py | grep -cP '^\s+"[a-z_]+",'""",
    "viewset_classes": (
        r"grep -rhoP 'router\.register\(.*?,\s*\K\w+ViewSet' "
        r"backend/rest_api/ | sort -u | wc -l"
    ),
    "viewset_registrations": r"grep -c 'router.register(' backend/rest_api/urls.py",
    "frontend_test_files": r"find frontend/src -name '*.test.ts*' | wc -l",
    "e2e_specs": r"find e2e -name '*.spec.ts' | wc -l",
    "backend_test_files": r"find backend -name 'test_*.py' | wc -l",
    "service_files": (
        r"find backend -name '*_service.py' -not -path '*/tests/*' | wc -l"
    ),
    "mcp_tools": r'''python3 -c "import json;print(json.load(open('docs/agent-templates/tool-manifest.json'))['tool_count'])"''',
}


def _read(rel_path: str) -> str:
    """Read a repository-relative UTF-8 text file."""
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _count_django_apps() -> int:
    """Count the entries of ``REQFLOW_APPS`` in the Django settings."""
    match = re.search(
        r"REQFLOW_APPS\s*=\s*\[(.*?)\n\]",
        _read("backend/reqogniloom/settings.py"),
        re.DOTALL,
    )
    if match is None:
        raise ValueError("REQFLOW_APPS list not found in settings.py")
    return len(re.findall(r'^\s+"[a-z_]+",', match.group(1), re.MULTILINE))


def _count_viewset_classes() -> int:
    """Count distinct ViewSet classes actually wired into the DRF router."""
    names: set[str] = set()
    for path in (REPO_ROOT / "backend" / "rest_api").rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "router.register(" not in line:
                continue
            # Docstrings may mention the router without registering anything.
            if "router-registered" in line or "router registers" in line:
                continue
            match = re.search(r",\s*(\w+ViewSet)\s*,", line)
            if match is not None:
                names.add(match.group(1))
    return len(names)


def _count_viewset_registrations() -> int:
    """Count real ``router.register(...)`` calls in the REST API URLconf."""
    return len(
        re.findall(
            r"^\s*router\.register\(",
            _read("backend/rest_api/urls.py"),
            re.MULTILINE,
        )
    )


def _count_files(rel_dir: str, pattern: str, *, exclude_tests: bool = False) -> int:
    """Count files matching ``pattern`` below a repository-relative directory."""
    root = REPO_ROOT / rel_dir
    return sum(
        1
        for path in root.rglob(pattern)
        if path.is_file()
        # Mirrors `find ... -not -path '*/tests/*'`.
        and not (exclude_tests and "tests" in path.parts)
    )


def _count_mcp_tools() -> int:
    """Read the canonical MCP tool count from the manifest."""
    manifest = json.loads(_read("docs/agent-templates/tool-manifest.json"))
    return int(manifest["tool_count"])


COUNT_FUNCS: dict[str, Callable[[], int]] = {
    "django_apps": _count_django_apps,
    "viewset_classes": _count_viewset_classes,
    "viewset_registrations": _count_viewset_registrations,
    "frontend_test_files": lambda: _count_files("frontend/src", "*.test.ts*"),
    "e2e_specs": lambda: _count_files("e2e", "*.spec.ts"),
    "backend_test_files": lambda: _count_files("backend", "test_*.py"),
    "service_files": lambda: _count_files(
        "backend", "*_service.py", exclude_tests=True
    ),
    "mcp_tools": _count_mcp_tools,
}


def generate_counts() -> dict[str, int]:
    """Return the eight measured counts keyed by stable identifier.

    The eight keys cover the seven DOC-008 figures (ViewSets are reported as
    both distinct classes and router registrations).
    """
    return {key: func() for key, func in COUNT_FUNCS.items()}


def main() -> None:
    """Print the measured counts as stable, sorted JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--commands",
        action="store_true",
        help="include the canonical shell command for each count",
    )
    args = parser.parse_args()
    counts = generate_counts()
    if args.commands:
        payload: dict[str, object] = {
            key: {"value": value, "command": COUNT_COMMANDS[key]}
            for key, value in counts.items()
        }
    else:
        payload = counts
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
