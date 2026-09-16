"""
SE-Auditor severity calibration regression tests (issue #581).

The QS review of #581 found the auditor scoring a 100% blocker rate with zero
warnings — TRACE-P2 (missing allocation) emitted as a BLOCKER, and ARCH-003
repeating 683x from a single root cause. Both calibrations are pinned here:

  * TRACE-P2 audits allocation *coverage*, which is advisory: it is a WARNING
    at every tier, never a BLOCKER (see ``severity_for_tier``).
  * ARCH-003 aggregates per architecture decomposition edge, so one missing
    derivation chain yields one finding instead of one per Requirement
    allocated to the child element (see the rule module's "ARCH-003
    granularity" section).

The genuine blockers (TRACE-P1/P1b, TRACE-P3, VERIF-P8, ...) must be
unaffected by both — the last test in this module pins that.
"""
from __future__ import annotations

import pytest

from persistence.models import ArchitectureElement
from traceability.audit import RuleEngine
from traceability.audit.registry import (
    ARCH_003,
    TRACE_P1,
    TRACE_P1B,
    TRACE_P2,
    VERIF_P8,
)
from traceability.audit.types import Severity
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_trace_link,
)
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _element(tenant, workspace, *, parent=None, title="AE"):
    """Create an ArchitectureElement (optionally nested under *parent*)."""
    artifact = make_artifact(tenant, workspace, artifact_type="architecture-element")
    return ArchitectureElement.objects.create(
        tenant=tenant, artifact=artifact, title=title, parent=parent
    )


def _allocate(tenant, workspace, element, title="Req"):
    """Create a Requirement allocated to *element*, with no derivation link."""
    artifact, _ = make_requirement(tenant, workspace, title=title)
    make_trace_link(artifact, element.artifact, tenant, LinkType.ALLOCATED_TO.value)
    return artifact


def _run(tier, workspace, tenant):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


# ---------------------------------------------------------------------------
# TRACE-P2 — allocation coverage is advisory (WARNING), never a BLOCKER
# ---------------------------------------------------------------------------


class TestTraceP2SeverityCalibration:
    def test_unallocated_requirement_is_a_warning_at_extended(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, title="Unallocated")

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, TRACE_P2)
        assert len(findings) == 1
        assert findings[0].severity is Severity.WARNING
        assert TRACE_P2 not in {f.rule_id for f in result.blockers()}

    def test_extended_tier_reports_warnings_as_well_as_blockers(
        self, tenant_a, workspace_a
    ):
        """The #581 headline symptom: 100% blockers, zero warnings.

        An unallocated, untraced Requirement still blocks (TRACE-P1/P1b,
        VERIF-P8), but the auditor must also report the advisory TRACE-P2
        warning next to it — a 100% blocker rate is the mis-calibration.
        """
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, title="Unallocated")

            result = _run("extended", workspace_a, tenant_a)

        blocker_rules = {f.rule_id for f in result.blockers()}
        warning_rules = {f.rule_id for f in result.warnings()}
        # Genuine blockers are untouched by the calibration ...
        assert {TRACE_P1, TRACE_P1B, VERIF_P8} <= blocker_rules
        # ... and the advisory classification produces actual warnings.
        assert warning_rules == {TRACE_P2}

    def test_aggregated_arch003_findings_stay_blockers(self, tenant_a, workspace_a):
        """Only TRACE-P2 was re-calibrated — ARCH-003 keeps its teeth."""
        with active_tenant(tenant_a):
            parent = _element(tenant_a, workspace_a, title="System")
            child = _element(tenant_a, workspace_a, parent=parent, title="Sub")
            _allocate(tenant_a, workspace_a, parent, title="Parent Req")
            _allocate(tenant_a, workspace_a, child, title="Child Req")

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, ARCH_003)
        assert len(findings) == 1
        assert findings[0].severity is Severity.BLOCKER


# ---------------------------------------------------------------------------
# ARCH-003 — one finding per decomposition edge (#581)
# ---------------------------------------------------------------------------


class TestArch003Aggregation:
    def test_one_edge_yields_one_finding_with_all_requirements(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent = _element(tenant_a, workspace_a, title="System")
            child = _element(tenant_a, workspace_a, parent=parent, title="Sub")
            _allocate(tenant_a, workspace_a, parent, title="Parent Req")
            child_reqs = [
                _allocate(tenant_a, workspace_a, child, title=f"Child Req {i}")
                for i in range(4)
            ]

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, ARCH_003)
        assert len(findings) == 1
        asserted_ids = set(findings[0].artifact_ids)
        assert {str(a.id) for a in child_reqs} <= asserted_ids
        assert {str(child.id), str(parent.id)} <= asserted_ids
        assert "4 Requirement(s)" in findings[0].message

    def test_finding_count_is_bounded_by_elements_not_allocations(
        self, tenant_a, workspace_a
    ):
        """Three identically broken children -> three findings, not six."""
        with active_tenant(tenant_a):
            parent = _element(tenant_a, workspace_a, title="System")
            _allocate(tenant_a, workspace_a, parent, title="Parent Req")
            children = [
                _element(tenant_a, workspace_a, parent=parent, title=f"Sub {i}")
                for i in range(3)
            ]
            for child in children:
                for i in range(2):
                    _allocate(tenant_a, workspace_a, child, title=f"{child.title}-{i}")

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, ARCH_003)
        assert len(findings) == 3
        for finding in findings:
            child_id = finding.artifact_ids[2]
            assert child_id in {str(child.id) for child in children}
            # (*2 requirements, child, parent)
            assert len(finding.artifact_ids) == 4

    def test_unallocated_parent_still_yields_exactly_one_finding(
        self, tenant_a, workspace_a
    ):
        """The empty-parent-allocation case used to explode per requirement.

        With no Requirement allocated to the parent element, *every*
        Requirement on the child element fails the check — one root cause, so
        it must stay one finding.
        """
        with active_tenant(tenant_a):
            parent = _element(tenant_a, workspace_a, title="System")
            child = _element(tenant_a, workspace_a, parent=parent, title="Sub")
            child_reqs = [
                _allocate(tenant_a, workspace_a, child, title=f"Child Req {i}")
                for i in range(5)
            ]

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, ARCH_003)
        assert len(findings) == 1
        assert {str(a.id) for a in child_reqs} <= set(findings[0].artifact_ids)

    def test_only_requirements_without_derivation_are_named(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent = _element(tenant_a, workspace_a, title="System")
            child = _element(tenant_a, workspace_a, parent=parent, title="Sub")
            parent_req = _allocate(tenant_a, workspace_a, parent, title="Parent Req")
            for i in range(2):
                derived = _allocate(
                    tenant_a, workspace_a, child, title=f"Derived Child Req {i}"
                )
                make_trace_link(
                    derived, parent_req, tenant_a, LinkType.DERIVES_FROM.value
                )
            und_req = _allocate(tenant_a, workspace_a, child, title="Underived Child Req")

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, ARCH_003)
        assert len(findings) == 1
        assert findings[0].artifact_ids == (
            str(und_req.id),
            str(child.id),
            str(parent.id),
        )

    def test_message_lists_at_most_five_requirement_ids(self, tenant_a, workspace_a):
        """A child element with 8 offenders must not produce an unbounded message."""
        with active_tenant(tenant_a):
            parent = _element(tenant_a, workspace_a, title="System")
            child = _element(tenant_a, workspace_a, parent=parent, title="Sub")
            _allocate(tenant_a, workspace_a, parent, title="Parent Req")
            child_reqs = [
                _allocate(tenant_a, workspace_a, child, title=f"Child Req {i}")
                for i in range(8)
            ]

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, ARCH_003)
        assert len(findings) == 1
        # Every offending Requirement is still reported structurally ...
        assert len(findings[0].artifact_ids) == len(child_reqs) + 2
        # ... while the rendered message stays bounded.
        assert "(+3 more)" in findings[0].message
        assert "8 Requirement(s)" in findings[0].message
