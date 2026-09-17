"""Codex CLI gets config + skills only, no bespoke plugin code — same reasoning
as the OpenCode package (see build_opencode_package.py): Codex CLI has no rich
plugin-bundle concept the way Claude Code does, it just reads MCP servers out of
~/.codex/config.toml (or a trusted project's .codex/config.toml) and reads
SKILL.md files in the same Agent Skills format Claude Code, Antigravity and
OpenCode use, so this reuses dist/agent-skills/ verbatim.

Two deliberate deviations from the JSON-based packages:

1. TOML, not JSON. Codex's config is TOML and the stdlib's tomllib is read-only,
   so the snippet is hand-formatted. Values still go through json.dumps() —
   a TOML basic string and a JSON string share their escaping rules, so this
   gets quoting right without adding a tomli-w dependency for four lines.

2. Authorization: Bearer, not X-API-Key. Codex's url-based (Streamable HTTP)
   transport has no custom-header mechanism; it has bearer_token_env_var, which
   names an env var whose value Codex sends as "Authorization: Bearer <value>".
   backend/mcp_server/views.py accepts either header for a reqlo_ key, so the
   same API key works — only the transport differs. Endpoint is /mcp/ (the
   single-request/response JSON-RPC endpoint) rather than /mcp/sse/, matching
   Codex's Streamable HTTP model instead of a long-lived event stream.

The URL is a literal placeholder, not an ${ENV} template: Codex does not expand
env vars inside `url`, only the token indirection above is supported. The
snippet is meant to be pasted and edited.

Note on DOMAIN_MODEL.md: as in the OpenCode package, the copied SKILL.md files
keep their "../../DOMAIN_MODEL.md" relative link. This package is not
self-contained — its skills/ directory is meant to be relocated by the user into
their own project, where "../../" resolves against that project's structure, so
copying DOMAIN_MODEL.md here would not fix the link post-move.
"""
import argparse
import json
import shutil
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent
SKILLS_SRC = REPO_ROOT / "dist" / "agent-skills"
SERVER_NAME = "reqogniloom"
MCP_URL = "https://your-reqogniloom-host/mcp/"
API_KEY_ENV_VAR = "REQOGNILOOM_API_KEY"
SKILL_NAMES = [
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit",
    "interview-management",
]


def build(out_dir: Path, skills_src: Path = SKILLS_SRC) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "config.toml.snippet").write_text(
        "# Paste into ~/.codex/config.toml (global) or .codex/config.toml\n"
        "# (project-scoped, trusted projects only).\n"
        "# Replace the url host with your ReqogniLoom deployment and export\n"
        f"# {API_KEY_ENV_VAR}=reqlo_... before starting Codex CLI.\n"
        f"[mcp_servers.{SERVER_NAME}]\n"
        f"url = {json.dumps(MCP_URL)}\n"
        f"bearer_token_env_var = {json.dumps(API_KEY_ENV_VAR)}\n",
        encoding="utf-8",
    )

    skills_out = out_dir / "skills"
    if skills_out.exists():
        shutil.rmtree(skills_out)
    for skill_name in SKILL_NAMES:
        dst = skills_out / skill_name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skills_src / skill_name / "SKILL.md", dst / "SKILL.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    parser.add_argument("--skills-src", type=Path, default=SKILLS_SRC)
    args = parser.parse_args()
    build(args.out, skills_src=args.skills_src)
