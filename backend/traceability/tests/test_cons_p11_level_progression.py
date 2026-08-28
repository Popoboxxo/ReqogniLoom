"""
SE-Auditor — CONS-P11 (V-model cascade level progression) tests.

SYSTEMAUDIT_2026-08-27 P1-9. Sibling of ``test_trace_p6_verif_p8_cons.py`` /
``test_trace_p4_p5_arch003.py`` and structured the same way: at least one
positive (no finding) and one negative (finding raised) case per behaviour,
plus the preset-tier and registration guard rails.

Split into its own file rather than appended to
``test_trace_p6_verif_p8_cons.py`` because CONS-P11 lives in its own rule
module (``rules/level_progression.py``) — the test files in this package are
organised one-per-rule-module, and that file's name already enumerates the
rules of ``coverage_consistency``.

Importing ``traceability.audit.rules.level_progression`` directly triggers the
``@register_rule`` self-registration side effect before ``RuleEngine()`` runs,
exactly like the sibling rule-module test files.
"""
from __future__ import annotations

import pytest

from persistence.models import RequirementLevel
from traceability.audit import RuleEngine
from traceability.audit.registry import CONS_P11, get_registered_rules
from traceability.audit.rules import level_progression  # noqa: F401  (registers rule)
from traceability.audit.types import Severity
from traceability.tests.conftest import (
    active_tenant,
    make_requirement,
    make_trace_link,
)
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _findings(result, rule_id=CONS_P11):
    return [f for f in result.findings if f.rule_id == rule_id]


def _run(tenant, workspace, tier="extended"):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


def _leveled_requirement(tenant, workspace, title, level):
    """Create a Requirement and assign *level* (``None`` leaves it NULL).

    ``conftest.make_requirement`` deliberately has no ``level`` parameter, so
    the field is set afterwards — same approach as
    ``test_trace_p4_p5_arch003.py``'s L4 fixture.
    """
    artifact, req = make_requirement(tenant, workspace, title=title)
    if level is not None:
        req.level = level
        req.save(update_fields=["level"])
    return artifact, req


def _decomposition(tenant, workspace, parent_level, child_level, link_type=None):
    """Build a parent --decomposes--> child pair with the given levels."""
    parent_artifact, _ = _leveled_requirement(
        tenant, workspace, "Parent Req", parent_level
    )
    child_artifact, _ = _leveled_requirement(
        tenant, workspace, "Child Req", child_level
    )
    make_trace_link(
        parent_artifact,
        child_artifact,
        tenant,
        link_type or LinkType.DECOMPOSES.value,
    )
    return parent_artifact, child_artifact


# ---------------------------------------------------------------------------
# Correct progression -> clean
# ---------------------------------------------------------------------------


class TestConsP11Clean:
    def test_child_exactly_one_level_below_parent_is_clean(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a,
                workspace_a,
                RequirementLevel.L1_SYSTEM,
                RequirementLevel.L2_SUBSYSTEM,
            )
            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []

    def test_full_cascade_chain_is_clean(self, tenant_a, workspace_a):
        """L1 -> L2 -> L3 -> L4, the complete cascade, raises nothing."""
        with active_tenant(tenant_a):
            artifacts = [
                _leveled_requirement(tenant_a, workspace_a, f"L{lvl}", lvl)[0]
                for lvl in (
                    RequirementLevel.L1_SYSTEM,
                    RequirementLevel.L2_SUBSYSTEM,
                    RequirementLevel.L3_COMPONENT,
                    RequirementLevel.L4_PRESENTATION,
                )
            ]
            for parent, child in zip(artifacts, artifacts[1:]):
                make_trace_link(
                    parent, child, tenant_a, LinkType.DECOMPOSES.value
                )

            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []

    def test_inverse_derives_from_spelling_is_also_clean(
        self, tenant_a, workspace_a
    ):
        """``child --derives-from--> parent`` is the same edge (issue #395)."""
        with active_tenant(tenant_a):
            parent_artifact, _ = _leveled_requirement(
                tenant_a, workspace_a, "Parent", RequirementLevel.L2_SUBSYSTEM
            )
            child_artifact, _ = _leveled_requirement(
                tenant_a, workspace_a, "Child", RequirementLevel.L3_COMPONENT
            )
            make_trace_link(
                child_artifact,
                parent_artifact,
                tenant_a,
                LinkType.DERIVES_FROM.value,
            )

            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []


# ---------------------------------------------------------------------------
# Wrong progression -> flagged
# ---------------------------------------------------------------------------


class TestConsP11Violations:
    def test_skipped_level_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            parent_artifact, child_artifact = _decomposition(
                tenant_a,
                workspace_a,
                RequirementLevel.L1_SYSTEM,
                RequirementLevel.L3_COMPONENT,
            )
            result = _run(tenant_a, workspace_a)

        findings = _findings(result)
        assert len(findings) == 1
        assert str(child_artifact.id) in findings[0].artifact_ids
        assert str(parent_artifact.id) in findings[0].artifact_ids

    def test_repeated_level_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a,
                workspace_a,
                RequirementLevel.L2_SUBSYSTEM,
                RequirementLevel.L2_SUBSYSTEM,
            )
            result = _run(tenant_a, workspace_a)

        assert len(_findings(result)) == 1

    def test_inverted_level_is_flagged(self, tenant_a, workspace_a):
        """A child *above* its parent in the cascade."""
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a,
                workspace_a,
                RequirementLevel.L3_COMPONENT,
                RequirementLevel.L2_SUBSYSTEM,
            )
            result = _run(tenant_a, workspace_a)

        assert len(_findings(result)) == 1

    def test_l4_is_not_exempt_from_this_rule(self, tenant_a, workspace_a):
        """Deliberate deviation from the §2.2 "L4 out of scope" convention.

        The other rule modules skip an explicitly-assigned L4 because the
        *verification/allocation* mandates make no sense for it. Level
        progression is a different question, and exempting L4 would blind the
        rule at exactly the boundary it polices — here an L1 parent with an L4
        child (two tiers skipped).
        """
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a,
                workspace_a,
                RequirementLevel.L1_SYSTEM,
                RequirementLevel.L4_PRESENTATION,
            )
            result = _run(tenant_a, workspace_a)

        assert len(_findings(result)) == 1

    def test_one_finding_per_edge_not_per_requirement(
        self, tenant_a, workspace_a
    ):
        """A child under two parents, both disagreeing, yields two findings."""
        with active_tenant(tenant_a):
            parent_one, _ = _leveled_requirement(
                tenant_a, workspace_a, "Parent 1", RequirementLevel.L1_SYSTEM
            )
            parent_two, _ = _leveled_requirement(
                tenant_a, workspace_a, "Parent 2", RequirementLevel.L2_SUBSYSTEM
            )
            child, _ = _leveled_requirement(
                tenant_a, workspace_a, "Child", RequirementLevel.L4_PRESENTATION
            )
            make_trace_link(parent_one, child, tenant_a, LinkType.DECOMPOSES.value)
            make_trace_link(parent_two, child, tenant_a, LinkType.DECOMPOSES.value)

            result = _run(tenant_a, workspace_a)

        findings = _findings(result)
        assert len(findings) == 2
        named_parents = {
            artifact_id
            for finding in findings
            for artifact_id in finding.artifact_ids
        } - {str(child.id)}
        assert named_parents == {str(parent_one.id), str(parent_two.id)}


# ---------------------------------------------------------------------------
# NULL level on either side -> not flagged
# ---------------------------------------------------------------------------


class TestConsP11NullLevels:
    def test_null_parent_level_is_not_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a, workspace_a, None, RequirementLevel.L3_COMPONENT
            )
            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []

    def test_null_child_level_is_not_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a, workspace_a, RequirementLevel.L1_SYSTEM, None
            )
            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []

    def test_both_levels_null_is_not_flagged(self, tenant_a, workspace_a):
        """The state of practically every pre-P1-9 Requirement — must stay silent."""
        with active_tenant(tenant_a):
            _decomposition(tenant_a, workspace_a, None, None)
            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []

    def test_unlinked_requirements_are_not_flagged(self, tenant_a, workspace_a):
        """No hierarchy edge means no progression claim to check."""
        with active_tenant(tenant_a):
            _leveled_requirement(
                tenant_a, workspace_a, "Lonely", RequirementLevel.L4_PRESENTATION
            )
            result = _run(tenant_a, workspace_a)

        assert _findings(result) == []


# ---------------------------------------------------------------------------
# Tier placement, severity and registration
# ---------------------------------------------------------------------------


class TestConsP11Wiring:
    def test_rule_is_registered(self):
        assert CONS_P11 in {r.rule_id for r in get_registered_rules()}

    def test_severity_is_warning_on_every_tier(self):
        rule = next(r for r in get_registered_rules() if r.rule_id == CONS_P11)
        for tier in ("minimal", "standard", "extended"):
            assert rule.severity_for_tier(tier) is Severity.WARNING

    @pytest.mark.parametrize("tier", ["minimal", "standard"])
    def test_rule_does_not_run_below_extended(self, tenant_a, workspace_a, tier):
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a,
                workspace_a,
                RequirementLevel.L1_SYSTEM,
                RequirementLevel.L4_PRESENTATION,
            )
            result = _run(tenant_a, workspace_a, tier=tier)

        assert _findings(result) == []

    def test_emitted_finding_carries_warning_severity(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            _decomposition(
                tenant_a,
                workspace_a,
                RequirementLevel.L1_SYSTEM,
                RequirementLevel.L3_COMPONENT,
            )
            result = _run(tenant_a, workspace_a)

        findings = _findings(result)
        assert len(findings) == 1
        assert findings[0].severity is Severity.WARNING
