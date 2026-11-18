"""Guard for the extended npm dependency-audit scope (DEP-006, S5.1 WP-3).

DEP-006 found that only ``/frontend`` (npm) and ``/backend`` (pip) were in the
Dependabot / audit scope while ``e2e/``, the repository root and ``promptfoo/``
had committed lockfiles that no gate ever refreshed or scanned. This guard
keeps that scope honest:

* every in-scope directory with a ``package-lock.json`` has a Dependabot npm
  entry (so the lock cannot silently rot);
* every in-scope lockfile is scanned by an npm-audit gate -- either the
  existing ``ci.yml`` frontend job or the new
  ``dependency-audit-extended.yml`` workflow (so no tree is left unscanned);
* the extended gate reuses the single shared waiver file and does not weaken
  the fail-closed logic; and
* the e2e convenience script no longer fetches ``@playwright/mcp@latest``.

Mirrors ``scripts/tests/test_npm_audit_waivers.py``: stdlib + PyYAML, reads the
repo as data. Wired into the repository-tests step of ci.yml by the caller.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
EXTENDED = REPO_ROOT / ".github" / "workflows" / "dependency-audit-extended.yml"
E2E_PACKAGE = REPO_ROOT / "e2e" / "package.json"
WAIVERS = REPO_ROOT / ".github" / "npm-audit-waivers.json"

# The Hermes plugin tree is a separate, externally-owned contract finding
# (CR-24 / DEP-003), explicitly out of the S5.1 WP-3 "e2e/root/promptfoo"
# scope. `.agent-meta` is a git submodule, not part of this repo's dep graph.
# Everything else with a package-lock.json must be covered by a gate.
OUT_OF_SCOPE_LOCK_DIRS = {"integrations/hermes-plugin/reqogniloom"}

# ci.yml's dependency-audit job scans the frontend lockfile in place. Assert
# that this remains true below so the union with the extended workflow is real.
CI_SCANNED_DIRS = {"frontend"}

FORBIDDEN_AUDIT_FLAGS = (
    "--audit-level=critical",
    "--audit-level=moderate",
    "--audit-level=low",
    "--audit-level=none",
    "--omit=dev",
    "--omit=optional",
    "--production",
    "|| true",
)


def _norm_dir(value: object) -> str:
    """Normalise a Dependabot/matrix directory to a comparable relative path."""
    text = str(value).strip("/")
    return text if text else "."


def _lock_dirs() -> set[str]:
    """All tracked-ish directories with a package-lock.json, excluding noise."""
    dirs: set[str] = set()
    noise = {".git", "node_modules", ".venv", "venv", ".tox", ".agent-meta"}
    for lock in REPO_ROOT.rglob("package-lock.json"):
        rel = lock.relative_to(REPO_ROOT)
        if any(part in noise for part in rel.parts[:-1]):
            continue
        dirs.add(_norm_dir(rel.parent))
    return dirs


def _in_scope_lock_dirs() -> set[str]:
    lock_dirs = _lock_dirs()
    assert lock_dirs, "no package-lock.json files discovered — test is misconfigured"
    return lock_dirs - OUT_OF_SCOPE_LOCK_DIRS


def _dependabot_dirs(doc: dict, ecosystem: str) -> set[str]:
    covered: set[str] = set()
    for entry in doc.get("updates", []):
        if entry.get("package-ecosystem") != ecosystem:
            continue
        if "directory" in entry:
            covered.add(_norm_dir(entry["directory"]))
        for directory in entry.get("directories", []) or []:
            covered.add(_norm_dir(directory))
    return covered


def _extended_matrix_dirs(doc: dict) -> set[str]:
    matrix = doc["jobs"]["dependency-audit-extended"]["strategy"]["matrix"]
    if "directory" in matrix:
        return {_norm_dir(value) for value in matrix["directory"]}
    # `include:` gives each directory a human-readable label for job names.
    return {_norm_dir(entry["directory"]) for entry in matrix["include"]}


# ---------------------------------------------------------------------------
# 1. Dependabot covers every directory that has a lockfile.
# ---------------------------------------------------------------------------
def test_dependabot_covers_every_lockfile_dir() -> None:
    doc = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    covered = _dependabot_dirs(doc, "npm")
    lock_dirs = _in_scope_lock_dirs()
    missing = sorted(lock_dirs - covered)
    assert not missing, (
        f"Dependabot npm scope is missing lockfile directories: {missing}. "
        "A committed lockfile without an update entry silently rots."
    )


# ---------------------------------------------------------------------------
# 2. Every lockfile is scanned by some npm-audit gate.
# ---------------------------------------------------------------------------
def test_ci_still_scans_the_frontend_lockfile() -> None:
    text = CI.read_text(encoding="utf-8")
    assert "Frontend - npm audit (fails on high/critical)" in text
    assert "working-directory: frontend" in text


def test_extended_workflow_exists() -> None:
    assert EXTENDED.is_file(), f"missing {EXTENDED} — DEP-006 audit gap is open"


def test_every_lockfile_is_scanned_by_some_workflow() -> None:
    assert EXTENDED.is_file(), f"missing {EXTENDED}"
    doc = yaml.safe_load(EXTENDED.read_text(encoding="utf-8"))
    scanned = CI_SCANNED_DIRS | _extended_matrix_dirs(doc)
    lock_dirs = _in_scope_lock_dirs()
    missing = sorted(lock_dirs - scanned)
    assert not missing, (
        f"lockfile directories not covered by any npm-audit gate: {missing}. "
        "ci.yml covers frontend; the extended workflow must cover the rest."
    )


def test_extended_gate_reuses_shared_waiver_without_weakening() -> None:
    """The extended audit must be the same gate, not a second/looser one."""
    assert EXTENDED.is_file(), f"missing {EXTENDED}"
    text = EXTENDED.read_text(encoding="utf-8")
    assert "npm audit --prefix" in text, "extended gate must run npm audit per prefix"
    assert "--json" in text, "extended gate must consume npm audit JSON"
    assert WAIVERS.name in text, "must reuse the single shared waiver file"
    assert "npm-audit-waivers" in text
    assert "GHSA_RE" in text, "must run the same GHSA waiver parser as ci.yml"
    # Split off the inline Python docs: comments there mention why `|| true`
    # is forbidden, which is not a shell command.
    shell = text.split("<<'PY'", 1)[0]
    shell = "\n".join(line for line in shell.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in FORBIDDEN_AUDIT_FLAGS:
        assert forbidden not in shell, f"extended gate was weakened with {forbidden!r}"


# ---------------------------------------------------------------------------
# 3. e2e convenience script must not float on @latest.
# ---------------------------------------------------------------------------
def test_e2e_package_json_has_no_floating_latest() -> None:
    raw = E2E_PACKAGE.read_text(encoding="utf-8")
    data = json.loads(raw)
    scripts = data.get("scripts", {})
    assert "@latest" not in json.dumps(scripts), (
        "e2e scripts fetch a floating @latest version — pin an exact version"
    )
    command = scripts.get("mcp:playwright", "")
    assert "@playwright/mcp@" in command, "mcp:playwright must reference @playwright/mcp"
    pinned = command.split("@playwright/mcp@", 1)[1].split()[0]
    assert pinned and pinned[0].isdigit(), (
        f"mcp:playwright must be pinned to an exact version, got {pinned!r}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
