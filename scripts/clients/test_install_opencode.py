"""Tests for the OpenCode installer paths in ``scripts/clients/install.sh``.

These pin Task 4 of the OpenCode V2 plan
(``docs/superpowers/plans/2026-11-01-opencode-v2-support.md``):

* the V2 path merges ``mcp.servers.reqogniloom`` through
  ``dist/opencode/merge_config.py`` and never puts a literal key in the config,
* ``--client opencode`` auto-detects the client binary's major version and
  falls back to the unchanged V1 path when the version is missing/garbled,
* ``--key-env`` is validated as an env-var *name* (no config-injection path),
* ``--dry-run`` stays side-effect free.

Each test runs the real installer as a subprocess against a scratch ``HOME`` /
``XDG_CONFIG_HOME`` and a fake ``opencode`` on ``PATH``; nothing touches the
developer's own ``~/.config/opencode``. ``install.sh`` ends with
``exec bash verify.sh``, so the fake also answers ``mcp list`` with a
``reqogniloom`` marker — otherwise every non-dry-run install would fail in the
verification step rather than in the code under test.

Only stdlib; runs from the repo root.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "scripts" / "clients" / "install.sh"

FAKE_OPENCODE = """#!/usr/bin/env bash
# Fake opencode binary for scripts/clients/test_install_opencode.py.
case "${1:-}" in
  --version)
    printf '%s\\n' "${FAKE_VERSION:-}"
    exit 0
    ;;
  mcp)
    case "${2:-}" in
      add)
        if [ -n "${FAKE_MCP_LOG:-}" ]; then
          printf '%s\\n' "$*" >> "$FAKE_MCP_LOG"
        fi
        exit 0
        ;;
      list)
        printf 'reqogniloom  connected\\n'
        exit 0
        ;;
    esac
    ;;
esac
exit 0
"""


def _install_fake(tmp_path: Path) -> Path:
    """Write the fake ``opencode`` into ``tmp_path/bin`` and return that dir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "opencode"
    fake.write_text(FAKE_OPENCODE, encoding="utf-8")
    fake.chmod(0o755)
    return bin_dir


def _path_without_opencode() -> str:
    """PATH minus every directory that would supply a real ``opencode``.

    The "binary missing" case must not accidentally pick up a developer's
    installed client, which would flip the result to the V1 or V2 path.
    """
    kept = [
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and not (Path(entry) / "opencode").exists()
    ]
    return os.pathsep.join(kept)


def _run(args, env, tmp_path: Path, fake_bin: Path | None) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True, exist_ok=True)
    run_env = dict(os.environ)
    run_env.pop("OPENCODE_BIN", None)
    run_env["HOME"] = str(home)
    run_env["XDG_CONFIG_HOME"] = str(home / ".config")
    run_env["PATH"] = (
        os.pathsep.join([str(fake_bin), os.environ.get("PATH", "")])
        if fake_bin is not None
        else _path_without_opencode()
    )
    run_env.update(env)
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args, "--yes"],
        cwd=str(REPO_ROOT),
        env=run_env,
        text=True,
        capture_output=True,
    )


def run_install(args, env, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run ``install.sh <args> --yes`` with a fake ``opencode`` on PATH."""
    return _run(args, env, tmp_path, _install_fake(tmp_path))


def run_install_without_binary(args, env, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run ``install.sh <args> --yes`` with no ``opencode`` on PATH at all."""
    return _run(args, env, tmp_path, None)


def config_path(tmp_path: Path) -> Path:
    return tmp_path / "home" / ".config" / "opencode" / "opencode.json"


def v2_args(*extra: str) -> list[str]:
    return [
        "--client",
        "opencode-v2",
        "--url",
        "http://h:8001",
        "--key-env",
        "MY_KEY",
        *extra,
    ]


def test_v2_writes_servers_entry_with_env_key_only(tmp_path: Path) -> None:
    log = tmp_path / "mcp-add.log"
    skills = tmp_path / "skills"
    result = run_install(
        v2_args("--skills-dir", str(skills)),
        {"FAKE_VERSION": "2.0.0-beta.3", "FAKE_MCP_LOG": str(log)},
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    raw = config_path(tmp_path).read_text(encoding="utf-8")
    entry = json.loads(raw)["mcp"]["servers"]["reqogniloom"]
    assert entry["url"] == "http://h:8001/mcp/"
    assert entry["headers"]["X-API-Key"] == "{env:MY_KEY}"
    assert entry["oauth"] is False
    assert "reqlo_" not in raw
    # The V2 path copies the same packaged skills into --skills-dir ...
    assert (skills / "traceability-audit" / "SKILL.md").is_file()
    # ... and ends in the V2 flavour of verify.sh.
    assert "info: OpenCode V2 is a beta; config lives in mcp.servers.reqogniloom" in result.stdout


def test_auto_detect_picks_v2_for_major_2(tmp_path: Path) -> None:
    log = tmp_path / "mcp-add.log"
    result = run_install(
        ["--client", "opencode", "--url", "http://h:8001", "--key-env", "MY_KEY",
         "--skills-dir", str(tmp_path / "skills")],
        {"FAKE_VERSION": "2.0.0-beta.3", "FAKE_MCP_LOG": str(log)},
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    entry = json.loads(config_path(tmp_path).read_text(encoding="utf-8"))["mcp"]["servers"][
        "reqogniloom"
    ]
    assert entry["url"] == "http://h:8001/mcp/"
    assert not log.exists() or log.read_text(encoding="utf-8") == ""


def test_auto_detect_handles_program_prefixed_version(tmp_path: Path) -> None:
    log = tmp_path / "mcp-add.log"
    result = run_install(
        ["--client", "opencode", "--url", "http://h:8001", "--key-env", "MY_KEY",
         "--skills-dir", str(tmp_path / "skills")],
        {"FAKE_VERSION": "opencode v2.2.5", "FAKE_MCP_LOG": str(log)},
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    entry = json.loads(config_path(tmp_path).read_text(encoding="utf-8"))["mcp"]["servers"][
        "reqogniloom"
    ]
    assert entry["url"] == "http://h:8001/mcp/"
    assert not log.exists() or log.read_text(encoding="utf-8") == ""


def test_auto_detect_picks_v1_for_major_1(tmp_path: Path) -> None:
    log = tmp_path / "mcp-add.log"
    result = run_install(
        ["--client", "opencode", "--url", "http://h:8001", "--key-env", "MY_KEY",
         "--skills-dir", str(tmp_path / "skills")],
        {"FAKE_VERSION": "1.18.35", "FAKE_MCP_LOG": str(log)},
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "/mcp/sse/" in log.read_text(encoding="utf-8")
    assert not config_path(tmp_path).exists()


def test_missing_or_garbled_version_falls_back_to_v1(tmp_path: Path) -> None:
    garbled_log = tmp_path / "garbled.log"
    garbled = run_install(
        ["--client", "opencode", "--url", "http://h:8001", "--key-env", "MY_KEY",
         "--skills-dir", str(tmp_path / "skills")],
        {"FAKE_VERSION": "garbage", "FAKE_MCP_LOG": str(garbled_log)},
        tmp_path,
    )
    assert garbled.returncode == 0, garbled.stderr
    assert "/mcp/sse/" in garbled_log.read_text(encoding="utf-8")
    assert not config_path(tmp_path).exists()

    # No binary at all: --dry-run keeps require_bin from exiting 3, so the V1
    # path is observable (and a pipefail abort in detect_opencode_major would
    # still fail this run).
    missing = run_install_without_binary(
        ["--client", "opencode", "--url", "http://h:8001", "--key-env", "MY_KEY",
         "--skills-dir", str(tmp_path / "skills"), "--dry-run"],
        {},
        tmp_path,
    )
    assert missing.returncode == 0, missing.stderr
    assert "[dry-run] " in missing.stdout
    assert "/mcp/sse/" in missing.stdout
    assert not config_path(tmp_path).exists()


def test_v2_rerun_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "mcp-add.log"
    args = v2_args("--skills-dir", str(tmp_path / "skills"))
    env = {"FAKE_VERSION": "2.0.0-beta.3", "FAKE_MCP_LOG": str(log)}

    assert run_install(args, env, tmp_path).returncode == 0
    first = config_path(tmp_path).read_text(encoding="utf-8")
    assert run_install(args, env, tmp_path).returncode == 0
    second = config_path(tmp_path).read_text(encoding="utf-8")

    assert second == first
    assert len(list(config_path(tmp_path).parent.glob("opencode.json.bak-*"))) <= 1


def test_v2_keeps_existing_servers(tmp_path: Path) -> None:
    path = config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mcp": {
                    "servers": {"other": {"type": "local", "command": ["x"]}},
                    "legacy": {"type": "remote", "url": "http://legacy/mcp/"},
                },
                "model": "m",
            }
        ),
        encoding="utf-8",
    )

    result = run_install(
        v2_args("--skills-dir", str(tmp_path / "skills")),
        {"FAKE_VERSION": "2.0.0-beta.3", "FAKE_MCP_LOG": str(tmp_path / "log")},
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["mcp"]["servers"]["other"] == {"type": "local", "command": ["x"]}
    assert config["mcp"]["legacy"] == {"type": "remote", "url": "http://legacy/mcp/"}
    assert config["model"] == "m"
    assert config["mcp"]["servers"]["reqogniloom"]["url"] == "http://h:8001/mcp/"


def test_v2_aborts_on_jsonc_without_touching_file(tmp_path: Path) -> None:
    path = config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = "// comment\n{}\n"
    path.write_text(original, encoding="utf-8")

    result = run_install(
        v2_args("--skills-dir", str(tmp_path / "skills")),
        {"FAKE_VERSION": "2.0.0-beta.3", "FAKE_MCP_LOG": str(tmp_path / "log")},
        tmp_path,
    )

    assert result.returncode != 0
    assert path.read_text(encoding="utf-8") == original


def test_bad_key_env_is_rejected(tmp_path: Path) -> None:
    result = run_install(
        ["--client", "opencode-v2", "--url", "http://h:8001", "--key-env", "A B",
         "--skills-dir", str(tmp_path / "skills")],
        {"FAKE_VERSION": "2.0.0-beta.3", "FAKE_MCP_LOG": str(tmp_path / "log")},
        tmp_path,
    )

    assert result.returncode != 0
    assert "env-var name" in result.stderr
    assert not config_path(tmp_path).exists()


def test_dry_run_v2_writes_nothing(tmp_path: Path) -> None:
    result = run_install(
        v2_args("--skills-dir", str(tmp_path / "skills"), "--dry-run"),
        {"FAKE_VERSION": "2.0.0-beta.3", "FAKE_MCP_LOG": str(tmp_path / "log")},
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert not config_path(tmp_path).exists()
    dry_lines = [line for line in result.stdout.splitlines() if line.startswith("[dry-run]")]
    assert dry_lines
    assert any("merge_config.py" in line for line in dry_lines)
