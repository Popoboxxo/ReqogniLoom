"""OpenCode gets config + skills only, no bespoke plugin code — see this
plan's Global Constraints for why (OpenCode's plugin API is
experimental-flagged and churning fast). OpenCode reads .opencode/skills/
in the same SKILL.md format Claude Code and Antigravity use, so this reuses
Task 4's output verbatim rather than regenerating it.

Note on DOMAIN_MODEL.md: the copied SKILL.md files still contain a
"../../DOMAIN_MODEL.md" relative link. Unlike the Claude Code / Antigravity
plugin bundles, this package is not self-contained — its skills/ directory
is explicitly meant to be relocated by the user into their OWN project's
.opencode/skills/ (see Interfaces note). Once moved there, "../../" resolves
relative to that project's structure, not to anything this build script
controls, so copying a DOMAIN_MODEL.md here would not fix the link post-move
and would just add a stale, orphaned file to this package. Left as-is
intentionally; see task-8-report.md for the full reasoning.
"""
import argparse
import json
import shutil
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent
SKILLS_SRC = REPO_ROOT / "dist" / "agent-skills"
SERVER_NAME = "reqogniloom"
SKILL_NAMES = [
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit",
]


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "opencode.json.snippet").write_text(
        json.dumps(
            {
                "mcp": {
                    SERVER_NAME: {
                        "type": "remote",
                        "url": "{env:REQOGNILOOM_MCP_URL}/mcp/sse/",
                        "headers": {"X-API-Key": "{env:REQOGNILOOM_API_KEY}"},
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    skills_out = out_dir / "skills"
    if skills_out.exists():
        shutil.rmtree(skills_out)
    for skill_name in SKILL_NAMES:
        dst = skills_out / skill_name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SKILLS_SRC / skill_name / "SKILL.md", dst / "SKILL.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    args = parser.parse_args()
    build(args.out)
