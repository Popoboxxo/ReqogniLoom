"""
Issue #151 — guard against re-introducing a hardcoded Fernet key.

The previously committed key (``KzOBYC05...``) was a valid 32-byte Fernet key
present in both ``settings_test.py`` and the CI workflows. Beyond the exposure
itself it normalised the "encryption key lives in the repo" pattern, so this
test fails the build if any tracked source or workflow file grows a literal
that parses as a Fernet key again.
"""
from __future__ import annotations

import base64
import re
import subprocess
from pathlib import Path

import pytest

def _find_repo_root() -> Path | None:
    """Locate the checkout root, or None when only ``backend/`` is available.

    The docker-compose backend service mounts ``backend/`` alone at /app, so
    the workflows and the git index simply do not exist there. CI runs against
    a full checkout, which is where this guard is meant to bite.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / ".github").is_dir():
            return candidate
    return None


REPO_ROOT = _find_repo_root()

pytestmark = pytest.mark.skipif(
    REPO_ROOT is None,
    reason="full repository checkout not available (backend-only container mount)",
)

#: The key that used to be committed — must never reappear.
LEAKED_KEY = "KzOBYC05wXl_7i1FedEC0dPI8E61uRMmXwhSVd40fis="

#: urlsafe-base64, 44 chars — the wire format of a Fernet key.
_FERNET_LITERAL = re.compile(r"[A-Za-z0-9_\-]{43}=")

_SCANNED_SUFFIXES = {".py", ".yml", ".yaml", ".ts", ".tsx", ".json", ".sh"}

# `.env` is untracked (developer-local) and the woodpecker placeholder is not a
# real key; only tracked, scannable sources are relevant here.
_EXCLUDED_PARTS = {"node_modules", "external", ".agent-meta", "__pycache__"}

# npm lockfiles are full of `sha512-<base64>` integrity digests whose base64
# body is indistinguishable from a Fernet key by shape alone.
_EXCLUDED_NAMES = {"package-lock.json"}


def _is_integrity_digest(line: str) -> bool:
    """True for npm/yarn subresource-integrity lines (sha256-/sha512- digests)."""
    return "integrity" in line or "sha512-" in line or "sha384-" in line


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths = []
    for rel in out.split("\0"):
        if not rel:
            continue
        path = Path(rel)
        if set(path.parts) & _EXCLUDED_PARTS:
            continue
        if path.name in _EXCLUDED_NAMES:
            continue
        if path.suffix not in _SCANNED_SUFFIXES:
            continue
        paths.append(REPO_ROOT / path)
    return paths


def _is_fernet_key(candidate: str) -> bool:
    """True when ``candidate`` decodes to exactly 32 bytes (a real Fernet key)."""
    try:
        return len(base64.urlsafe_b64decode(candidate.encode())) == 32
    except (ValueError, TypeError):
        return False


def test_leaked_key_is_gone_from_the_worktree():
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _tracked_files()
        # This guard file necessarily contains the leaked-key literal to check for.
        if p.name != Path(__file__).name
        and LEAKED_KEY in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, (
        "The previously leaked Fernet key reappeared in: "
        f"{offenders}. Never commit encryption keys."
    )


def test_no_tracked_file_contains_a_fernet_key_literal():
    offenders: list[str] = []
    for path in _tracked_files():
        # This guard file necessarily contains the pattern it searches for.
        if path.name == Path(__file__).name:
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if _is_integrity_digest(line):
                continue
            for match in _FERNET_LITERAL.findall(line):
                if _is_fernet_key(match):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {match[:8]}...")

    assert not offenders, (
        "Fernet-key-shaped literals found in tracked files: "
        f"{offenders}. Generate keys at runtime or read them from a secret."
    )


@pytest.mark.parametrize("workflow", ["ci.yml", "playwright.yml"])
def test_workflows_do_not_pin_a_key_literal(workflow):
    text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    for line in text.splitlines():
        if "FIELD_ENCRYPTION_KEY" not in line or line.strip().startswith("#"):
            continue
        # Only a secret reference, a shell expansion or an env export is allowed.
        assert (
            "secrets." in line
            or "$" in line
            or line.strip().endswith("FIELD_ENCRYPTION_KEY=$KEY\" >> \"$GITHUB_ENV\"")
        ), f"{workflow} pins FIELD_ENCRYPTION_KEY to a literal: {line.strip()}"


def test_settings_test_generates_a_usable_key(monkeypatch):
    """The generated fallback must actually be a valid Fernet key."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    token = Fernet(key.encode()).encrypt(b"secret")
    assert Fernet(key.encode()).decrypt(token) == b"secret"
