#!/usr/bin/env python3
"""Fail when a Compose or Django settings key is absent from ``.env.example``.

Issue #1737: a deployment that strictly follows ``.env.example`` silently ran a
partial stack because ``COMPOSE_PROFILES``, ``SESSION_COOKIE_SECURE`` and
others were undocumented. This gate compares the keys the shipped Compose files
interpolate and the keys ``settings.py`` reads via ``config(...)`` against
``.env.example`` (active **or** commented entries count as documented).

A key that appears twice as an *active* assignment is a second failure: two
values for one key are almost always a merge accident.

Usage:
    python scripts/check_env_example_keys.py
    python scripts/check_env_example_keys.py --root /tmp/fixture
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

COMPOSE_GLOB = "deploy/docker-compose*.yml"
SETTINGS_PATH = "backend/reqogniloom/settings.py"
ENV_EXAMPLE = ".env.example"

#: Keys that intentionally have no ``.env.example`` line. Each entry needs a
#: reason; "it is inconvenient" is not one.
ALLOWLIST: dict[str, str] = {
    "COMPOSE_PROFILES": (
        "read by Docker Compose itself (not by a container) and documented in "
        "the .env.example prose block, so it has no interpolation site"
    ),
}

_ENV_KEY = re.compile(r"^\s*#?\s*([A-Z0-9_]+)=", re.MULTILINE)
_ENV_ACTIVE = re.compile(r"^\s*([A-Z0-9_]+)=", re.MULTILINE)
_COMPOSE_BRACED = re.compile(r"\$\{([A-Z0-9_]+)")
_COMPOSE_BARE = re.compile(r"(?<!\$)\$([A-Z0-9_]{3,})")
_SETTINGS_KEY = re.compile(r"config\(\s*[\"']([A-Z0-9_]+)")


def _strip_comments(text: str) -> str:
    """Drop YAML ``#`` comments so prose like ``${VAR:-default}`` is ignored."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def compose_keys(root: Path) -> set[str]:
    """Return every variable the shipped Compose files interpolate."""
    keys: set[str] = set()
    for path in sorted(root.glob(COMPOSE_GLOB)):
        text = _strip_comments(path.read_text(encoding="utf-8"))
        # ``$${X}`` / ``$$HOSTNAME`` are escaped shell dollars, not Compose
        # variables: drop them before the variable scan.
        text = re.sub(r"\$\$(\{[^}]*\}|[A-Za-z_][A-Za-z0-9_]*)", "", text)
        keys.update(_COMPOSE_BRACED.findall(text))
        keys.update(_COMPOSE_BARE.findall(text))
    return keys


def settings_keys(root: Path) -> set[str]:
    """Return every key ``settings.py`` reads through ``config(...)``."""
    path = root / SETTINGS_PATH
    if not path.is_file():
        return set()
    return set(_SETTINGS_KEY.findall(path.read_text(encoding="utf-8")))


def env_keys(root: Path) -> tuple[set[str], dict[str, int]]:
    """Return (documented keys, active-definition counts) from ``.env.example``."""
    path = root / ENV_EXAMPLE
    if not path.is_file():
        return set(), {}
    text = path.read_text(encoding="utf-8")
    documented = set(_ENV_KEY.findall(text))
    counts: dict[str, int] = {}
    for key in _ENV_ACTIVE.findall(text):
        counts[key] = counts.get(key, 0) + 1
    return documented, counts


def collect_issues(root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """Return ``{"missing": [...], "duplicates": [...]}`` for *root*."""
    wanted = compose_keys(root) | settings_keys(root)
    documented, active = env_keys(root)
    missing = sorted(wanted - documented - set(ALLOWLIST))
    duplicates = sorted(key for key, count in active.items() if count > 1)
    return {"missing": missing, "duplicates": duplicates}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: the checkout containing this script).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args(argv)

    issues = collect_issues(args.root)
    if args.json:
        print(json.dumps(issues, indent=2, sort_keys=True))
    else:
        if issues["missing"]:
            print("Missing from .env.example:")
            for key in issues["missing"]:
                print(f"  - {key}")
        if issues["duplicates"]:
            print("Defined more than once (active assignment):")
            for key in issues["duplicates"]:
                print(f"  - {key}")
        if not issues["missing"] and not issues["duplicates"]:
            print("OK: every Compose/settings key is documented once.")
    return 1 if issues["missing"] or issues["duplicates"] else 0


if __name__ == "__main__":
    sys.exit(main())
