import json
import subprocess
import sys
from pathlib import Path

from build_claude_plugin import discover_skill_names

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
    assert server["url"] == "${user_config.mcp_url}/mcp/sse/"
    assert server["headers"]["X-API-Key"] == "${user_config.api_key}"
    assert "reqlo_" not in json.dumps(mcp_json)  # no real key leaked into template

    architect_md = (
        tmp_path / "reqogniloom" / "agents" / "requirements-architecture-manager.md"
    ).read_text()
    assert "mcp__reqogniloom__requirement.create" in architect_md
    assert "mcp__reqogniloom__goal.read" in architect_md  # Task 3 addition survives packaging

    change_manager_md = (
        tmp_path / "reqogniloom" / "agents" / "change-manager.md"
    ).read_text()
    assert "mcp__reqogniloom__change_request.create" in change_manager_md
    assert "mcp__reqogniloom__review.approve" in change_manager_md

    # marketplace.json must live under .claude-plugin/ at the marketplace
    # root so `claude plugin marketplace add <out_dir>` finds it.
    assert not (tmp_path / "marketplace.json").exists(), (
        "marketplace.json must not be written directly into out_dir root"
    )
    marketplace = json.loads(
        (tmp_path / ".claude-plugin" / "marketplace.json").read_text()
    )
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
    assert "](../skills/vmodell-decomposition/SKILL.md)" in architect_md


def test_plugin_declares_user_config_and_mcp_uses_it(tmp_path):
    """`.mcp.json` must not depend on ambient environment variables.

    Claude Code expands `${user_config.<key>}` in a plugin's `.mcp.json` from
    the `userConfig` block in `.claude-plugin/plugin.json`, so the two files
    are one contract: every reference needs a declared key, and both required
    keys need to be prompt-visible (`title`/`description`) — an unset key
    silently yields an unusable MCP url or an empty API key.
    """
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_claude_plugin.py"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    plugin = json.loads(
        (tmp_path / "reqogniloom" / ".claude-plugin" / "plugin.json").read_text()
    )
    user_config = plugin["userConfig"]
    assert set(user_config) == {"mcp_url", "api_key"}
    assert user_config["mcp_url"] == {
        "type": "string",
        "title": "ReqogniLoom URL",
        "description": "Base URL, e.g. https://reqlo.example.com",
        "required": True,
    }
    assert user_config["api_key"]["type"] == "string"
    assert user_config["api_key"]["title"] == "API key"
    assert user_config["api_key"]["sensitive"] is True
    assert user_config["api_key"]["required"] is True

    server = json.loads(
        (tmp_path / "reqogniloom" / ".mcp.json").read_text()
    )["mcpServers"]["reqogniloom"]
    assert server["url"] == "${user_config.mcp_url}/mcp/sse/"
    assert "mcp_url" in server["url"]
    assert server["headers"]["X-API-Key"] == "${user_config.api_key}"

    # No ambient-env fallback and no literal credential in either manifest.
    rendered = json.dumps(plugin) + json.dumps(server)
    assert "REQOGNILOOM_" not in rendered
    assert "reqlo_" not in rendered


def test_build_claude_plugin_all_json_files_parse(tmp_path):
    subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_claude_plugin.py"),
         "--out", str(tmp_path)],
        cwd=REPO_ROOT, check=True,
    )
    for json_file in tmp_path.rglob("*.json"):
        json.loads(json_file.read_text(encoding="utf-8"))  # raises on invalid JSON


def test_discover_skill_names_matches_the_canonical_skill_set():
    """The skill set is derived from dist/agent-skills/ rather than written
    out as a literal, so a new skill added by
    docs/agent-templates/package_skills.py cannot land in this package while
    the other three silently ship without it. Pinning the derived set keeps
    that derivation honest."""
    assert discover_skill_names(REPO_ROOT / "dist" / "agent-skills") == [
        "ccb-approval-and-baseline", "interview-management", "risk-derivation",
        "test-lifecycle", "traceability-audit", "vmodell-decomposition",
    ]

