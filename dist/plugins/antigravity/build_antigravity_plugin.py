"""Minimal Antigravity plugin: manifest + MCP config + the same SKILL.md
files Claude Code uses (Antigravity shares the Agent Skills format), plus the
stage-B listen-mode hook (`PreInvocation`, see docs/clients/listen-mode-contract.md).
The listen relay is opt-in at runtime via the shared local switch; the hook
itself only queues and detaches, so it never blocks a model call.
"""
import argparse
import json
import shutil
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent
SKILLS_SRC = REPO_ROOT / "dist" / "agent-skills"
DOMAIN_MODEL_SRC = REPO_ROOT / "docs" / "agent-templates" / "DOMAIN_MODEL.md"
LISTEN_SRC = BUILD_DIR / "listen.py"
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


def _listen_readme() -> str:
    return """\
# Listen mode (Antigravity) — stage B

`hooks.json` registers a `PreInvocation` hook that runs `python3 listen.py`.
Antigravity has no submit event, so this fires before **every** model call and
carries `lastUserInput`; the relay deduplicates on `(session_id, sha256(text))`
in `~/.reqogniloom/listen/capture-seen.json` before it queues a message.

* Default **off**. Switch: `python3 listen.py on <workspace_id>` / `off` /
  `status`, or the equivalent commands of the other clients — the state
  directory `~/.reqogniloom/listen` is shared.
* Both switches must be on: the local `listen.json` and the server-side
  workspace preference `capture.enabled`.
* The hook only queues and detaches; delivery happens in `listen.py --drain`
  and uses `POST /api/v1/suggestions/capture/` with
  `REQOGNILOOM_MCP_URL` (or `REQOGNILOOM_BASE_URL`) and `REQOGNILOOM_API_KEY`.
* Fail-open: no stdout, no non-zero exit, diagnostics without message text in
  `capture.log`.

Status of this adapter: **partial**. The hook schema (`PreInvocation`,
`lastUserInput`, script cwd) follows the documented preview shape but was not
executed against a live Antigravity installation; the conformance suite checks
the relay against an HTTP stub. See `docs/clients/listen-mode-contract.md`.
"""


def build(out_dir: Path, skills_src: Path = SKILLS_SRC) -> None:
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

    # Listen mode, stage B: Antigravity has no submit event, so `PreInvocation`
    # (which fires before every model call, with `lastUserInput`) is the only
    # deterministic catch point. The relay deduplicates on (session, hash).
    shutil.copy2(LISTEN_SRC, plugin_root / "listen.py")
    (plugin_root / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreInvocation": [
                        {
                            "type": "command",
                            "command": "python3 listen.py",
                            "timeout_seconds": 5,
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_root / "LISTEN.md").write_text(_listen_readme(), encoding="utf-8")

    skills_out = plugin_root / "skills"
    if skills_out.exists():
        shutil.rmtree(skills_out)
    for skill_name in discover_skill_names(skills_src):
        src = skills_src / skill_name
        dst = skills_out / skill_name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "SKILL.md", dst / "SKILL.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    parser.add_argument("--skills-src", type=Path, default=SKILLS_SRC)
    args = parser.parse_args()
    build(args.out, skills_src=args.skills_src)
