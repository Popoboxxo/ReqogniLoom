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


def build(out_dir: Path, skills_src: Path = SKILLS_SRC) -> None:
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
    for skill_name in discover_skill_names(skills_src):
        dst = skills_out / skill_name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skills_src / skill_name / "SKILL.md", dst / "SKILL.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    parser.add_argument("--skills-src", type=Path, default=SKILLS_SRC)
    args = parser.parse_args()
    build(args.out, skills_src=args.skills_src)
