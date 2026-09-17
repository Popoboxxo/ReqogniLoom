import subprocess
import sys
import tomllib
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent


def test_build_codex_package(tmp_path):
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_codex_package.py"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    raw = (tmp_path / "config.toml.snippet").read_text(encoding="utf-8")
    # Hand-formatted TOML (stdlib tomllib is read-only), so parse it back.
    snippet = tomllib.loads(raw)
    server = snippet["mcp_servers"]["reqogniloom"]
    assert server["url"] == "https://your-reqogniloom-host/mcp/"
    # Codex's url transport has no custom-header mechanism — auth goes through
    # bearer_token_env_var, which must name an env var, never carry the key.
    assert server["bearer_token_env_var"] == "REQOGNILOOM_API_KEY"
    assert "headers" not in server
    assert "reqlo_" not in server["bearer_token_env_var"]

    for skill_name in ["vmodell-decomposition", "test-lifecycle", "risk-derivation",
                        "ccb-approval-and-baseline", "traceability-audit",
                        "interview-management"]:
        assert (tmp_path / "skills" / skill_name / "SKILL.md").exists()
