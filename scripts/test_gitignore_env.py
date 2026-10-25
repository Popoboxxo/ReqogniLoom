"""Guard for the environment-file ignore rules (plan D / D2.6, ENT-X1 = A).

Background: three untracked ``.env.bak-*`` files with production secrets sat in
the repository root while ``.gitignore`` only covered ``.env``, ``.env.local``
and ``.env.*.local``. The repository is public, and ``secret-scan`` at the time
only knew the ``reqlo_`` key pattern — one ``git add -A`` would have published
the secrets (QR-S03, index §h).

ENT-X1 was answered "A — never shared", so the fix is the ignore rule, not a
key rotation. This test pins the rule so a later edit cannot silently drop it:

* ``.env`` and every ``.env.*`` sibling (including ``.env.bak-*``) are ignored,
* the tracked ``.env.example`` templates are explicitly re-included.

``git check-ignore`` exits 0 when a path is ignored and 1 when it is not; both
are asserted, so a rule that over- or under-matches fails loudly. A bare
``scripts/test_*.py`` runs in no CI job by default (RB-D18) — this file is
wired into ``agent-templates-test`` in the same PR.

Stdlib only; runs from the repo root.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _git_check_ignore(path: str) -> int:
    """Return ``git check-ignore -q``'s exit code for *path* (0 = ignored)."""
    return subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO_ROOT,
        check=False,
    ).returncode


def test_env_backup_file_is_ignored() -> None:
    assert _git_check_ignore(".env.bak-x") == 0


def test_env_backup_with_timestamp_is_ignored() -> None:
    assert _git_check_ignore(".env.bak-20261004-011947") == 0


def test_plain_env_file_is_ignored() -> None:
    assert _git_check_ignore(".env") == 0


def test_env_local_file_is_ignored() -> None:
    assert _git_check_ignore(".env.local") == 0


def test_env_example_is_not_ignored() -> None:
    assert _git_check_ignore(".env.example") == 1


def test_nested_env_example_is_not_ignored() -> None:
    """The pattern has no slash, so the negation must also reach subdirectories."""
    assert _git_check_ignore("frontend/.env.example") == 1
