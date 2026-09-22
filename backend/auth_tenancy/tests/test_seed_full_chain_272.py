"""#272 — the ``seed_full_chain`` fixture and its golden-path guarantees.

Cluster-5 spec section 7.5 / AC-272-F1..F4. The command must produce the
documented minimum counts, be idempotent, and its workspace must be the proof
that the Extended auditor comes back clean (VAL-P1 included) and that the
requirement approval gate is satisfiable.
"""
from __future__ import annotations

import pytest

from persistence.models import (
    Artifact,
    ArchitectureElement,
    Goal,
    Requirement,
    StakeholderNeed,
    TestCase,
    TestRun,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(db):
    from django.core.management import call_command

    call_command("seed_full_chain", verbosity=0)
    # The command clears the tenant context in its own ``finally`` (it is
    # request-less), so re-arm it for the assertions below.
    workspace = Workspace.unscoped.get(name="SysEng Full-Chain Demo")
    TenantContext.set_tenant(workspace.tenant_id)
    return workspace


def _counts(workspace_id):
    from baseline.models import BaselineSnapshot
    from persistence.models import ChangeRequest, ChangeRequestAffectedItem

    return {
        "needs": StakeholderNeed.unscoped.filter(
            artifact__workspace_id=workspace_id
        ).count(),
        "goals": Goal.unscoped.filter(workspace_id=workspace_id).count(),
        "requirements": Requirement.unscoped.filter(
            artifact__workspace_id=workspace_id
        ).count(),
        "architecture": ArchitectureElement.unscoped.filter(
            artifact__workspace_id=workspace_id
        ).count(),
        "test_cases": TestCase.unscoped.filter(
            artifact__workspace_id=workspace_id
        ).count(),
        "test_runs": TestRun.unscoped.filter(workspace_id=workspace_id).count(),
        "baselines": BaselineSnapshot.unscoped.filter(
            workspace_id=workspace_id
        ).count(),
        "change_requests": ChangeRequest.unscoped.filter(
            workspace_id=workspace_id
        ).count(),
        "affected_items": ChangeRequestAffectedItem.unscoped.filter(
            change_request__workspace_id=workspace_id
        ).count(),
    }


def test_fixture_meets_the_documented_minimum_counts(seeded):
    """AC-272-F1."""
    counts = _counts(seeded.id)

    assert counts["needs"] >= 4
    assert counts["goals"] >= 3
    assert counts["requirements"] >= 24
    assert counts["architecture"] >= 8
    assert counts["test_cases"] >= 12
    assert counts["test_runs"] >= 3
    assert counts["baselines"] >= 1
    assert counts["change_requests"] >= 1
    assert counts["affected_items"] >= 2


def test_fixture_mix_of_scenario_kinds_and_authorship(seeded):
    """8 nominal / 4 off-nominal, all human-authored and reviewed (producer P6)."""
    cases = list(
        TestCase.unscoped.filter(artifact__workspace_id=seeded.id).values(
            "origin", "reviewed", "scenario_kind"
        )
    )
    assert sum(1 for c in cases if c["scenario_kind"] == "off_nominal") == 4
    assert sum(1 for c in cases if c["scenario_kind"] == "nominal") == 8
    assert all(c["origin"] == "manual" for c in cases)
    assert all(c["reviewed"] is True for c in cases)


def test_fixture_is_idempotent(seeded):
    """AC-272-F2."""
    from django.core.management import call_command

    before = _counts(seeded.id)
    call_command("seed_full_chain", verbosity=0)
    TenantContext.set_tenant(seeded.tenant_id)
    after = _counts(seeded.id)

    assert Workspace.unscoped.filter(name="SysEng Full-Chain Demo").count() == 1
    assert before == after


def test_fixture_has_no_val_p1_findings(seeded):
    """AC-272-F4 (first half): the golden path satisfies VAL-P1."""
    from traceability.audit import RuleEngine
    from traceability.audit.registry import VAL_P1

    TenantContext.set_tenant(seeded.tenant_id)
    result = RuleEngine().run(
        tier="extended",
        workspace_id=str(seeded.id),
        tenant_id=str(seeded.tenant_id),
    )
    try:
        assert [f for f in result.findings if f.rule_id == VAL_P1] == []
    finally:
        TenantContext.clear_tenant()


def test_fixture_requirements_pass_the_approval_field_gate(seeded):
    """AC-272-F4 (second half): no Requirement is missing a mandatory field."""
    from workflow.precondition_rules import check_mandatory_fields

    TenantContext.set_tenant(seeded.tenant_id)
    try:
        requirements = list(
            Requirement.unscoped.filter(artifact__workspace_id=seeded.id)
        )
        assert requirements
        for requirement in requirements:
            error = check_mandatory_fields(
                item_type="Requirement",
                item_id=requirement.id,
                target_state="approved",
                workspace_id=str(seeded.id),
                change_reason="Fixture-Freigabe",
            )
            assert error is None, (requirement.title, error)
    finally:
        TenantContext.clear_tenant()


def test_fixture_chain_is_connected(seeded):
    """The links that make the report and the auditor meaningful."""
    from persistence.models import TestCase as _TestCase
    from persistence.models import TraceLink

    TenantContext.set_tenant(seeded.tenant_id)
    try:
        links = list(
            TraceLink.unscoped.filter(tenant_id=seeded.tenant_id).values(
                "link_type", "source_id", "target_id"
            )
        )
        by_type: dict[str, int] = {}
        for link in links:
            by_type[link["link_type"]] = by_type.get(link["link_type"], 0) + 1

        assert by_type.get("derives-from", 0) >= 24
        assert by_type.get("allocated-to", 0) >= 24
        assert by_type.get("verifies", 0) == 12
        assert by_type.get("decomposes", 0) == 7
        assert by_type.get("satisfies", 0) >= 16

        # Every test case verifies a distinct leaf requirement.
        verified_targets = {
            link["target_id"] for link in links if link["link_type"] == "verifies"
        }
        assert len(verified_targets) == 12

        assert Artifact.unscoped.filter(workspace_id=seeded.id).count() > 0
        assert _TestCase.unscoped.filter(artifact__workspace_id=seeded.id).count() == 12
    finally:
        TenantContext.clear_tenant()
