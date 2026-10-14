#!/usr/bin/env python3
"""Release ratchet for plugin packages (issues #1283 / #1284 / #1285).

``VERSION`` is the single source of truth for every first-party, in-repo
plugin artifact (ADR-017, Option A). This check runs *after* a release tag and
answers two questions that otherwise only surface as a silent
"installed != shipped" drift:

1. **Presence** — every first-party plugin package that the release claims to
   ship still exists as a *source* tree/manifest in the repo. This is the
   guard against the #1283/#1285 failure mode where a plugin package was
   reduced to a ``dist/``+``node_modules`` rump (so ``npm run build`` dies with
   ``ENOENT package.json``) or its whole source tree disappeared between two
   releases.
2. **Version consistency** — every version-coupled plugin/store manifest
   declares exactly the released ``VERSION``. The Hermes desktop plugin
   (``integrations/hermes-plugin/``) is hand-maintained, so unlike the
   ``dist/plugins/**`` builders it *can* drift; before this check that drift
   was invisible until someone diffed the carriers by hand.

Independently-versioned POC artifacts (the Python Hermes *agent* plugin,
ADR-017 decision 2: own SemVer + ``minServerVersion``) are checked for
presence only and are deliberately **not** forced onto ``VERSION``.

Usage::

    python scripts/check_plugin_packages.py              # against repo VERSION
    python scripts/check_plugin_packages.py --tag v1.8.0-beta.20
    python scripts/check_plugin_packages.py --expect-version 1.8.0-beta.20

Exit codes: 0 = all packages present and consistent, 1 = at least one problem,
2 = usage/IO error (unreadable VERSION or manifest).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = REPO_ROOT / "VERSION"


@dataclass(frozen=True)
class VersionLocation:
    """A concrete version string inside a manifest, addressed by a JSON path."""

    label: str
    path: str
    pointer: tuple[str | int, ...]


#: Version-coupled first-party plugin/store manifests. Each must carry exactly
#: the released ``VERSION`` (ADR-017 Option A).
VERSION_COUPLED: tuple[VersionLocation, ...] = (
    VersionLocation(
        "Hermes desktop plugin package.json",
        "integrations/hermes-plugin/reqogniloom/package.json",
        ("version",),
    ),
    VersionLocation(
        "Hermes desktop plugin manifest",
        "integrations/hermes-plugin/reqogniloom/hermes-plugin.json",
        ("version",),
    ),
    VersionLocation(
        "Hermes desktop plugin lockfile (root)",
        "integrations/hermes-plugin/reqogniloom/package-lock.json",
        ("version",),
    ),
    VersionLocation(
        "Hermes desktop plugin lockfile (packages[''])",
        "integrations/hermes-plugin/reqogniloom/package-lock.json",
        ("packages", "", "version"),
    ),
    VersionLocation(
        "Claude Code plugin manifest",
        "dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json",
        ("version",),
    ),
    VersionLocation(
        "Antigravity plugin manifest",
        "dist/plugins/antigravity/reqogniloom/plugin.json",
        ("version",),
    ),
    VersionLocation(
        "Claude Code marketplace",
        ".claude-plugin/marketplace.json",
        ("version",),
    ),
    VersionLocation(
        "Claude Code marketplace plugin entry",
        ".claude-plugin/marketplace.json",
        ("plugins", 0, "version"),
    ),
    VersionLocation(
        "MCP registry entry",
        "server.json",
        ("version",),
    ),
)

#: Source-tree files that must exist for a first-party plugin package to be
#: genuinely buildable from the repo (not a ``dist``+``node_modules`` rump).
REQUIRED_SOURCES: tuple[tuple[str, str], ...] = (
    ("Hermes desktop plugin package.json", "integrations/hermes-plugin/reqogniloom/package.json"),
    ("Hermes desktop plugin manifest", "integrations/hermes-plugin/reqogniloom/hermes-plugin.json"),
    ("Hermes desktop plugin lockfile", "integrations/hermes-plugin/reqogniloom/package-lock.json"),
    ("Hermes desktop plugin build guard", "integrations/hermes-plugin/reqogniloom/scripts/verify-build.mjs"),
    ("Hermes desktop plugin entry", "integrations/hermes-plugin/reqogniloom/src/activate.ts"),
    ("Claude Code plugin manifest", "dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json"),
    ("Antigravity plugin manifest", "dist/plugins/antigravity/reqogniloom/plugin.json"),
    ("Claude Code plugin builder", "dist/plugins/claude-code/build_claude_plugin.py"),
    ("Antigravity plugin builder", "dist/plugins/antigravity/build_antigravity_plugin.py"),
)

#: Independently-versioned POC artifacts (ADR-017 decision 2). Presence and a
#: non-empty version are required; the value must NOT be forced onto VERSION.
INDEPENDENT_POC: tuple[tuple[str, str], ...] = (
    ("Hermes agent plugin (POC)", "integrations/hermes-agent-plugin/plugin.yaml"),
    ("Hermes agent plugin dashboard manifest", "integrations/hermes-agent-plugin/dashboard/manifest.json"),
)

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def load_expected_version(repo_root: Path = REPO_ROOT) -> str:
    """Return the released version: the repo ``VERSION`` file, stripped."""
    version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError(f"{repo_root / 'VERSION'}: empty version")
    return version


def _dig(data: object, pointer: tuple[str | int, ...]) -> object:
    current = data
    for key in pointer:
        if isinstance(key, int):
            if not isinstance(current, list) or len(current) <= key:
                raise KeyError("/".join(str(k) for k in pointer))
            current = current[key]
        else:
            if not isinstance(current, dict) or key not in current:
                raise KeyError("/".join(str(k) for k in pointer))
            current = current[key]
    return current


def _read_yaml_field(path: Path, field: str) -> str | None:
    """Read a top-level scalar from a minimal YAML file without PyYAML.

    Only the flat ``key: value`` subset used by ``plugin.yaml`` /
    ``manifest.json`` is needed here, keeping this release check stdlib-only.
    """
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get(field)
        return None if value is None else str(value)
    pattern = re.compile(rf"^{re.escape(field)}\s*:\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip().strip("\"'")
    return None


def collect_problems(repo_root: Path, expected_version: str) -> list[str]:
    """Return every presence/version problem for the plugin packages.

    ``repo_root`` is a parameter (not the module constant) so the checks are
    testable against a temporary tree.
    """
    problems: list[str] = []

    for label, rel in REQUIRED_SOURCES:
        if not (repo_root / rel).is_file():
            problems.append(f"{label}: missing source file {rel}")

    # Cache parsed JSON per file so several pointers into the same manifest do
    # not re-read or re-parse it.
    parsed: dict[str, object] = {}
    for loc in VERSION_COUPLED:
        target = repo_root / loc.path
        if not target.is_file():
            problems.append(f"{loc.label}: missing {loc.path}")
            continue
        if loc.path not in parsed:
            try:
                parsed[loc.path] = json.loads(target.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                problems.append(f"{loc.label}: {loc.path} is not valid JSON: {exc}")
                parsed[loc.path] = None
        data = parsed[loc.path]
        if data is None:
            continue
        pointer = "/".join(str(k) for k in loc.pointer)
        try:
            value = _dig(data, loc.pointer)
        except KeyError:
            problems.append(f"{loc.label}: {loc.path} has no '{pointer}'")
            continue
        if value != expected_version:
            problems.append(
                f"{loc.label}: version {value!r} != VERSION {expected_version!r} "
                f"({loc.path} → {pointer})"
            )

    for label, rel in INDEPENDENT_POC:
        target = repo_root / rel
        if not target.is_file():
            problems.append(f"{label}: missing {rel}")
            continue
        version = _read_yaml_field(target, "version")
        if not version:
            problems.append(f"{label}: {rel} has no 'version'")
        elif not _VERSION_RE.match(version):
            problems.append(f"{label}: {rel} version {version!r} is not a concrete SemVer")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-version",
        help="version every coupled manifest must declare (default: repo VERSION)",
    )
    parser.add_argument(
        "--tag",
        help="release tag to check against (leading 'v' is stripped); "
        "mutually exclusive with --expect-version",
    )
    args = parser.parse_args(argv)

    if args.tag and args.expect_version:
        print("error: --tag and --expect-version are mutually exclusive", file=sys.stderr)
        return 2

    if args.expect_version:
        expected = args.expect_version.strip()
    elif args.tag:
        expected = args.tag.strip().lstrip("vV")
    else:
        try:
            expected = load_expected_version()
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if not _VERSION_RE.match(expected):
        print(f"error: expected version {expected!r} is not a concrete SemVer", file=sys.stderr)
        return 2

    problems = collect_problems(REPO_ROOT, expected)

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        print(
            f"plugin-packages: {len(problems)} problem(s) against VERSION {expected}",
            file=sys.stderr,
        )
        return 1

    print(
        f"plugin-packages: OK — {len(REQUIRED_SOURCES)} source(s), "
        f"{len(VERSION_COUPLED)} version location(s), "
        f"{len(INDEPENDENT_POC)} independent POC manifest(s) consistent with VERSION {expected}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
