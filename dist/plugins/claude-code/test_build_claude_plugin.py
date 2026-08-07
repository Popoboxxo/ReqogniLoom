import json
import subprocess
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent


def test_build_claude_plugin_produces_valid_manifests(tmp_path):
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_claude_plugin.py"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    plugin_json = json.loads(
        (tmp_path / "reqogniloom" / ".claude-plugin" / "plugin.json").read_text()
    )
    assert plugin_json["name"] == "reqogniloom"
    assert plugin_json["version"] == (REPO_ROOT / "VERSION").read_text().strip()

    mcp_json = json.loads(
        (tmp_path / "reqogniloom" / ".mcp.json").read_text()
    )
    server = mcp_json["mcpServers"]["reqogniloom"]
    assert server["type"] == "sse"
    assert server["url"] == "${REQOGNILOOM_MCP_URL}/mcp/sse/"
    assert server["headers"]["X-API-Key"] == "${REQOGNILOOM_API_KEY}"
    assert "reqlo_" not in json.dumps(mcp_json)  # no real key leaked into template

    architect_md = (
        tmp_path / "reqogniloom" / "agents" / "requirements-architect.md"
    ).read_text()
    assert "mcp__reqogniloom__requirement.create" in architect_md
    assert "mcp__reqogniloom__goal.read" in architect_md  # Task 3 addition survives packaging

    change_manager_md = (
        tmp_path / "reqogniloom" / "agents" / "change-manager.md"
    ).read_text()
    assert "mcp__reqogniloom__change_request.create" in change_manager_md
    assert "mcp__reqogniloom__review.approve" in change_manager_md

    marketplace = json.loads((tmp_path / "marketplace.json").read_text())
    assert marketplace["plugins"][0]["name"] == "reqogniloom"
    assert marketplace["plugins"][0]["source"] == "./reqogniloom"

    skill = (
        tmp_path / "reqogniloom" / "skills" / "ccb-approval-and-baseline" / "SKILL.md"
    ).read_text()
    assert skill == (
        REPO_ROOT / "dist" / "agent-skills" / "ccb-approval-and-baseline" / "SKILL.md"
    ).read_text(), "process skill must be byte-identical to Task 4's staged copy"
    assert "tools:" not in skill.split("---", 2)[1]  # skills stay unrestricted

    # DOMAIN_MODEL.md must ship at the plugin root, byte-identical to source,
    # so the 10 relative links from agents/<role>.md (../DOMAIN_MODEL.md) and
    # skills/<name>/SKILL.md (../../DOMAIN_MODEL.md) both resolve.
    domain_model = tmp_path / "reqogniloom" / "DOMAIN_MODEL.md"
    assert domain_model.read_text() == (
        REPO_ROOT / "docs" / "agent-templates" / "DOMAIN_MODEL.md"
    ).read_text()
    assert "](../DOMAIN_MODEL.md)" in architect_md
    assert "](../../DOMAIN_MODEL.md)" in skill


def test_build_claude_plugin_all_json_files_parse(tmp_path):
    subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_claude_plugin.py"),
         "--out", str(tmp_path)],
        cwd=REPO_ROOT, check=True,
    )
    for json_file in tmp_path.rglob("*.json"):
        json.loads(json_file.read_text(encoding="utf-8"))  # raises on invalid JSON
