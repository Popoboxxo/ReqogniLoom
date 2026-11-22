"""Regression guard for #1964.

Two independent contracts live here:

1. Drift: every canonical process-skill text and DOMAIN_MODEL.md must stay
   byte-identical to every generated distribution copy. A skill edit that was
   never propagated to dist/ used to be invisible until the next manual
   release; the full-regeneration test catches that indirectly, this one
   catches it directly and cheaply.
2. The bug itself: `workspace.get_context` only reports the active preset when
   a concrete `workspace_id` is passed. Every skill workflow step that calls it
   must pass the id, and every shipped agent must state the prerequisite for
   obtaining one via a role that actually has `workspace.list`.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = REPO_ROOT / "docs" / "agent-templates"

SKILL_NAMES = {
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit", "interview-management",
    "document-projection", "reqogniloom-support",
}

DIST_SKILL_ROOTS = (
    "dist/agent-skills",
    "dist/codex/skills",
    "dist/npm/reqogniloom-opencode/skills",
    "dist/opencode/skills",
    "dist/plugins/antigravity/reqogniloom/skills",
    "dist/plugins/claude-code/reqogniloom/skills",
)

DIST_DOMAIN_MODEL_COPIES = (
    "dist/npm/reqogniloom-opencode/DOMAIN_MODEL.md",
    "dist/plugins/antigravity/reqogniloom/DOMAIN_MODEL.md",
    "dist/plugins/claude-code/reqogniloom/DOMAIN_MODEL.md",
)

AGENT_FILES = (
    "change-manager", "quality-auditor", "requirements-architecture-manager",
    "risk-analyst", "test-engineer", "document-steward", "reqogniloom-support",
)


def test_canonical_skills_match_every_distribution_copy():
    for skill in SKILL_NAMES:
        canonical = (TEMPLATES_DIR / "skills" / skill / "SKILL.md").read_bytes()
        for root in DIST_SKILL_ROOTS:
            copy = REPO_ROOT / root / skill / "SKILL.md"
            assert copy.is_file(), f"missing distribution copy: {copy}"
            assert copy.read_bytes() == canonical, (
                f"{copy} drifted from canonical skills/{skill}/SKILL.md; "
                "propagate the canonical text to all dist/ skill copies"
            )


def test_canonical_domain_model_matches_every_distribution_copy():
    canonical = (TEMPLATES_DIR / "DOMAIN_MODEL.md").read_bytes()
    for rel in DIST_DOMAIN_MODEL_COPIES:
        copy = REPO_ROOT / rel
        assert copy.is_file(), f"missing distribution copy: {copy}"
        assert copy.read_bytes() == canonical, (
            f"{copy} drifted from canonical DOMAIN_MODEL.md"
        )


def test_skill_workflow_steps_pass_workspace_id_to_get_context():
    """Any numbered workflow step invoking workspace.get_context must pass the id."""
    for skill in SKILL_NAMES:
        text = (TEMPLATES_DIR / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        offending = [
            line.strip()
            for line in text.splitlines()
            if re.match(r"^\s*\d+\.\s+`workspace\.get_context`", line)
        ]
        assert not offending, (
            f"skills/{skill}/SKILL.md calls workspace.get_context without workspace_id: "
            f"{offending}"
        )


def test_domain_model_documents_the_workspace_id_prerequisite():
    text = (TEMPLATES_DIR / "DOMAIN_MODEL.md").read_text(encoding="utf-8")
    assert "## Workspace-ID prerequisite" in text
    assert "workspace.get_context(workspace_id)" in text
    assert "workspace.list" in text


def test_every_shipped_agent_states_the_workspace_id_prerequisite():
    agents_dir = REPO_ROOT / "dist" / "plugins" / "claude-code" / "reqogniloom" / "agents"
    for agent in AGENT_FILES:
        path = agents_dir / f"{agent}.md"
        assert path.is_file(), f"missing shipped agent: {path}"
        text = path.read_text(encoding="utf-8")
        assert "Workspace-ID" in text and "workspace.get_context" in text, (
            f"{path} neither passes workspace_id nor states the prerequisite"
        )
