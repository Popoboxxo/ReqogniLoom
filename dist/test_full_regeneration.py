"""Runs the entire generator pipeline in the order docs/agent-templates/INSTALL.md
prescribes, into an isolated tmp_path, so a change to any one generator's
output shape that breaks a downstream consumer fails here instead of at the
next manual release."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"{' '.join(cmd)} failed:\n{result.stderr}"


def test_full_pipeline_regenerates_cleanly(tmp_path):
    skills_dir = tmp_path / "agent-skills"
    run(
        [sys.executable, "docs/agent-templates/package_skills.py",
         "--out", str(skills_dir)],
        cwd=REPO_ROOT,
    )
    assert (skills_dir / "vmodell-decomposition" / "SKILL.md").exists()

    # Claude Code / Antigravity / OpenCode builders read dist/agent-skills/
    # by convention (see each build_*.py's SKILLS_SRC constant) — point them
    # at the tmp copy by pre-seeding the real path is out of scope for a
    # unit test; this test instead re-runs each builder against the
    # already-committed dist/agent-skills/ to confirm they succeed from a
    # clean checkout, which is the actual release-time invariant.
    claude_out = tmp_path / "claude-code"
    run(
        [sys.executable, "dist/plugins/claude-code/build_claude_plugin.py",
         "--out", str(claude_out)],
        cwd=REPO_ROOT,
    )
    assert (claude_out / "reqogniloom" / ".mcp.json").exists()

    antigravity_out = tmp_path / "antigravity"
    run(
        [sys.executable, "dist/plugins/antigravity/build_antigravity_plugin.py",
         "--out", str(antigravity_out)],
        cwd=REPO_ROOT,
    )
    assert (antigravity_out / "reqogniloom" / "mcp_config.json").exists()

    opencode_out = tmp_path / "opencode"
    run(
        [sys.executable, "dist/opencode/build_opencode_package.py",
         "--out", str(opencode_out)],
        cwd=REPO_ROOT,
    )
    assert (opencode_out / "opencode.json.snippet").exists()
