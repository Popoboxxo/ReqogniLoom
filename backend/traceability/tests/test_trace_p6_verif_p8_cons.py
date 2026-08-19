"""
SysEng 2.0 SE-Auditor — TRACE-P6, VERIF-P8, CONS-P9, CONS-P10 tests.

UMSETZUNGSPLAN_SYSENG_2.0.md §2.2. Each rule gets at least one positive
(no finding) and one negative (finding raised) case, plus preset-tier checks,
mirroring ``test_trace_p7.py`` / ``test_trace_p4_p5_arch003.py``'s structure.

Importing ``traceability.audit.rules.coverage_consistency`` directly (not via
``rules/__init__.py``, which the central-integration step still owns)
triggers the ``@register_rule`` self-registration side effect before
``RuleEngine()`` runs, exactly like the sibling rule-module test files.
"""
from __future__ import annotations

import pytest

from persistence.models import Requirement, RequirementLevel, TestCase
from traceability.audit import RuleEngine
from traceability.audit.registry import (
    CONS_P9,
    CONS_P10,
    TRACE_P6,
    VERIF_P8,
    get_registered_rules,
)
from traceability.audit.rules import coverage_consistency  # noqa: F401  (registers rules)
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_test_case,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local factories
# ---------------------------------------------------------------------------


def _workflow_definition(tenant, workspace, item_type):
    from workflow.models import WorkflowEngineDefinition

    return WorkflowEngineDefinition.unscoped.get_or_create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        item_type=item_type,
        defaults={
            "preset": "standard",
            "workflow_json": {"states": ["draft", "approved"], "transitions": []},
        },
    )[0]


def _set_workflow_state(tenant, workspace, item_type, item_id, current_state):
    from workflow.models import WorkflowItemState

    definition = _workflow_definition(tenant, workspace, item_type)
    return WorkflowItemState.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        item_id=item_id,
        item_type=item_type,
        definition=definition,
        current_state=current_state,
    )


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


def _run(tenant, workspace, tier="extended"):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


# ---------------------------------------------------------------------------
# TRACE-P6 — TestCase verifies an existing, non-superseded target.
# ---------------------------------------------------------------------------


class TestTraceP6:
    def test_testcase_verifying_requirement_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Req")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, TRACE_P6) == []

    def test_testcase_without_verifies_link_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            tc_artifact, tc = make_test_case(tenant_a, workspace_a, title="Orphan TC")

            result = _run(tenant_a, workspace_a, tier="standard")

        findings = _findings(result, TRACE_P6)
        assert len(findings) == 1
        assert str(tc_artifact.id) in findings[0].artifact_ids

    def test_testcase_verifying_only_a_superseded_requirement_is_flagged(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            old_req, _ = make_requirement(tenant_a, workspace_a, title="Old Req")
            new_req, _ = make_requirement(tenant_a, workspace_a, title="New Req")
            make_trace_link(new_req, old_req, tenant_a, "supersedes")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="TC")
            make_trace_link(tc_artifact, old_req, tenant_a, "verifies")

            result = _run(tenant_a, workspace_a, tier="standard")

        findings = _findings(result, TRACE_P6)
        assert len(findings) == 1
        assert str(tc_artifact.id) in findings[0].artifact_ids

    def test_outdated_testcase_is_not_flagged(self, tenant_a, workspace_a):
        """GH-574: a soft-deleted TestCase must not keep blocking the workspace.

        ``TestService.delete_test_case`` routes through
        ``workflow.services.outdate()``, which mirrors ``"outdated"`` into
        ``TestCase.status`` (REQ-165/REQ-166). TRACE-P6 used to audit every
        row regardless, so deleting the offending TestCase left the finding —
        and the id it named no longer resolved in any list view.
        """
        with active_tenant(tenant_a):
            tc_artifact, tc = make_test_case(tenant_a, workspace_a, title="Deleted TC")
            TestCase.objects.filter(pk=tc.pk).update(status="outdated")

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, TRACE_P6) == []

    def test_outdated_testcase_does_not_count_as_verification_evidence(
        self, tenant_a, workspace_a
    ):
        """VERIF-P8 side of the same helper: a deleted TestCase verifies nothing.

        Deliberate consequence of the GH-574 fix — ``_active_test_cases`` feeds
        both rules. Deleting the only TestCase covering a leaf Requirement
        clears TRACE-P6 *and* re-opens VERIF-P8, instead of leaving the
        Requirement silently "covered" by a removed artifact.
        """
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Leaf Req")
            tc_artifact, tc = make_test_case(tenant_a, workspace_a, title="Deleted TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")
            TestCase.objects.filter(pk=tc.pk).update(status="outdated")

            result = _run(tenant_a, workspace_a, tier="extended")

        assert _findings(result, TRACE_P6) == []
        verif = _findings(result, VERIF_P8)
        assert len(verif) == 1
        assert str(req_artifact.id) in verif[0].artifact_ids


# ---------------------------------------------------------------------------
# VERIF-P8 — every leaf Requirement (non-L4) has a verifying TestCase.
# ---------------------------------------------------------------------------


class TestVerifP8:
    def test_leaf_requirement_with_test_case_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Leaf Req")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")

            result = _run(tenant_a, workspace_a, tier="extended")

        assert _findings(result, VERIF_P8) == []

    def test_leaf_requirement_without_test_case_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Leaf Req")

            result = _run(tenant_a, workspace_a, tier="extended")

        findings = _findings(result, VERIF_P8)
        assert len(findings) == 1
        assert str(req_artifact.id) in findings[0].artifact_ids

    def test_non_leaf_requirement_is_not_required_to_have_a_test_case(
        self, tenant_a, workspace_a
    ):
        """A Requirement that was itself decomposed (has children) is not a leaf."""
        with active_tenant(tenant_a):
            parent_artifact, _ = make_requirement(tenant_a, workspace_a, title="Parent")
            child_artifact, _ = make_requirement(tenant_a, workspace_a, title="Child")
            make_trace_link(parent_artifact, child_artifact, tenant_a, "decomposes")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="TC")
            make_trace_link(tc_artifact, child_artifact, tenant_a, "verifies")

            result = _run(tenant_a, workspace_a, tier="extended")

        # Only the leaf (child) needs a TestCase; the parent is exempt.
        assert _findings(result, VERIF_P8) == []

    def test_l4_requirement_is_out_of_scope(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            artifact = make_artifact(tenant_a, workspace_a, artifact_type="requirement")
            Requirement.objects.create(
                tenant=tenant_a,
                artifact=artifact,
                title="Presentation Req",
                level=RequirementLevel.L4_MATERIAL,
            )

            result = _run(tenant_a, workspace_a, tier="extended")

        assert _findings(result, VERIF_P8) == []

    def test_standard_preset_does_not_run_verif_p8(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, title="Leaf Req")

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, VERIF_P8) == []


# ---------------------------------------------------------------------------
# CONS-P9 / CONS-P10 — deferred (LinkType.CONFLICTS_WITH / SUPERCEDES do not
# exist in the traceability.types.LinkType enum, and no unvalidated string
# workaround is used per product decision). Both rules stay registered but
# must never produce a finding and must never crash, for any rigor tier. See
# the "LinkType gap" section of coverage_consistency.py's module docstring.
# ---------------------------------------------------------------------------


class TestConsP9AndP10AreDeferred:
    def test_both_rules_are_still_registered(self):
        ids = {r.rule_id for r in get_registered_rules()}
        assert CONS_P9 in ids
        assert CONS_P10 in ids

    def test_both_rules_expose_a_deferred_reason(self):
        rules = {r.rule_id: r for r in get_registered_rules()}
        assert rules[CONS_P9].deferred_reason
        assert rules[CONS_P10].deferred_reason

    @pytest.mark.parametrize("tier", ["minimal", "standard", "extended"])
    def test_run_yields_zero_findings_for_every_tier_no_matter_the_data(
        self, tenant_a, workspace_a, tier
    ):
        """Deferred rules must never fire, even against data that would have
        violated the old (now-removed) CONS-P9/CONS-P10 check logic."""
        with active_tenant(tenant_a):
            req_a, requirement_a = make_requirement(tenant_a, workspace_a, title="A")
            req_b, _ = make_requirement(tenant_a, workspace_a, title="B")
            _set_workflow_state(
                tenant_a, workspace_a, "Requirement", requirement_a.id, "approved"
            )
            old_req, _ = make_requirement(tenant_a, workspace_a, title="Old")
            new_req, _ = make_requirement(tenant_a, workspace_a, title="New")
            make_trace_link(new_req, old_req, tenant_a, "supersedes")
            make_trace_link(req_a, old_req, tenant_a, "satisfies")
            make_trace_link(req_a, req_b, tenant_a, "conflicts-with")

            result = _run(tenant_a, workspace_a, tier=tier)

        assert _findings(result, CONS_P9) == []
        assert _findings(result, CONS_P10) == []


# ---------------------------------------------------------------------------
# Preset structural guarantee, exercised across TRACE-P6/VERIF-P8.
# ---------------------------------------------------------------------------


class TestMinimalPresetIsUnaffected:
    def test_minimal_preset_yields_no_findings_on_violating_data(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            # TRACE-P6 violation: orphan TestCase.
            make_test_case(tenant_a, workspace_a, title="Orphan TC")
            # VERIF-P8 violation: leaf Requirement without TestCase.
            make_requirement(tenant_a, workspace_a, title="Leaf Req")

            result = _run(tenant_a, workspace_a, tier="minimal")

        assert result.findings == []
