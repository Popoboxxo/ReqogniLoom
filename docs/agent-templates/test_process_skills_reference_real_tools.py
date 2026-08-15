"""skills-tool-refs.json is test-only metadata (never shipped) listing which
real tools each process skill documents — this test is what keeps that
sidecar honest against the manifest, the same drift guard Task 1/2 apply to
the registry itself, one layer up."""
import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = TEMPLATES_DIR / "tool-manifest.json"
REFS_PATH = TEMPLATES_DIR / "skills-tool-refs.json"

SKILL_NAMES = {
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit", "interview-management",
}


def test_skills_tool_refs_only_lists_real_tools():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    known_tools = {t["name"] for t in manifest["tools"]}
    refs = json.loads(REFS_PATH.read_text(encoding="utf-8"))

    assert set(refs.keys()) == SKILL_NAMES
    for skill_name, tools in refs.items():
        unknown = set(tools) - known_tools
        assert not unknown, f"{skill_name} references unknown tool(s): {sorted(unknown)}"


def test_every_skill_file_exists_with_valid_frontmatter():
    import yaml

    for skill_name in SKILL_NAMES:
        skill_path = TEMPLATES_DIR / "skills" / skill_name / "SKILL.md"
        assert skill_path.exists(), f"missing {skill_path}"
        raw = skill_path.read_text(encoding="utf-8")
        end = raw.index("\n---\n", 4)
        frontmatter = yaml.safe_load(raw[4:end])
        assert frontmatter["name"] == skill_name
        assert "description" in frontmatter and len(frontmatter["description"]) > 20
        assert "tools" not in frontmatter, (
            "process skills carry no tools: field — that's the whole point of "
            "separating them from RBAC-scoped agents"
        )
