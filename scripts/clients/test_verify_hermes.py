"""Tests for the Hermes branch of ``verify.sh`` (#1914).

A copied plugin install goes stale while a symlink follows ``git pull``. The
verifier therefore compares the installed SemVer with the shipped manifest and
must fail loudly (with the explicit --refresh update path) on drift. A fake
``hermes`` binary keeps the test independent of a real host, stack or socket.
"""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY = REPO_ROOT / "scripts" / "clients" / "verify.sh"
PLUGIN_YAML = REPO_ROOT / "integrations" / "hermes-agent-plugin" / "plugin.yaml"


def _installed_version() -> str:
    for line in PLUGIN_YAML.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"')
    raise AssertionError(f"no version in {PLUGIN_YAML}")


def _run(tmp_path: Path, *, installed: str | None) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    hermes = bin_dir / "hermes"
    hermes.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"mcp\" ] && [ \"$2\" = \"test\" ]; then\n"
        "  echo '✓ reqogniloom  Connected'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'unexpected invocation' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR)

    home = tmp_path / "home"
    plugins = home / ".hermes" / "plugins" / "reqogniloom"
    if installed is not None:
        plugins.mkdir(parents=True, exist_ok=True)
        (plugins / "plugin.yaml").write_text(
            f"name: reqogniloom\nversion: {installed}\n", encoding="utf-8"
        )

    env = {
        "HOME": str(home),
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
    }
    return subprocess.run(
        ["bash", str(VERIFY), "--client", "hermes"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_stale_install_fails_with_update_path(tmp_path: Path) -> None:
    result = _run(tmp_path, installed="0.1.0")

    assert result.returncode != 0
    assert "#1914" in result.stderr
    assert "--refresh" in result.stderr
    assert "0.1.0" in result.stderr


def test_matching_install_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, installed=_installed_version())

    assert result.returncode == 0, result.stderr
    assert "matches shipped manifest" in result.stdout


def test_missing_optional_plugin_is_only_info(tmp_path: Path) -> None:
    result = _run(tmp_path, installed=None)

    assert result.returncode == 0, result.stderr
    assert "no agent/dashboard plugin" in result.stdout
