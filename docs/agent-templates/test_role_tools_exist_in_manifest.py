"""Every tool referenced in a shipped role's frontmatter must be a real,
current MCP tool, and each thinned role must point at the process skill
that documents how to use those tools."""
import json
from pathlib import Path

import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = TEMPLATES_DIR / "tool-manifest.json"

EXPECTED_TOOLS_BY_ROLE = {
    "requirements-architect": {
        "needs.read", "needs.create", "needs.update", "needs.get_traces",
        "needs.derive_requirements", "requirement.get", "requirement.query",
        "requirement.create", "requirement.update", "requirement.decompose",
        "requirement.validate", "requirement.derive", "requirement.check_consistency",
        "ai_derivation.derive_requirements_from_need",
        "ai_derivation.decompose_requirement_next_level",
        "ai_derivation.suggest_architecture_for_requirement",
        "traceability.query", "traceability.suggest_links", "traceability.create_link",
        "artifact.search", "artifact.get_tree", "workspace.get_context", "glossary.read",
        "prompt_template.get", "prompt_template.list", "custom_field.get", "custom_field.query",
        "goal.read", "goal.query", "main_goal.read",
    },
    "test-engineer": {
        "test.get", "test.query", "test.create", "test.update", "test.link",
        "test.run_create", "test.run_get", "test.run_report_results",
        "test.derive_from_requirement", "requirement.get", "requirement.query",
        "traceability.query", "artifact.search", "workspace.get_context",
        "custom_field.get", "custom_field.query",
    },
    "risk-analyst": {
        "risk.read", "risk.create", "risk.update", "risk.delete",
        "architecture.get", "architecture.query", "diagram.get", "diagram.query",
        "requirement.get", "requirement.query", "traceability.query",
        "traceability.create_link", "artifact.search", "workspace.get_context",
        "ai_derivation.derive_risks_from_architecture", "custom_field.get", "custom_field.query",
    },
    "change-manager": {
        "adr.read", "adr.create", "adr.update", "adr.delete", "adr.outdate", "adr.reactivate",
        "issue.read", "issue.create", "issue.update", "issue.delete", "issue.outdate",
        "issue.reactivate",
        "change_request.read", "change_request.create", "change_request.update",
        "change_request.outdate", "change_request.reactivate", "change_request.query",
        "review.list_pending", "review.approve", "review.reject", "review.request_changes",
        "baseline.create", "baseline.list", "baseline.get", "baseline.compare",
        "diagram.create", "diagram.get", "diagram.update", "diagram.query",
        "diagram.outdate", "diagram.reactivate",
        "requirement.update", "architecture.update", "traceability.query",
        "traceability.suggest_links", "traceability.create_link", "artifact.search",
        "workspace.get_context",
    },
    "quality-auditor": {
        "requirement.get", "requirement.query", "architecture.get", "architecture.query",
        "diagram.get", "diagram.query", "test.get", "test.query", "traceability.query",
        "artifact.search", "artifact.get_tree", "workspace.get_context", "glossary.read",
        "adr.read", "risk.read", "issue.read", "goal.read", "goal.query", "main_goal.read",
        "baseline.list", "baseline.get", "baseline.compare", "change_request.read",
        "change_request.query", "review.list_pending", "custom_field.get", "custom_field.query",
    },
}

ROLE_TO_SKILL = {
    "requirements-architect": "vmodell-decomposition",
    "test-engineer": "test-lifecycle",
    "risk-analyst": "risk-derivation",
    "change-manager": "ccb-approval-and-baseline",
    "quality-auditor": "traceability-audit",
}


def _parse_frontmatter(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    end = raw.index("\n---\n", 4)
    return yaml.safe_load(raw[4:end])


def test_every_role_tool_exists_in_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    known_tools = {t["name"] for t in manifest["tools"]}

    for role_name, expected in EXPECTED_TOOLS_BY_ROLE.items():
        frontmatter = _parse_frontmatter(TEMPLATES_DIR / f"{role_name}.md")
        role_tools = set(frontmatter["tools"])
        unknown = role_tools - known_tools
        assert not unknown, f"{role_name}.md references unknown tool(s): {sorted(unknown)}"
        assert role_tools == expected, (
            f"{role_name}.md tools drifted from spec: "
            f"missing={sorted(expected - role_tools)} extra={sorted(role_tools - expected)}"
        )


def test_quality_auditor_stays_strictly_read_only():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    is_write = {t["name"]: t["is_write"] for t in manifest["tools"]}
    frontmatter = _parse_frontmatter(TEMPLATES_DIR / "quality-auditor.md")
    write_tools = [t for t in frontmatter["tools"] if is_write.get(t)]
    assert not write_tools, f"quality-auditor must stay read-only, found write tool(s): {write_tools}"


def test_every_role_points_at_its_process_skill():
    for role_name, skill_name in ROLE_TO_SKILL.items():
        frontmatter = _parse_frontmatter(TEMPLATES_DIR / f"{role_name}.md")
        assert frontmatter.get("process_skill") == skill_name, (
            f"{role_name}.md should declare process_skill: {skill_name}"
        )
        skill_path = TEMPLATES_DIR / "skills" / skill_name / "SKILL.md"
        assert skill_path.exists(), f"{role_name}.md points at missing skill {skill_path}"


def test_no_tool_appears_in_a_role_without_appearing_in_its_skill_refs():
    """A tool in a role's whitelist with no explanation anywhere in its
    process skill is drift by another name — see this plan's Global
    Constraints."""
    refs = json.loads((TEMPLATES_DIR / "skills-tool-refs.json").read_text(encoding="utf-8"))
    for role_name, skill_name in ROLE_TO_SKILL.items():
        frontmatter = _parse_frontmatter(TEMPLATES_DIR / f"{role_name}.md")
        role_tools = set(frontmatter["tools"])
        documented = set(refs[skill_name])
        undocumented = role_tools - documented
        assert not undocumented, (
            f"{role_name}.md whitelists tool(s) not documented in "
            f"skills/{skill_name}/SKILL.md: {sorted(undocumented)}"
        )
