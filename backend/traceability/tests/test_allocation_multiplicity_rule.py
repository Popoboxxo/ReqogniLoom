"""ALLOC-P1: multiple active allocations are reported (ADR-028 D9)."""

from __future__ import annotations

import pytest

from auth_tenancy.models import PreferenceValue
from persistence.models import (
    Allocation,
    AllocationStatus,
    Artifact,
    Tenant,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.audit.rules.allocation_multiplicity import AllocationMultiplicityRule
from traceability.audit.types import AuditContext, Severity

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Alloc Rule Tenant", slug="alloc-rule")


@pytest.fixture(autouse=True)
def _tenant_context(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return Workspace.objects.create(tenant=tenant, name="Rule-WS")


def _artifact(tenant: Tenant, workspace: Workspace) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )


def _allocation(
    tenant: Tenant,
    workspace: Workspace,
    requirement_artifact: Artifact,
    element_artifact: Artifact,
    *,
    primary: bool,
) -> Allocation:
    return Allocation.objects.create(
        tenant=tenant,
        workspace=workspace,
        requirement_artifact=requirement_artifact,
        element_artifact=element_artifact,
        status=AllocationStatus.DRAFT,
        is_primary=primary,
    )


def _context(tenant: Tenant, workspace: Workspace) -> AuditContext:
    return AuditContext(
        tier="standard",
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
    )


def _set_severity(tenant: Tenant, workspace: Workspace, value: str) -> None:
    PreferenceValue.objects.create(
        tenant=tenant,
        scope="workspace",
        workspace=workspace,
        key="allocation.conflict_severity",
        value=value,
    )


def test_a_single_allocation_is_not_reported(
    tenant: Tenant, workspace: Workspace
) -> None:
    requirement = _artifact(tenant, workspace)
    element = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    _allocation(tenant, workspace, requirement, element, primary=True)

    findings = AllocationMultiplicityRule().check(_context(tenant, workspace))

    assert findings == []


def test_two_allocations_are_reported_once(
    tenant: Tenant, workspace: Workspace
) -> None:
    requirement = _artifact(tenant, workspace)
    first = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    second = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    _allocation(tenant, workspace, requirement, first, primary=True)
    _allocation(tenant, workspace, requirement, second, primary=False)

    findings = AllocationMultiplicityRule().check(_context(tenant, workspace))

    assert len(findings) == 1
    assert findings[0].rule_id == "ALLOC-P1"
    assert findings[0].severity == Severity.WARNING
    assert str(requirement.id) in findings[0].artifact_ids
    assert "2 active allocations" in findings[0].message


def test_the_workspace_severity_raises_the_finding_to_a_blocker(
    tenant: Tenant, workspace: Workspace
) -> None:
    _set_severity(tenant, workspace, "blocker")
    requirement = _artifact(tenant, workspace)
    for _ in range(2):
        element = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        _allocation(tenant, workspace, requirement, element, primary=False)

    findings = AllocationMultiplicityRule().check(_context(tenant, workspace))

    assert len(findings) == 1
    assert findings[0].severity == Severity.BLOCKER


def test_info_stays_a_warning_because_the_vocabulary_has_two_levels(
    tenant: Tenant, workspace: Workspace
) -> None:
    _set_severity(tenant, workspace, "info")
    requirement = _artifact(tenant, workspace)
    for _ in range(2):
        element = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        _allocation(tenant, workspace, requirement, element, primary=False)

    findings = AllocationMultiplicityRule().check(_context(tenant, workspace))

    assert findings[0].severity == Severity.WARNING
    assert "configured severity=info" in findings[0].message
