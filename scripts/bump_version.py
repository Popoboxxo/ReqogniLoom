#!/usr/bin/env python3
"""Bump every release version carrier, then re-render the client artifacts.

Release process (issues #1349 / #1353):

1. create the release branch (never on ``main``/``master``),
2. ``python scripts/bump_version.py --version X.Y.Z``,
3. review the diff, commit, tag.

The script owns the *complete* carrier list, including the four hand-maintained
Hermes desktop-plugin version locations across
``integrations/hermes-plugin/reqogniloom/**`` that used to be missed by the
manual release commit. It sets the version *structurally* (JSON pointers,
env-var lines, compose defaults), so it also repairs a carrier that is already
stale before the bump. ``VERSION`` is the single source for the value
(ADR-017 Option A); the Hermes agent/dashboard plugin is deliberately NOT
touched because it carries its own SemVer + ``minServerVersion`` (ADR-017
decision 2).

After writing the carriers the script re-renders ``docs/clients/**``,
``.claude-plugin/marketplace.json`` and ``server.json`` (``render.py``), then
runs both release gates against the new version:

* ``scripts/check_plugin_packages.py --expect-version <new>``
* ``scripts/clients/render.py --check``

Usage::

    python scripts/bump_version.py --version 1.8.0-beta.22
    python scripts/bump_version.py --version 1.8.0-beta.22 --dry-run

Exit codes: 0 = bumped and verified, 2 = refused (main/master, bad version),
1 = a carrier is missing/unreadable or a gate failed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Reuse the single canonical list of VERSION-coupled JSON manifests so the
# release bump and the release ratchet can never disagree about the carriers.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_plugin_packages import VERSION_COUPLED

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

#: Text carriers whose version cannot be addressed as a JSON pointer.
TEXT_CARRIERS = (
    "VERSION",
    ".env.example",
    "deploy/docker-compose.yml",
    "deploy/docker-compose.minimal.yml",
    "site/index.html",
    "docs/CODEBASE_OVERVIEW.md",
    "docs/api/MCP-SURFACE.md",
    "systemagents/reqogniloom-operator.md",
)

_JSON_INDENT = 2


class BumpError(RuntimeError):
    """A carrier is missing/malformed or the checkout is not a release branch."""


def load_current_version(repo_root: Path = REPO_ROOT) -> str:
    try:
        version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BumpError(f"cannot read {repo_root / 'VERSION'}: {exc}") from exc
    if not version:
        raise BumpError(f"{repo_root / 'VERSION'}: empty version")
    return version


def validate_version(version: str) -> str:
    value = version.strip()
    if not _VERSION_RE.match(value):
        raise BumpError(f"{version!r} is not a concrete SemVer (e.g. 1.8.0-beta.22)")
    return value


def _git_branch(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BumpError(
            "cannot determine the git branch; run the release bump inside the "
            "release-branch checkout"
        ) from exc
    return result.stdout.strip()


def assert_release_branch(repo_root: Path = REPO_ROOT) -> str:
    """Refuse to bump on main/master or a detached HEAD (convention boundary)."""
    branch = _git_branch(repo_root)
    if branch in {"main", "master", "HEAD"}:
        raise BumpError(
            f"refusing to bump the release version on '{branch}'; create the "
            "release branch and run the bump there"
        )
    return branch


def _set_pointer(data: object, pointer: tuple[str | int, ...], value: str) -> bool:
    current = data
    for key in pointer[:-1]:
        current = current[key]  # type: ignore[index]
    last = pointer[-1]
    if current[last] == value:  # type: ignore[index]
        return False
    current[last] = value  # type: ignore[index]
    return True


def bump_json_carriers(
    repo_root: Path, new_version: str, *, dry_run: bool = False
) -> list[tuple[str, int]]:
    """Set every version-coupled JSON pointer to ``new_version``.

    Structural (not string-replace) so a stale carrier is repaired even when it
    does not currently match ``VERSION``.
    """
    changes: list[tuple[str, int]] = []
    per_file: dict[str, list[object]] = {}
    for loc in VERSION_COUPLED:
        per_file.setdefault(loc.path, []).append(loc)

    for rel_path, locations in per_file.items():
        target = repo_root / rel_path
        if not target.is_file():
            raise BumpError(f"missing version carrier: {rel_path}")
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BumpError(f"{rel_path}: invalid JSON: {exc}") from exc
        changed = 0
        for loc in locations:
            try:
                if _set_pointer(data, loc.pointer, new_version):
                    changed += 1
            except (KeyError, TypeError) as exc:
                pointer = "/".join(str(k) for k in loc.pointer)
                raise BumpError(
                    f"{rel_path}: no addressable '{pointer}' for {loc.label}"
                ) from exc
        if changed:
            if not dry_run:
                target.write_text(
                    json.dumps(data, indent=_JSON_INDENT, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            changes.append((rel_path, changed))
    return changes


def _subn(pattern: str, repl: str, text: str) -> tuple[str, int]:
    """Regex-substitute and count only actual changes (idempotent re-runs)."""
    updated, matches = re.subn(pattern, repl, text, flags=re.MULTILINE)
    return updated, matches if updated != text else 0


def bump_text_carriers(
    repo_root: Path,
    old_version: str,
    new_version: str,
    *,
    dry_run: bool = False,
) -> list[tuple[str, int]]:
    """Bump the text carriers (compose defaults, env, site, docs)."""
    changes: list[tuple[str, int]] = []

    for rel_path in TEXT_CARRIERS:
        target = repo_root / rel_path
        if not target.is_file():
            raise BumpError(f"missing version carrier: {rel_path}")
        text = target.read_text(encoding="utf-8")
        count = 0

        if rel_path == "VERSION":
            if text.strip() != new_version:
                text = f"{new_version}\n"
                count = 1
        elif rel_path == ".env.example":
            text, count = _subn(
                r"^# \S+(; keep REQOGNILOOM_VERSION.*)$", rf"# {new_version}\1", text
            )
            text, value_count = _subn(
                r"^REQOGNILOOM_VERSION=.*$", f"REQOGNILOOM_VERSION={new_version}", text
            )
            count += value_count
        elif rel_path.startswith("deploy/docker-compose"):
            text, count = _subn(
                r"(\$\{REQOGNILOOM_VERSION:-)[^}]+(\})",
                lambda match: f"{match.group(1)}{new_version}{match.group(2)}",
                text,
            )
        elif old_version != new_version:
            count = text.count(old_version)
            if count:
                text = text.replace(old_version, new_version)

        if count:
            if not dry_run:
                target.write_text(text, encoding="utf-8", newline="\n")
            changes.append((rel_path, count))

    return changes


def apply_bumps(
    repo_root: Path = REPO_ROOT, new_version: str = "", *, dry_run: bool = False
) -> list[tuple[str, int]]:
    """Apply every carrier bump and return ``(relative path, edits)``."""
    new_version = validate_version(new_version)
    old_version = load_current_version(repo_root)
    changes = bump_json_carriers(repo_root, new_version, dry_run=dry_run)
    changes += bump_text_carriers(
        repo_root, old_version, new_version, dry_run=dry_run
    )
    return changes


def render_client_artifacts(repo_root: Path = REPO_ROOT) -> None:
    """Re-render docs/clients/** and the store artifacts from VERSION (#1353)."""
    subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "clients" / "render.py")],
        cwd=repo_root,
        check=True,
    )


def run_release_gates(repo_root: Path = REPO_ROOT, new_version: str = "") -> None:
    new_version = validate_version(new_version)
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_plugin_packages.py"),
            "--expect-version",
            new_version,
        ],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "clients" / "render.py"), "--check"],
        cwd=repo_root,
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="new release version, e.g. 1.8.0-beta.22")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the carrier edits without writing or rendering",
    )
    args = parser.parse_args(argv)

    try:
        new_version = validate_version(args.version)
        branch = assert_release_branch()
        old_version = load_current_version()
        print(
            f"release-bump: {old_version} -> {new_version} on branch '{branch}'",
            flush=True,
        )
        changes = apply_bumps(REPO_ROOT, new_version, dry_run=args.dry_run)
    except BumpError as exc:
        print(f"release-bump: {exc}", file=sys.stderr)
        return 2

    for rel_path, count in changes:
        print(f"  updated {rel_path} ({count})", flush=True)
    if not changes:
        print("  no carrier changes (already at the requested version)", flush=True)
    if args.dry_run:
        print("release-bump: dry-run, nothing written", flush=True)
        return 0

    try:
        render_client_artifacts()
        run_release_gates(REPO_ROOT, new_version)
    except subprocess.CalledProcessError as exc:
        print(
            f"release-bump: release gate failed (exit {exc.returncode}); "
            "fix the reported drift before committing",
            file=sys.stderr,
        )
        return 1

    print(
        "release-bump: OK - carriers bumped, client artifacts re-rendered, "
        "ratchet + render --check green. Add the CHANGELOG.md entry next."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
