import json
import subprocess
import sys
from pathlib import Path

from build_opencode_package import build, discover_skill_names, v2_server_entry

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent


def _run_builder(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_opencode_package.py"), *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr


def test_build_opencode_package(tmp_path):
    # --npm-out is explicit so the snippet test never writes into the repo's
    # tracked dist/npm tree (the builder's CLI default is still the real path).
    _run_builder("--out", str(tmp_path), "--npm-out", str(tmp_path / "npm"))

    snippet = json.loads((tmp_path / "opencode.json.snippet").read_text())
    server = snippet["mcp"]["reqogniloom"]
    assert server["type"] == "remote"
    assert server["url"] == "{env:REQOGNILOOM_MCP_URL}/mcp/"
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


def _package_files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_npm_package_is_generated_and_versioned(tmp_path):
    """D5.3: the Stufe-2 npm package is a real, deterministic artifact.

    Covers the four properties a publish would otherwise discover too late:
    the decided name/version (E2 + VERSION), the module/skills that ``npm pack``
    must contain, no literal credential anywhere in the tree, and byte-for-byte
    reproducibility (so a re-run never produces a spurious diff).
    """
    npm_out = tmp_path / "npm"
    _run_builder(
        "--out", str(tmp_path / "opencode"),
        "--npm-out", str(npm_out),
    )

    package_dir = npm_out / "reqogniloom-opencode"
    manifest = json.loads((package_dir / "package.json").read_text())
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert manifest["name"] == "@popoboxxo/reqogniloom-opencode"
    assert manifest["version"] == version
    assert manifest["main"] == "index.js"
    assert manifest["type"] == "module"
    assert manifest["license"] == "MIT"
    assert manifest["engines"] == {"node": ">=22.14"}
    assert manifest["repository"]["url"].endswith("github.com/Popoboxxo/ReqogniLoom.git")
    assert manifest["files"] == [
        "index.js", "skills/", "DOMAIN_MODEL.md", "README.md", "LICENSE",
    ]
    # No timestamp / build metadata of any kind: the artifact is reproducible.
    assert "time" not in manifest and "buildTime" not in manifest

    module = (package_dir / "index.js").read_text(encoding="utf-8")
    assert 'type: "remote"' in module
    # V2 (the package's target): Streamable HTTP on /mcp/ through ctx.mcp.
    # Both generations connect to Streamable HTTP on /mcp/ — V1 only falls back
    # to SSE at runtime, so no /mcp/sse/ path is baked into the module.
    assert '"{env:REQOGNILOOM_MCP_URL}/mcp/"' in module
    assert "/mcp/sse/" not in module
    assert "ctx.mcp" in module and "transform(" in module and "editor.set" in module
    assert 'headers: { "X-API-Key": API_KEY }' in module
    assert '"{env:REQOGNILOOM_API_KEY}"' in module
    assert "export default" in module
    # V1 compatibility (mcp.<name> config hook) and the named v1 plugin export.
    assert "config:" in module and "server: ReqogniLoomPlugin" in module
    # No literal key anywhere in the package (module, manifest, skills, docs).
    for name, content in _package_files(package_dir).items():
        assert b"reqlo_" not in content, f"{name} contains a literal API key"

    for skill_name in discover_skill_names(REPO_ROOT / "dist" / "agent-skills"):
        assert (package_dir / "skills" / skill_name / "SKILL.md").is_file()
    # Self-contained: ../../DOMAIN_MODEL.md from skills/<name>/SKILL.md resolves.
    assert (package_dir / "DOMAIN_MODEL.md").is_file()
    assert (package_dir / "LICENSE").is_file()

    # Determinism: a second generation into a different parent is identical.
    second = tmp_path / "npm-again"
    _run_builder(
        "--out", str(tmp_path / "opencode-again"),
        "--npm-out", str(second),
    )
    assert _package_files(package_dir) == _package_files(second / "reqogniloom-opencode")
