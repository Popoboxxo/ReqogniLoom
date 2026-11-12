"""Tests for the OpenCode branch of ``verify.sh``.

Two findings from the live Phase-C verification are pinned here:

1. OpenCode V2's background service re-reads the config with a delay, so a
   single immediate ``mcp list`` produced a false negative. The verifier now
   retries.
2. OpenCode also loads a project-root config, so running the check inside the
   checkout mixed the maintainer's own servers into the result. The verifier
   now runs from a temporary directory.

The fake client records its working directory and its call count, so both
properties are observable without a browser, a stack, or a socket.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY = REPO_ROOT / "scripts" / "clients" / "verify.sh"


def _fake_opencode(tmp_path: Path, *, succeed_on: int) -> tuple[Path, Path, Path]:
    """Create a fake ``opencode`` that succeeds on call number ``succeed_on``.

    ``succeed_on=0`` never succeeds. Returns (bin_dir, cwd_log, call_log).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cwd_log = tmp_path / "cwd.log"
    call_log = tmp_path / "calls.log"
    script = bin_dir / "opencode"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$PWD" >> "{cwd_log}"\n'
        f'echo call >> "{call_log}"\n'
        f"calls=$(wc -l < \"{call_log}\")\n"
        "if [ \"$1\" = \"mcp\" ] && [ \"$2\" = \"list\" ]; then\n"
        f'  if [ "{succeed_on}" -gt 0 ] && [ "$calls" -ge "{succeed_on}" ]; then\n'
        "    echo '✓ reqogniloom  connected'\n"
        "    exit 0\n"
        "  fi\n"
        "  echo 'No MCP servers configured'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'unexpected invocation' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return bin_dir, cwd_log, call_log


def _run_verify(
    tmp_path: Path, bin_dir: Path, client: str, *, attempts: int
) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "VERIFY_RETRY_ATTEMPTS": str(attempts),
        "VERIFY_RETRY_DELAY": "0",
        "OPENCODE_BIN": "opencode",
    }
    return subprocess.run(
        ["bash", str(VERIFY), "--client", client],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_v2_retries_until_the_service_reports_the_server(tmp_path: Path) -> None:
    bin_dir, _cwd_log, call_log = _fake_opencode(tmp_path, succeed_on=3)

    result = _run_verify(tmp_path, bin_dir, "opencode-v2", attempts=5)

    assert result.returncode == 0, result.stderr
    assert len(call_log.read_text().splitlines()) == 3


def test_verify_runs_outside_the_checkout(tmp_path: Path) -> None:
    bin_dir, cwd_log, _call_log = _fake_opencode(tmp_path, succeed_on=1)

    result = _run_verify(tmp_path, bin_dir, "opencode", attempts=3)

    assert result.returncode == 0, result.stderr
    used_cwds = [Path(line) for line in cwd_log.read_text().splitlines()]
    assert used_cwds, "the fake client never ran"
    for cwd in used_cwds:
        assert REPO_ROOT not in cwd.parents and cwd != REPO_ROOT, (
            f"verify.sh ran the client inside the checkout: {cwd}"
        )


def test_verify_fails_after_exhausting_the_attempts(tmp_path: Path) -> None:
    bin_dir, _cwd_log, call_log = _fake_opencode(tmp_path, succeed_on=0)

    result = _run_verify(tmp_path, bin_dir, "opencode-v2", attempts=2)

    assert result.returncode != 0
    assert "reqogniloom" in result.stderr
    assert len(call_log.read_text().splitlines()) == 2
