import json
import subprocess
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent


def test_build_antigravity_plugin(tmp_path):
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_antigravity_plugin.py"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    plugin_json = json.loads((tmp_path / "reqogniloom" / "plugin.json").read_text())
    assert plugin_json["name"] == "reqogniloom"
    assert plugin_json["version"] == (REPO_ROOT / "VERSION").read_text().strip()

    mcp_config = json.loads(
        (tmp_path / "reqogniloom" / "mcp_config.json").read_text()
    )
    server = mcp_config["mcpServers"]["reqogniloom"]
    assert server["url"] == "${REQOGNILOOM_MCP_URL}/mcp/sse/"

    for skill_name in ["vmodell-decomposition", "test-lifecycle", "risk-derivation",
                        "ccb-approval-and-baseline", "traceability-audit",
                        "interview-management"]:
        skill = tmp_path / "reqogniloom" / "skills" / skill_name / "SKILL.md"
        assert skill.exists()
        assert skill.read_text() == (
            REPO_ROOT / "dist" / "agent-skills" / skill_name / "SKILL.md"
        ).read_text(), "Antigravity skill must be byte-identical to the canonical one"

    domain_model = tmp_path / "reqogniloom" / "DOMAIN_MODEL.md"
    assert domain_model.exists()
    assert domain_model.read_text() == (
        REPO_ROOT / "docs" / "agent-templates" / "DOMAIN_MODEL.md"
    ).read_text(), "DOMAIN_MODEL.md must be byte-identical to the canonical one"
