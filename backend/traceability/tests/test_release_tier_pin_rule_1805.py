"""#1805 — ``REL-P1``: a released Requirement's live tier vs. its released pin.

ADR-028 D11 pins ``Requirement.released_tier_key`` at release time and the
baseline capture reads the pin. The live ``tier_key`` keeps being recomputed, so
a re-allocation after the release makes the two disagree. The rule reports that
divergence; these tests pin the population (released + divergent), the
NULL-handling (never released = silent, unresolved live tier = reported), the
tenant/workspace isolation, the message content and the per-tier severity.
"""
from __future__ import annotations

import pytest

from persistence.models import (
    Allocation,
    AllocationStatus,
    Artifact,
    LifecycleStatus,
    Requirement,
    Tenant,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.audit import RuleEngine
from traceability.audit.registry import REL_P1, active_rule_ids_for_tier
from traceability.audit.rules.release_tier_pin import ReleaseTierPinDivergenceRule
from traceability.audit.types import AuditContext, Severity
from traceability.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Release Pin Tenant", slug="rel-pin")


@pytest.fixture(autouse=True)
def _tenant_context(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return Workspace.objects.create(tenant=tenant, name="Pin-WS")


def _requirement(
    tenant: Tenant,
    workspace: Workspace,
    *,
    live: str | None,
    pinned: str | None,
    title: str = "Requirement",
) -> tuple[Artifact, Requirement]:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    requirement = Requirement.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact=artifact,
        title=title,
        tier_key=live,
        released_tier_key=pinned,
    )
    return artifact, requirement


def _allocate(
    tenant: Tenant,
    workspace: Workspace,
    requirement_artifact: Artifact,
    *,
    primary: bool = True,
    status: str = AllocationStatus.RELEASED,
) -> Artifact:
    element_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    Allocation.objects.create(
        tenant=tenant,
        workspace=workspace,
        requirement_artifact=requirement_artifact,
        element_artifact=element_artifact,
        status=status,
        is_primary=primary,
    )
    return element_artifact


def _context(tenant: Tenant, workspace: Workspace, *, tier: str = "extended"):
    return AuditContext(
        tier=tier,
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
    )


def _run_rule(tenant: Tenant, workspace: Workspace, *, tier: str = "extended"):
    return ReleaseTierPinDivergenceRule().check(
        _context(tenant, workspace, tier=tier)
    )


def _engine(tier: str, tenant: Tenant, workspace: Workspace):
    return RuleEngine().run(
        tier=tier,
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
    )


# ---------------------------------------------------------------------------
# Population: released + divergent -> exactly one finding
# ---------------------------------------------------------------------------


def test_a_divergent_pin_is_reported_once_with_both_tiers(
    tenant: Tenant, workspace: Workspace
) -> None:
    artifact, requirement = _requirement(
        tenant, workspace, live="L2", pinned="L1", title="Brake controller"
    )

    findings = _run_rule(tenant, workspace)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == REL_P1
    assert str(artifact.id) in finding.artifact_ids
    # The message has to name both values, otherwise the reader cannot tell
    # which side moved.
    assert "'L1'" in finding.message
    assert "'L2'" in finding.message
    # The uid is the readable identifier a reviewer can search for.
    assert requirement.uid in finding.message


def test_the_driving_allocation_is_named(
    tenant: Tenant, workspace: Workspace
) -> None:
    artifact, _ = _requirement(tenant, workspace, live="L3", pinned="L2")
    element_artifact = _allocate(tenant, workspace, artifact, primary=True)
    # A second, non-leading allocation must not replace the leading one in the
    # message (ADR-028 D9: only `is_primary` decides the tier).
    _allocate(tenant, workspace, artifact, primary=False)

    findings = _run_rule(tenant, workspace)

    assert len(findings) == 1
    assert str(element_artifact.id) in findings[0].message
    assert "leading allocation" in findings[0].message
    assert "non-leading allocation" not in findings[0].message


def test_a_requirement_without_an_active_allocation_is_still_reported(
    tenant: Tenant, workspace: Workspace
) -> None:
    """The pin survives a revoked allocation: that is exactly the case where
    the live tier goes unresolved while the release still claims a level."""
    artifact, _ = _requirement(tenant, workspace, live=None, pinned="L1")
    _allocate(tenant, workspace, artifact, status=AllocationStatus.REVOKED)

    findings = _run_rule(tenant, workspace)

    assert len(findings) == 1
    # NULL is spelled out instead of leaking "None" into the report.
    assert "unresolved (NULL)" in findings[0].message
    assert "no active allocation" in findings[0].message


# ---------------------------------------------------------------------------
# Negative cases: the rule must not fire outside its population
# ---------------------------------------------------------------------------


def test_matching_pin_and_live_tier_is_not_reported(
    tenant: Tenant, workspace: Workspace
) -> None:
    _requirement(tenant, workspace, live="L2", pinned="L2")

    assert _run_rule(tenant, workspace) == []


def test_a_never_released_requirement_is_not_reported(
    tenant: Tenant, workspace: Workspace
) -> None:
    _requirement(tenant, workspace, live="L2", pinned=None)
    _requirement(tenant, workspace, live=None, pinned=None)

    assert _run_rule(tenant, workspace) == []


def test_another_workspace_is_not_reported(
    tenant: Tenant, workspace: Workspace
) -> None:
    other = Workspace.objects.create(tenant=tenant, name="Other-WS")
    _requirement(tenant, other, live="L3", pinned="L1")

    assert _run_rule(tenant, workspace) == []


def test_another_tenant_is_not_reported(tenant: Tenant, workspace: Workspace) -> None:
    other_tenant = Tenant.objects.create(name="Other", slug="rel-pin-other")
    with active_tenant(other_tenant):
        other_workspace = Workspace.objects.create(
            tenant=other_tenant, name="Other-Tenant-WS"
        )
        _requirement(other_tenant, other_workspace, live="L3", pinned="L1")

    assert _run_rule(tenant, workspace) == []


def test_a_soft_deleted_requirement_is_not_reported(
    tenant: Tenant, workspace: Workspace
) -> None:
    """Archived requirements stay out of every other list, so the audit must not
    resurrect them (``outdated_item_ids`` convention)."""
    artifact, _ = _requirement(tenant, workspace, live="L3", pinned="L1")
    Artifact.objects.filter(id=artifact.id).update(
        lifecycle_status=LifecycleStatus.OUTDATED
    )

    assert _run_rule(tenant, workspace) == []


def test_the_workspace_filter_uses_the_artifact_not_the_denormalized_copy(
    tenant: Tenant, workspace: Workspace
) -> None:
    """``Requirement.workspace_id`` is a denormalized, nullable copy (#133); the
    artifact relation is authoritative, so a NULL copy must still be found."""
    _, requirement = _requirement(tenant, workspace, live="L3", pinned="L1")
    Requirement.objects.filter(id=requirement.id).update(workspace=None)

    findings = _run_rule(tenant, workspace)

    assert len(findings) == 1


# ---------------------------------------------------------------------------
# Severity per rigor tier
# ---------------------------------------------------------------------------


class TestSeverityPerTier:
    def test_extended_is_a_blocker(self) -> None:
        assert (
            ReleaseTierPinDivergenceRule().severity_for_tier("extended")
            is Severity.BLOCKER
        )

    def test_standard_is_a_warning(self) -> None:
        assert (
            ReleaseTierPinDivergenceRule().severity_for_tier("standard")
            is Severity.WARNING
        )

    def test_the_rule_runs_at_standard_and_extended_but_not_at_minimal(
        self,
    ) -> None:
        assert REL_P1 in active_rule_ids_for_tier("standard")
        assert REL_P1 in active_rule_ids_for_tier("extended")
        # Minimal is empty by construction — the third level the issue names
        # ("info") is unreachable, which is why the rule has no minimal branch.
        assert REL_P1 not in active_rule_ids_for_tier("minimal")

    def test_the_engine_stamps_the_tier_severity(
        self, tenant: Tenant, workspace: Workspace
    ) -> None:
        _requirement(tenant, workspace, live="L3", pinned="L1")

        extended = [
            f for f in _engine("extended", tenant, workspace).findings
            if f.rule_id == REL_P1
        ]
        standard = [
            f for f in _engine("standard", tenant, workspace).findings
            if f.rule_id == REL_P1
        ]

        assert len(extended) == 1
        assert extended[0].severity is Severity.BLOCKER
        assert len(standard) == 1
        assert standard[0].severity is Severity.WARNING

    def test_minimal_runs_no_findings_at_all(
        self, tenant: Tenant, workspace: Workspace
    ) -> None:
        _requirement(tenant, workspace, live="L3", pinned="L1")

        assert _engine("minimal", tenant, workspace).findings == []
