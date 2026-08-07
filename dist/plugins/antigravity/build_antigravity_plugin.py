"""Minimal Antigravity plugin: manifest + MCP config + the same SKILL.md
files Claude Code uses (Antigravity shares the Agent Skills format).
Deliberately no hooks.json / custom rules beyond this — Antigravity is a
free-quota preview with documented security findings (browser-subagent
data exfiltration, RCE), so this package stays on the low-risk static-file
surface per this plan's Global Constraints.
"""
import argparse
import json
import shutil
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent
SKILLS_SRC = REPO_ROOT / "dist" / "agent-skills"
DOMAIN_MODEL_SRC = REPO_ROOT / "docs" / "agent-templates" / "DOMAIN_MODEL.md"
SERVER_NAME = "reqogniloom"
SKILL_NAMES = [
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit",
]


def build(out_dir: Path) -> None:
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    plugin_root = out_dir / SERVER_NAME
    plugin_root.mkdir(parents=True, exist_ok=True)

    (plugin_root / "plugin.json").write_text(
        json.dumps(
            {
                "name": SERVER_NAME,
                "version": version,
                "description": (
                    "SE-domain agent skills + native MCP connection for a "
                    "ReqogniLoom requirements/architecture/test workspace."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (plugin_root / "mcp_config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    SERVER_NAME: {
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

    # SKILL.md files reference "../../DOMAIN_MODEL.md" (two levels up from
    # skills/<name>/). That must resolve to plugin_root/DOMAIN_MODEL.md.
    shutil.copy2(DOMAIN_MODEL_SRC, plugin_root / "DOMAIN_MODEL.md")

    skills_out = plugin_root / "skills"
    if skills_out.exists():
        shutil.rmtree(skills_out)
    for skill_name in SKILL_NAMES:
        src = SKILLS_SRC / skill_name
        dst = skills_out / skill_name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "SKILL.md", dst / "SKILL.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    args = parser.parse_args()
    build(args.out)
