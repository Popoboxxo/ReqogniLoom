import json
import subprocess
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent


def test_build_opencode_package(tmp_path):
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_opencode_package.py"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    snippet = json.loads((tmp_path / "opencode.json.snippet").read_text())
    server = snippet["mcp"]["reqogniloom"]
    assert server["type"] == "remote"
    assert server["url"] == "{env:REQOGNILOOM_MCP_URL}/mcp/sse/"
    assert server["headers"]["X-API-Key"] == "{env:REQOGNILOOM_API_KEY}"
    # Regression guard for the exact misconfiguration the 2026-08-05
    # research found the team hit: key placed INSIDE the {env:...} template
    # instead of the template referencing an external env var.
    assert "{env:reqlo_" not in json.dumps(snippet)

    for skill_name in ["vmodell-decomposition", "test-lifecycle", "risk-derivation",
                        "ccb-approval-and-baseline", "traceability-audit",
                        "interview-management"]:
        assert (tmp_path / "skills" / skill_name / "SKILL.md").exists()
