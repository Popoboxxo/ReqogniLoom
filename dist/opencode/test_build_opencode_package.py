import json
import subprocess
import sys
from pathlib import Path

from build_opencode_package import build, discover_skill_names, v2_server_entry

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent


def test_build_opencode_package(tmp_path):
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_opencode_package.py"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr

    snippet = json.loads((tmp_path / "opencode.json.snippet").read_text())
    server = snippet["mcp"]["reqogniloom"]
    assert server["type"] == "remote"
    assert server["url"] == "{env:REQOGNILOOM_MCP_URL}/mcp/sse/"
    assert server["headers"]["X-API-Key"] == "{env:REQOGNILOOM_API_KEY}"
    # Regression guard for the exact misconfiguration the 2026-08-05
    # research found the team hit: key placed INSIDE the {env:...} template
    # instead of the template referencing an external env var.
    assert "{env:reqlo_" not in json.dumps(snippet)

    for skill_name in ["vmodell-decomposition", "test-lifecycle", "risk-derivation",
                        "ccb-approval-and-baseline", "traceability-audit",
                        "interview-management"]:
        assert (tmp_path / "skills" / skill_name / "SKILL.md").exists()


def test_v2_snippet_shape(tmp_path):
    """OpenCode V2 reads ``mcp.servers.<name>`` with Streamable HTTP on /mcp/.
    Pinned as an exact dict so a stray key (or a silently added one) fails
    here rather than in a user's client."""
    build(tmp_path)

    snippet = json.loads((tmp_path / "opencode.v2.json.snippet").read_text())
    assert snippet["mcp"]["servers"]["reqogniloom"] == {
        "type": "remote",
        "url": "{env:REQOGNILOOM_MCP_URL}/mcp/",
        "headers": {"X-API-Key": "{env:REQOGNILOOM_API_KEY}"},
        "oauth": False,
        "codemode": False,
    }
    # Same regression guard as the V1 snippet: the key name lives in the
    # {env:...} template, never a literal key in the config.
    assert "reqlo_" not in json.dumps(snippet)


def test_v2_entry_uses_literal_url_and_env_key():
    """``url`` is the base without a path (literal or an env placeholder); the
    /mcp/ suffix and the header shell are added here, so callers cannot
    assemble them inconsistently."""
    entry = v2_server_entry("http://h:8001", "MY_KEY")

    assert entry["url"] == "http://h:8001/mcp/"
    assert entry["headers"] == {"X-API-Key": "{env:MY_KEY}"}
    assert entry["oauth"] is False
    assert entry["codemode"] is False


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

