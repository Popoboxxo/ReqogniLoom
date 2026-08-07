"""Render the canonical role templates + tool manifest into a Claude Code
plugin: .claude-plugin/plugin.json, .mcp.json (SSE, env-templated, never a
literal key), agents/<role>.md (Claude Code subagent format with MCP tool
names rewritten to mcp__<server>__<tool>) — the tool-restricted RBAC
identities from Task 3 — plus skills/<name>/SKILL.md (the unrestricted
process skills from Task 4, copied verbatim), and a marketplace.json so
`claude plugin install` / `/plugin` discovery works without manual
`claude mcp add` steps — this is what removes the 4 onboarding
misconfigurations the 2026-08-05 research found the team hit on OpenCode
(wrong port, missing env var, key inside the {env:} template, wrong header
name): the whole connection travels inside the plugin bundle instead of
being hand-typed per install.
"""
import argparse
import json
import shutil
from pathlib import Path

import yaml

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent
TEMPLATES_DIR = REPO_ROOT / "docs" / "agent-templates"
SKILLS_SRC = REPO_ROOT / "dist" / "agent-skills"
SERVER_NAME = "reqogniloom"

ROLE_FILES = [
    "requirements-architect.md",
    "test-engineer.md",
    "risk-analyst.md",
    "change-manager.md",
    "quality-auditor.md",
]
SKILL_NAMES = [
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit",
]


def parse_role_file(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    end = raw.index("\n---\n", 4)
    return yaml.safe_load(raw[4:end]), raw[end + 5:]


def build(out_dir: Path) -> None:
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    plugin_root = out_dir / SERVER_NAME
    plugin_meta_dir = plugin_root / ".claude-plugin"
    agents_dir = plugin_root / "agents"
    plugin_meta_dir.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    (plugin_meta_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": SERVER_NAME,
                "version": version,
                "description": (
                    "SE-domain agent roles + native MCP connection for a "
                    "ReqogniLoom requirements/architecture/test workspace."
                ),
                "author": {"name": "ReqogniLoom"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (plugin_root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    SERVER_NAME: {
                        "type": "sse",
                        "url": "${REQOGNILOOM_MCP_URL}/mcp/sse/",
                        "headers": {"X-API-Key": "${REQOGNILOOM_API_KEY}"},
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for role_file in ROLE_FILES:
        frontmatter, body = parse_role_file(TEMPLATES_DIR / role_file)
        prefixed_tools = [
            f"mcp__{SERVER_NAME}__{t}" for t in frontmatter.get("tools", [])
        ]
        agent_frontmatter = yaml.safe_dump(
            {
                "name": frontmatter["name"],
                "description": frontmatter["description"],
                "tools": prefixed_tools,
            },
            sort_keys=False,
        )
        (agents_dir / role_file).write_text(
            f"---\n{agent_frontmatter}---\n{body}", encoding="utf-8"
        )

    skills_dir = plugin_root / "skills"
    if skills_dir.exists():
        shutil.rmtree(skills_dir)
    for skill_name in SKILL_NAMES:
        dst = skills_dir / skill_name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SKILLS_SRC / skill_name / "SKILL.md", dst / "SKILL.md")

    (out_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": f"{SERVER_NAME}-marketplace",
                "owner": {"name": "ReqogniLoom"},
                "plugins": [
                    {
                        "name": SERVER_NAME,
                        "source": f"./{SERVER_NAME}",
                        "description": "ReqogniLoom SE agent roles + MCP connection",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    args = parser.parse_args()
    build(args.out)
