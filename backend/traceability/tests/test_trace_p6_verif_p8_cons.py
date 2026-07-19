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

from persistence.models import (
    ArchitectureElement,
    Requirement,
    RequirementLevel,
    StakeholderNeed,
)
from traceability.audit import RuleEngine
from traceability.audit.registry import CONS_P9, CONS_P10, TRACE_P6, VERIF_P8
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
# Local factories (mirrors test_trace_p4_p5_arch003.py's _architecture_element)
# ---------------------------------------------------------------------------


def _architecture_element(tenant, workspace, *, parent=None, title="AE"):
    artifact = make_artifact(tenant, workspace, artifact_type="architecture-element")
    return artifact, ArchitectureElement.objects.create(
        tenant=tenant, artifact=artifact, title=title, parent=parent
    )


def _stakeholder_need(tenant, workspace, *, title="Need"):
    artifact = make_artifact(tenant, workspace, artifact_type="stakeholder-need")
    return artifact, StakeholderNeed.objects.create(
        tenant=tenant, artifact=artifact, title=title
    )


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
# CONS-P9 — open CONFLICTS_WITH links block the Approval-Transition.
# ---------------------------------------------------------------------------


class TestConsP9:
    def test_draft_artifact_with_open_conflict_is_not_flagged(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            req_a, requirement_a = make_requirement(tenant_a, workspace_a, title="A")
            req_b, _ = make_requirement(tenant_a, workspace_a, title="B")
            make_trace_link(req_a, req_b, tenant_a, "conflicts-with")
            _set_workflow_state(
                tenant_a, workspace_a, "Requirement", requirement_a.id, "draft"
            )

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, CONS_P9) == []

    def test_approved_artifact_with_open_conflict_is_flagged(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            req_a, requirement_a = make_requirement(tenant_a, workspace_a, title="A")
            req_b, _ = make_requirement(tenant_a, workspace_a, title="B")
            make_trace_link(req_a, req_b, tenant_a, "conflicts-with")
            _set_workflow_state(
                tenant_a, workspace_a, "Requirement", requirement_a.id, "approved"
            )

            result = _run(tenant_a, workspace_a, tier="standard")

        findings = _findings(result, CONS_P9)
        assert len(findings) == 1
        assert str(req_a.id) in findings[0].artifact_ids

    def test_approved_architecture_element_with_open_conflict_is_flagged(
        self, tenant_a, workspace_a
    ):
        """ArchitectureElement has no status mirror — must read WorkflowItemState directly."""
        with active_tenant(tenant_a):
            ae_artifact, ae = _architecture_element(tenant_a, workspace_a, title="AE")
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Req")
            make_trace_link(ae_artifact, req_artifact, tenant_a, "conflicts-with")
            _set_workflow_state(
                tenant_a, workspace_a, "ArchitectureElement", ae.id, "approved"
            )

            result = _run(tenant_a, workspace_a, tier="standard")

        findings = _findings(result, CONS_P9)
        assert len(findings) == 1
        assert str(ae_artifact.id) in findings[0].artifact_ids


# ---------------------------------------------------------------------------
# CONS-P10 — no active TraceLink references a superseded artifact.
# ---------------------------------------------------------------------------


class TestConsP10:
    def test_link_to_non_superseded_artifact_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            old_req, _ = make_requirement(tenant_a, workspace_a, title="Old")
            new_req, _ = make_requirement(tenant_a, workspace_a, title="New")
            make_trace_link(new_req, old_req, tenant_a, "supersedes")

            unrelated_a, _ = make_requirement(tenant_a, workspace_a, title="X")
            unrelated_b, _ = make_requirement(tenant_a, workspace_a, title="Y")
            make_trace_link(unrelated_a, unrelated_b, tenant_a, "satisfies")

            result = _run(tenant_a, workspace_a, tier="standard")

        assert _findings(result, CONS_P10) == []

    def test_dangling_reference_to_superseded_artifact_is_flagged(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            old_req, _ = make_requirement(tenant_a, workspace_a, title="Old")
            new_req, _ = make_requirement(tenant_a, workspace_a, title="New")
            make_trace_link(new_req, old_req, tenant_a, "supersedes")

            other, _ = make_requirement(tenant_a, workspace_a, title="Other")
            make_trace_link(other, old_req, tenant_a, "satisfies")

            result = _run(tenant_a, workspace_a, tier="standard")

        findings = _findings(result, CONS_P10)
        assert len(findings) == 1
        assert str(old_req.id) in findings[0].artifact_ids


# ---------------------------------------------------------------------------
# Preset structural guarantee, exercised across all 4 rules.
# ---------------------------------------------------------------------------


class TestMinimalPresetIsUnaffected:
    def test_minimal_preset_yields_no_findings_on_violating_data(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            # TRACE-P6 violation: orphan TestCase.
            make_test_case(tenant_a, workspace_a, title="Orphan TC")
            # VERIF-P8 violation: leaf Requirement without TestCase.
            req_artifact, requirement = make_requirement(
                tenant_a, workspace_a, title="Leaf Req"
            )
            # CONS-P9 violation: approved Requirement with an open conflict.
            other_req, _ = make_requirement(tenant_a, workspace_a, title="Other")
            make_trace_link(req_artifact, other_req, tenant_a, "conflicts-with")
            _set_workflow_state(
                tenant_a, workspace_a, "Requirement", requirement.id, "approved"
            )
            # CONS-P10 violation: dangling reference to a superseded artifact.
            old_req, _ = make_requirement(tenant_a, workspace_a, title="Old")
            new_req, _ = make_requirement(tenant_a, workspace_a, title="New")
            make_trace_link(new_req, old_req, tenant_a, "supersedes")
            make_trace_link(other_req, old_req, tenant_a, "satisfies")

            result = _run(tenant_a, workspace_a, tier="minimal")

        assert result.findings == []
