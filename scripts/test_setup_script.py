"""Contract tests for ``scripts/setup.sh`` (plan D3.2, #792 points 7 and 12).

The script is the one-step onboarding path: it copies ``.env.example`` to the
target env file, generates the secrets that still carry a ``CHANGE-ME`` marker,
locks the file to mode 600 and (with ``--check-ports``) refuses to continue when
``BACKEND_PORT``/``FRONTEND_PORT`` are already bound.

What is pinned here — each assertion maps to a requirement, not to an
implementation detail:

* a first run creates the file and replaces **every** placeholder,
* a second run changes nothing (idempotent, plan D3.2),
* ``FIELD_ENCRYPTION_KEY`` is a real Fernet key, not just "32 bytes" — a bad key
  would only fail at first start, which is the worst possible moment,
* a busy port exits 2 with the documented message,
* a backup of an existing env file lands **outside** the repository under
  ``$XDG_STATE_HOME/reqogniloom/env-backups`` with mode 600 and never as a
  ``.env.bak*`` next to the file (QR-S03: the 2026-10-21 incident was exactly a
  secret-bearing untracked backup in the repo),
* an env file inside a checkout that git does not ignore is refused (exit 3).

``cryptography`` is the only third-party import; ``agent-templates-test``
installs it in the same PR (RB-D18: a bare ``scripts/test_*.py`` runs nowhere).

Runs from the repo root; uses a temporary directory per test.
"""
from __future__ import annotations

import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup.sh"

GENERATED_KEYS = (
    "SECRET_KEY",
    "AUTH_JWT_SECRET",
    "DB_PASSWORD",
    "DB_APP_PASSWORD",
    "SYSTEM_ADMIN_PASSWORD",
    "FIELD_ENCRYPTION_KEY",
)


def run_setup(*args: str, state_home: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the script with an isolated XDG_STATE_HOME (so no real state is touched)."""
    env = os.environ.copy()
    if state_home is not None:
        env["XDG_STATE_HOME"] = str(state_home)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=False,
    )


def _value(text: str, key: str) -> str:
    match = re.search(rf"^{key}=(.*)$", text, re.MULTILINE)
    assert match is not None, f"{key} missing from the env file"
    return match.group(1)


def test_first_run_creates_env_and_replaces_placeholders(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    result = run_setup("--env-file", str(env_file), state_home=tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert env_file.is_file()

    text = env_file.read_text()
    for key in GENERATED_KEYS:
        value = _value(text, key)
        assert value, f"{key} is empty"
        assert not value.startswith("CHANGE-ME"), f"{key} still carries the template marker"

    # Values must never be echoed — only the key names.
    assert "generated: SECRET_KEY" in result.stdout
    assert _value(text, "SECRET_KEY") not in result.stdout
    assert _value(text, "DB_PASSWORD") not in result.stdout


def test_env_file_is_mode_600(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    assert run_setup("--env-file", str(env_file), state_home=tmp_path / "state").returncode == 0
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_secrets_have_the_documented_shape(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    assert run_setup("--env-file", str(env_file), state_home=tmp_path / "state").returncode == 0
    text = env_file.read_text()

    # openssl rand -hex 50 -> 100 hex characters.
    assert re.fullmatch(r"[0-9a-f]{100}", _value(text, "SECRET_KEY"))
    assert re.fullmatch(r"[0-9a-f]{100}", _value(text, "AUTH_JWT_SECRET"))
    # Base64 characters that need .env quoting are stripped from the passwords.
    for key in ("DB_PASSWORD", "DB_APP_PASSWORD", "SYSTEM_ADMIN_PASSWORD"):
        assert not re.search(r"[/+=]", _value(text, key)), key


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    state = tmp_path / "state"
    assert run_setup("--env-file", str(env_file), state_home=state).returncode == 0
    first = env_file.read_text()

    second = run_setup("--env-file", str(env_file), state_home=state)

    assert second.returncode == 0, second.stderr
    assert env_file.read_text() == first
    assert not list((state / "reqogniloom" / "env-backups").glob("*.env"))


def test_field_encryption_key_is_a_valid_fernet_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    assert run_setup("--env-file", str(env_file), state_home=tmp_path / "state").returncode == 0

    key = _value(env_file.read_text(), "FIELD_ENCRYPTION_KEY")
    fernet = Fernet(key.encode())
    assert fernet.decrypt(fernet.encrypt(b"reqogniloom")) == b"reqogniloom"


def test_busy_port_exits_2(tmp_path: Path) -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    env_file = tmp_path / ".env"
    env_file.write_text(f"BACKEND_PORT={port}\n")
    try:
        result = run_setup("--env-file", str(env_file), "--check-ports", state_home=tmp_path / "state")
    finally:
        server.close()

    assert result.returncode == 2, (result.stdout, result.stderr)
    assert f"Port {port} is already in use" in result.stderr
    # The message must name the knob, not just the port.
    assert "BACKEND_PORT/FRONTEND_PORT" in result.stderr


def test_backup_lands_outside_repo_with_mode_600(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    state = tmp_path / "state"
    assert run_setup("--env-file", str(env_file), state_home=state).returncode == 0

    # Simulate a template that gained one more placeholder later.
    text = env_file.read_text()
    env_file.write_text(
        re.sub(r"(?m)^DB_APP_PASSWORD=.*$", "DB_APP_PASSWORD=CHANGE-ME-strong-app-password", text)
    )

    repo_env_files_before = set(REPO_ROOT.glob(".env*"))
    result = run_setup("--env-file", str(env_file), state_home=state)
    repo_env_files_after = set(REPO_ROOT.glob(".env*"))

    assert result.returncode == 0, result.stderr
    assert "CHANGE-ME" not in _value(env_file.read_text(), "DB_APP_PASSWORD")

    backups = list((state / "reqogniloom" / "env-backups").glob("*.env"))
    assert len(backups) == 1, backups
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    # The backup holds the pre-edit state, including the placeholder.
    assert "DB_APP_PASSWORD=CHANGE-ME" in backups[0].read_text()

    # No secret artifact appeared in the checkout or next to the env file.
    assert repo_env_files_after == repo_env_files_before
    assert not list(tmp_path.glob(".env.bak*"))


def test_env_file_inside_checkout_must_be_git_ignored(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "setup.sh").write_text(SCRIPT.read_text())
    (repo / ".env.example").write_text((REPO_ROOT / ".env.example").read_text())
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    result = subprocess.run(
        ["bash", str(repo / "scripts" / "setup.sh"), "--env-file", str(repo / ".env")],
        capture_output=True,
        text=True,
        env={**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")},
        cwd=str(repo),
        check=False,
    )

    assert result.returncode == 3, (result.stdout, result.stderr)
    assert "not git-ignored" in result.stderr


if __name__ == "__main__":  # pragma: no cover - convenience only
    sys.exit(pytest.main([__file__, "-q"]))
