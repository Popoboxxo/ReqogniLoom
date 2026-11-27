"""Render the canonical role templates + tool manifest into a Claude Code
plugin: .claude-plugin/plugin.json (including the ``userConfig`` prompts the
installer/`claude plugin configure` fills in), .mcp.json (Streamable HTTP,
interpolated from ``userConfig``, never a literal key), agents/<role>.md (Claude Code
subagent format with MCP tool
names rewritten to mcp__plugin_<plugin>_<server>__<tool_underscored>) — the tool-restricted RBAC
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
import sys
from pathlib import Path

import yaml

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent
# Standalone script (no package __init__.py) and also loaded by path from the
# repo root by dist/test_mcp_convention_parity.py: make the shared helper
# importable from either entry point.
DIST_DIR = REPO_ROOT / "dist"
if str(DIST_DIR) not in sys.path:
    sys.path.insert(0, str(DIST_DIR))
from mcp_url import mcp_endpoint_url  # noqa: E402

TEMPLATES_DIR = REPO_ROOT / "docs" / "agent-templates"
# Plugin-specific sources (hooks, relay scripts, commands). They are code, not
# role templates, so they live next to their generator rather than being
# rendered from the tool manifest.
PLUGIN_SOURCE_DIR = TEMPLATES_DIR / "claude-plugin"
# Copied recursively into the plugin root, in this order. Every target is
# removed first so a file deleted at the source cannot linger in dist/.
PLUGIN_SOURCE_DIRS = ("hooks", "scripts", "commands")
SKILLS_SRC = REPO_ROOT / "dist" / "agent-skills"
SERVER_NAME = "reqogniloom"

ROLE_FILES = [
    "requirements-architecture-manager.md",
    "test-engineer.md",
    "risk-analyst.md",
    "change-manager.md",
    "quality-auditor.md",
    "document-steward.md",
    "reqogniloom-support.md",
]


def discover_skill_names(skills_src: Path) -> list[str]:
    """Every immediate subdirectory of skills_src that holds a SKILL.md.

    Derived rather than hardcoded: docs/agent-templates/package_skills.py owns
    the skill set, and a literal list in one builder could be updated while the
    other three silently shipped without the new skill. Sorted so repeated
    generation stays byte-for-byte deterministic.
    """
    return sorted(
        entry.name
        for entry in skills_src.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    )


def parse_role_file(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    end = raw.index("\n---\n", 4)
    return yaml.safe_load(raw[4:end]), raw[end + 5:]


def build(out_dir: Path, skills_src: Path = SKILLS_SRC) -> None:
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
                # Required installer prompts (Claude Code `userConfig`); the
                # .mcp.json interpolates them as ${user_config.<key>}. The key
                # description deliberately avoids the literal prefix spelling
                # so no plugin artifact reads like a credential.
                "userConfig": {
                    "mcp_url": {
                        "type": "string",
                        "title": "ReqogniLoom URL",
                        "description": (
                            "Base URL, no path; do not end in /mcp "
                            "(e.g. https://reqlo.example.com)"
                        ),
                        "required": True,
                    },
                    "api_key": {
                        "type": "string",
                        "title": "API key",
                        "description": (
                            "ReqogniLoom API key created in your workspace "
                            "settings. Tools that publish proposals (e.g. "
                            "traceability.suggest_links) need an "
                            "agent-principal key with write scope; a plain "
                            "user key is refused for those calls."
                        ),
                        "sensitive": True,
                        "required": True,
                    },
                    # Listen mode (ambient capture) is opt-in and off by
                    # default. The relay needs the target workspace explicitly;
                    # it is optional here so an installation that never enables
                    # listen mode is not blocked at configure time.
                    "workspace_id": {
                        "type": "string",
                        "title": "Workspace ID",
                        "description": (
                            "UUID of the workspace that listen-mode capture "
                            "sends to. Required to enable listen mode; leave "
                            "empty otherwise."
                        ),
                        "required": False,
                    },
                },
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
                        "type": "http",
                        "url": mcp_endpoint_url("${user_config.mcp_url}"),
                        "headers": {"X-API-Key": "${user_config.api_key}"},
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # DOMAIN_MODEL.md lives at the plugin root so skills/<name>/SKILL.md's
    # ../../DOMAIN_MODEL.md links (two levels up from skills/<name>/) resolve.
    # The role files' source location (docs/agent-templates/<role>.md) has
    # DOMAIN_MODEL.md as a direct sibling, so their bare `DOMAIN_MODEL.md`
    # links must be rewritten to `../DOMAIN_MODEL.md` once the body is
    # relocated one level deeper into agents/<role>.md.
    shutil.copy2(
        TEMPLATES_DIR / "DOMAIN_MODEL.md", plugin_root / "DOMAIN_MODEL.md"
    )

    for role_file in ROLE_FILES:
        frontmatter, body = parse_role_file(TEMPLATES_DIR / role_file)
        # Claude Code exposes an MCP tool from a plugin as
        # ``mcp__plugin_<plugin>_<server>__<tool>`` with every ``.`` in the tool
        # name replaced by ``_`` (issue #1974). The old ``mcp__<server>__<dotted>``
        # form matched nothing, so all 155 role refs were dead.
        prefixed_tools = [
            f"mcp__plugin_{SERVER_NAME}_{SERVER_NAME}__{t.replace('.', '_')}"
            for t in frontmatter.get("tools", [])
        ]
        agent_frontmatter = yaml.safe_dump(
            {
                "name": frontmatter["name"],
                "description": frontmatter["description"],
                "tools": prefixed_tools,
            },
            sort_keys=False,
        )
        body = body.replace("(DOMAIN_MODEL.md)", "(../DOMAIN_MODEL.md)")
        body = body.replace("](skills/", "](../skills/")
        (agents_dir / role_file).write_text(
            f"---\n{agent_frontmatter}---\n{body}", encoding="utf-8"
        )

    skills_dir = plugin_root / "skills"
    if skills_dir.exists():
        shutil.rmtree(skills_dir)
    for skill_name in discover_skill_names(skills_src):
        dst = skills_dir / skill_name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skills_src / skill_name / "SKILL.md", dst / "SKILL.md")

    # Claude Code plugin hooks + their local relay scripts + slash commands.
    # Source of truth is docs/agent-templates/claude-plugin/; the generator
    # never renders these, so a source edit must reach dist/ through a rebuild.
    for source_name in PLUGIN_SOURCE_DIRS:
        src = PLUGIN_SOURCE_DIR / source_name
        dst = plugin_root / source_name
        if dst.exists():
            shutil.rmtree(dst)
        if src.is_dir():
            shutil.copytree(src, dst)

    # marketplace.json must live in .claude-plugin/ at the marketplace root
    # (out_dir), not directly in out_dir, because `claude plugin marketplace
    # add <out_dir>` looks for it at <out_dir>/.claude-plugin/marketplace.json
    # (see docs/agent-templates/INSTALL.md).
    marketplace_meta_dir = out_dir / ".claude-plugin"
    marketplace_meta_dir.mkdir(parents=True, exist_ok=True)
    (marketplace_meta_dir / "marketplace.json").write_text(
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
    parser.add_argument("--skills-src", type=Path, default=SKILLS_SRC)
    args = parser.parse_args()
    build(args.out, skills_src=args.skills_src)
