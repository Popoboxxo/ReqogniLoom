"""Runs the entire generator pipeline in the order docs/agent-templates/INSTALL.md
prescribes, into an isolated tmp_path, so a change to any one generator's
output shape that breaks a downstream consumer fails here instead of at the
next manual release.

Each generator's tmp_path output is also compared byte-for-byte against the
COMMITTED dist/ tree. Without this, a VERSION bump or a template edit that
was never re-run through the builders (e.g. a forgotten `python
build_claude_plugin.py`) would go unnoticed here even though the shipped
dist/ package is now stale relative to its source."""
import filecmp
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"{' '.join(cmd)} failed:\n{result.stderr}"


def assert_dirs_equal(generated: Path, committed: Path, builder_hint: str) -> None:
    """Recursively assert two directory trees are byte-identical.

    `builder_hint` is echoed in the failure message so a reader knows which
    build_*.py to re-run and commit.
    """
    comparison = filecmp.dircmp(generated, committed)
    mismatches = (
        comparison.left_only + comparison.right_only + comparison.diff_files
        + comparison.funny_files
    )
    assert not mismatches, (
        f"dist/ is stale relative to its generator: {committed} does not "
        f"match freshly generated output ({generated}). "
        f"Mismatched entries: {mismatches}. "
        f"Re-run `{builder_hint}` and commit the result."
    )
    for sub in comparison.common_dirs:
        assert_dirs_equal(generated / sub, committed / sub, builder_hint)


def test_full_pipeline_regenerates_cleanly(tmp_path):
    skills_dir = tmp_path / "agent-skills"
    run(
        [sys.executable, "docs/agent-templates/package_skills.py",
         "--out", str(skills_dir)],
        cwd=REPO_ROOT,
    )
    assert (skills_dir / "vmodell-decomposition" / "SKILL.md").exists()
    assert_dirs_equal(
        skills_dir, REPO_ROOT / "dist" / "agent-skills",
        "docs/agent-templates/package_skills.py",
    )

    # Claude Code / Antigravity / OpenCode builders read from the tmp copy of
    # agent-skills via --skills-src, making this a real pipeline test of the
    # package_skills -> builders contract rather than three independent
    # smoke checks against the already-committed dist/agent-skills/.
    claude_out = tmp_path / "claude-code"
    run(
        [sys.executable, "dist/plugins/claude-code/build_claude_plugin.py",
         "--out", str(claude_out), "--skills-src", str(skills_dir)],
        cwd=REPO_ROOT,
    )
    assert (claude_out / "reqogniloom" / ".mcp.json").exists()
    assert_dirs_equal(
        claude_out / "reqogniloom",
        REPO_ROOT / "dist" / "plugins" / "claude-code" / "reqogniloom",
        "dist/plugins/claude-code/build_claude_plugin.py",
    )
    assert (claude_out / "marketplace.json").read_text() == (
        REPO_ROOT / "dist" / "plugins" / "claude-code" / "marketplace.json"
    ).read_text(), (
        "dist/plugins/claude-code/marketplace.json is stale — re-run "
        "dist/plugins/claude-code/build_claude_plugin.py and commit the result."
    )

    antigravity_out = tmp_path / "antigravity"
    run(
        [sys.executable, "dist/plugins/antigravity/build_antigravity_plugin.py",
         "--out", str(antigravity_out), "--skills-src", str(skills_dir)],
        cwd=REPO_ROOT,
    )
    assert (antigravity_out / "reqogniloom" / "mcp_config.json").exists()
    assert_dirs_equal(
        antigravity_out / "reqogniloom",
        REPO_ROOT / "dist" / "plugins" / "antigravity" / "reqogniloom",
        "dist/plugins/antigravity/build_antigravity_plugin.py",
    )

    opencode_out = tmp_path / "opencode"
    run(
        [sys.executable, "dist/opencode/build_opencode_package.py",
         "--out", str(opencode_out), "--skills-src", str(skills_dir)],
        cwd=REPO_ROOT,
    )
    assert (opencode_out / "opencode.json.snippet").exists()
    assert_dirs_equal(
        opencode_out / "skills",
        REPO_ROOT / "dist" / "opencode" / "skills",
        "dist/opencode/build_opencode_package.py",
    )
    assert (opencode_out / "opencode.json.snippet").read_text() == (
        REPO_ROOT / "dist" / "opencode" / "opencode.json.snippet"
    ).read_text(), (
        "dist/opencode/opencode.json.snippet is stale — re-run "
        "dist/opencode/build_opencode_package.py and commit the result."
    )
