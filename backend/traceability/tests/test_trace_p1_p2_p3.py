"""
SysEng 2.0 SE-Auditor — TRACE-P1, TRACE-P1b, TRACE-P2, TRACE-P3 tests.

UMSETZUNGSPLAN_SYSENG_2.0.md §2.2. Each rule gets at least one positive case
(no finding) and one negative case (finding correctly raised). Also covers
the TRACE-P2 tiered severity (WARNING at standard, BLOCKER at extended) and
the L4 out-of-scope exemption.

These rules are NOT wired into ``rules/__init__.py`` yet (a later
integration step does that centrally to avoid merge conflicts with a
parallel rule-implementer). Importing the module directly here triggers its
``@register_rule`` decorators, exactly like ``RuleEngine.__init__`` would
once the import is added to ``rules/__init__.py``.
"""
from __future__ import annotations

import pytest

import traceability.audit.rules.trace_derivation_allocation  # noqa: F401  (registration)
from persistence.models import (
    ArchitectureElement,
    Requirement,
    RequirementLevel,
    StakeholderNeed,
)
from traceability.audit import AuditScope, RuleEngine
from traceability.audit.registry import TRACE_P1, TRACE_P1B, TRACE_P2, TRACE_P3
from traceability.tests.conftest import active_tenant, make_artifact, make_trace_link

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _need(tenant, workspace, title="Need"):
    artifact = make_artifact(tenant, workspace, artifact_type="StakeholderNeed")
    need = StakeholderNeed.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, need


def _requirement(tenant, workspace, title="Req", level=None):
    artifact = make_artifact(tenant, workspace, artifact_type="Requirement")
    req = Requirement.objects.create(
        tenant=tenant, artifact=artifact, title=title, level=level
    )
    return artifact, req


def _arch_element(tenant, workspace, title="AE"):
    artifact = make_artifact(tenant, workspace, artifact_type="ArchitectureElement")
    ae = ArchitectureElement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, ae


def _run(tier, workspace, tenant):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


# ---------------------------------------------------------------------------
# TRACE-P1 — root Requirement derives-from a StakeholderNeed
# ---------------------------------------------------------------------------


class TestTraceP1:
    def test_root_requirement_with_need_link_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            need_art, _ = _need(tenant_a, workspace_a)
            req_art, _ = _requirement(tenant_a, workspace_a)
            make_trace_link(req_art, need_art, tenant_a, "derives-from")

            result = _run("standard", workspace_a, tenant_a)

        assert _findings(result, TRACE_P1) == []

    def test_root_requirement_without_need_link_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_art, _ = _requirement(tenant_a, workspace_a, title="Orphan Root")

            result = _run("standard", workspace_a, tenant_a)

        findings = _findings(result, TRACE_P1)
        assert len(findings) == 1
        assert str(req_art.id) in findings[0].artifact_ids

    def test_derives_from_wrong_target_type_still_flagged(self, tenant_a, workspace_a):
        """A root Requirement deriving from another Requirement (not a Need)
        satisfies the general orphan check (P1b) but not the P1 need-link."""
        with active_tenant(tenant_a):
            need_art, _ = _need(tenant_a, workspace_a)
            other_art, _ = _requirement(tenant_a, workspace_a, title="Other")
            make_trace_link(other_art, need_art, tenant_a, "derives-from")
            root_art, _ = _requirement(tenant_a, workspace_a, title="Root")
            make_trace_link(root_art, other_art, tenant_a, "derives-from")

            result = _run("standard", workspace_a, tenant_a)

        findings = _findings(result, TRACE_P1)
        assert len(findings) == 1
        assert str(root_art.id) in findings[0].artifact_ids


# ---------------------------------------------------------------------------
# TRACE-P1b — orphan-requirement check (any upstream derives-from)
# ---------------------------------------------------------------------------


class TestTraceP1b:
    def test_requirement_with_upstream_link_is_clean(self, tenant_a, workspace_a):
        """Every Requirement needs its OWN upstream 'derives-from' — the
        root's is to a StakeholderNeed, the child's is to its parent."""
        with active_tenant(tenant_a):
            need_art, _ = _need(tenant_a, workspace_a)
            parent_art, _ = _requirement(tenant_a, workspace_a, title="Parent")
            make_trace_link(parent_art, need_art, tenant_a, "derives-from")
            child_art, _ = _requirement(tenant_a, workspace_a, title="Child")
            make_trace_link(child_art, parent_art, tenant_a, "decomposes")
            make_trace_link(child_art, parent_art, tenant_a, "derives-from")

            result = _run("standard", workspace_a, tenant_a)

        assert _findings(result, TRACE_P1B) == []

    def test_requirement_without_any_upstream_link_is_flagged(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent_art, _ = _requirement(tenant_a, workspace_a, title="Parent")
            child_art, _ = _requirement(tenant_a, workspace_a, title="Child")
            # decompose() in production only creates 'decomposes', not
            # 'derives-from' (see module docstring) — this is exactly the
            # gap TRACE-P1b exists to catch.
            make_trace_link(child_art, parent_art, tenant_a, "decomposes")

            result = _run("standard", workspace_a, tenant_a)

        findings = _findings(result, TRACE_P1B)
        ids_flagged = {a for f in findings for a in f.artifact_ids}
        assert str(child_art.id) in ids_flagged

    def test_l4_requirement_is_out_of_scope(self, tenant_a, workspace_a):
        """L4 (Presentation) is explicitly excluded from every rule (§2.2)."""
        with active_tenant(tenant_a):
            _requirement(
                tenant_a,
                workspace_a,
                title="L4 leaf",
                level=RequirementLevel.L4_MATERIAL,
            )

            result = _run("standard", workspace_a, tenant_a)

        assert _findings(result, TRACE_P1B) == []

    def test_deleted_requirement_is_excluded(self, tenant_a, workspace_a):
        """Requirement has a status mirror (Phase 0) — ``outdate()`` writes
        ``status``, not the dead ``lifecycle_status`` column, so the fixture
        must set the field the rule actually reads."""
        with active_tenant(tenant_a):
            art, req = _requirement(tenant_a, workspace_a, title="Deleted")
            req.status = "outdated"
            req.save(update_fields=["status"])

            result = _run("standard", workspace_a, tenant_a)

        assert _findings(result, TRACE_P1B) == []


# ---------------------------------------------------------------------------
# TRACE-P2 — Requirement allocated-to an ArchitectureElement (tiered severity)
# ---------------------------------------------------------------------------


class TestTraceP2:
    def test_allocated_requirement_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_art, _ = _requirement(tenant_a, workspace_a)
            ae_art, _ = _arch_element(tenant_a, workspace_a)
            make_trace_link(req_art, ae_art, tenant_a, "allocated-to")

            result = _run("extended", workspace_a, tenant_a)

        assert _findings(result, TRACE_P2) == []

    def test_unallocated_requirement_is_flagged(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_art, _ = _requirement(tenant_a, workspace_a, title="Unallocated")

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, TRACE_P2)
        assert len(findings) == 1
        assert str(req_art.id) in findings[0].artifact_ids

    def test_severity_is_warning_at_standard_and_blocker_at_extended(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            _requirement(tenant_a, workspace_a, title="Unallocated")

            standard_result = _run("standard", workspace_a, tenant_a)
            extended_result = _run("extended", workspace_a, tenant_a)

        from traceability.audit.types import Severity

        standard_findings = _findings(standard_result, TRACE_P2)
        extended_findings = _findings(extended_result, TRACE_P2)
        assert len(standard_findings) == 1
        assert len(extended_findings) == 1
        assert standard_findings[0].severity is Severity.WARNING
        assert extended_findings[0].severity is Severity.BLOCKER


# ---------------------------------------------------------------------------
# TRACE-P3 — ArchitectureElement satisfies/implements >= 1 Requirement
# (Extended only)
# ---------------------------------------------------------------------------


class TestTraceP3:
    def test_element_satisfying_requirement_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_art, _ = _requirement(tenant_a, workspace_a)
            ae_art, _ = _arch_element(tenant_a, workspace_a)
            make_trace_link(ae_art, req_art, tenant_a, "satisfies")

            result = _run("extended", workspace_a, tenant_a)

        assert _findings(result, TRACE_P3) == []

    def test_element_implementing_requirement_is_clean(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            req_art, _ = _requirement(tenant_a, workspace_a)
            ae_art, _ = _arch_element(tenant_a, workspace_a)
            make_trace_link(ae_art, req_art, tenant_a, "implements")

            result = _run("extended", workspace_a, tenant_a)

        assert _findings(result, TRACE_P3) == []

    def test_element_without_satisfies_or_implements_is_flagged(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            ae_art, _ = _arch_element(tenant_a, workspace_a, title="Unsatisfied")

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, TRACE_P3)
        assert len(findings) == 1
        assert str(ae_art.id) in findings[0].artifact_ids

    def test_standard_preset_does_not_run_p3(self, tenant_a, workspace_a):
        """TRACE-P3 is Extended-only; Standard must not emit it."""
        with active_tenant(tenant_a):
            _arch_element(tenant_a, workspace_a, title="Unsatisfied")

            result = _run("standard", workspace_a, tenant_a)

        assert _findings(result, TRACE_P3) == []


# ---------------------------------------------------------------------------
# Cross-cutting: Minimal preset has zero findings across all four rules.
# ---------------------------------------------------------------------------


class TestMinimalPresetHasNoFindings:
    def test_minimal_preset_yields_no_findings_on_incomplete_graph(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            _requirement(tenant_a, workspace_a, title="Unlinked")
            _arch_element(tenant_a, workspace_a, title="Unsatisfied")

            result = _run("minimal", workspace_a, tenant_a)

        assert result.findings == []
