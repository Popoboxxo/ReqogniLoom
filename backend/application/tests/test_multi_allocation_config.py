"""ADR-028 D9: configurable multi-allocation.

Two layers are pinned here:

* the service paths (``single`` refuses a second allocation, ``multiple``
  allows it and marks the first one as leading),
* the pure tier resolver (a leading edge decides the tier, two without one
  leave it unresolved).
"""

from __future__ import annotations

import uuid

import pytest

from application.tier_compute import _derive_tiers
from application.tier_ladder_service import TierLadder
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from auth_tenancy.models import PreferenceValue
from persistence.models import (
    Allocation,
    AllocationStatus,
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Multi Alloc Tenant", slug="multi-alloc")


@pytest.fixture(autouse=True)
def _tenant_context(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="multi-alloc-user", email="multi@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    from link_types.workspace_store import provision_workspace_link_types

    workspace = Workspace.objects.create(tenant=tenant, name="Multi-WS")
    provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    return workspace


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("admin",),
        auth_method="test",
        api_key_id=None,
    )


def _requirement(tenant: Tenant, workspace: Workspace) -> Requirement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant, workspace=workspace, artifact=artifact, title="R", type="SyReq"
    )


def _element(tenant: Tenant, workspace: Workspace, title: str) -> ArchitectureElement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    return ArchitectureElement.objects.create(
        tenant=tenant, workspace=workspace, artifact=artifact, title=title
    )


def _set_cardinality(tenant: Tenant, workspace: Workspace, value: str) -> None:
    PreferenceValue.objects.create(
        tenant=tenant,
        scope="workspace",
        workspace=workspace,
        key="allocation.cardinality",
        value=value,
    )


def test_single_is_the_default_and_refuses_a_second_allocation(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    from application.base import AllocationConflictError

    requirement = _requirement(tenant, workspace)
    first = _element(tenant, workspace, "A")
    second = _element(tenant, workspace, "B")
    service = TraceLinkService()
    service.allocate(requirement.id, first.id, ctx)

    with pytest.raises(AllocationConflictError):
        service.allocate(requirement.id, second.id, ctx, mode="add")

    assert (
        TraceLink.objects.filter(
            source_id=requirement.artifact_id, link_type=LinkType.ALLOCATED_TO
        ).count()
        == 1
    )


def test_multiple_allows_a_second_secondary_allocation(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    _set_cardinality(tenant, workspace, "multiple")
    requirement = _requirement(tenant, workspace)
    first = _element(tenant, workspace, "A")
    second = _element(tenant, workspace, "B")
    service = TraceLinkService()
    service.allocate(requirement.id, first.id, ctx)
    service.allocate(requirement.id, second.id, ctx, mode="add")

    active = list(
        Allocation.objects.filter(
            requirement_artifact_id=requirement.artifact_id,
            status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
        )
    )
    assert len(active) == 2
    primaries = [row for row in active if row.is_primary]
    assert len(primaries) == 1
    assert primaries[0].element_artifact_id == first.artifact_id


def test_replace_still_archives_the_previous_allocation_under_multiple(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    _set_cardinality(tenant, workspace, "multiple")
    requirement = _requirement(tenant, workspace)
    first = _element(tenant, workspace, "A")
    second = _element(tenant, workspace, "B")
    service = TraceLinkService()
    service.allocate(requirement.id, first.id, ctx)
    service.allocate(requirement.id, second.id, ctx)  # default mode="replace"

    active = Allocation.objects.filter(
        requirement_artifact_id=requirement.artifact_id,
        status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
    )
    assert active.count() == 1
    assert active.first().element_artifact_id == second.artifact_id


# ---------------------------------------------------------------------------
# Pure resolver tests (no DB needed beyond the fixture's tenant context)
# ---------------------------------------------------------------------------


def _ladder() -> TierLadder:
    return TierLadder(entries=(), position_by_key={"system": 0, "component": 1})


def _requirement_row() -> dict:
    return {"tier_key": None, "level": None, "level_source": "unresolved"}


def test_leading_allocation_decides_the_tier() -> None:
    requirement_artifact = uuid.uuid4()
    first = uuid.uuid4()
    second = uuid.uuid4()
    requirements = {requirement_artifact: _requirement_row()}

    derived = _derive_tiers(
        uuid.uuid4(),
        requirements,
        _ladder(),
        {requirement_artifact: [first, second]},
        {first: "system", second: "component"},
        {},
        {requirement_artifact: second},
    )

    assert derived[requirement_artifact] == ("component", 2, "derived_allocation")


def test_two_allocations_without_a_leading_edge_stay_unresolved() -> None:
    requirement_artifact = uuid.uuid4()
    first = uuid.uuid4()
    second = uuid.uuid4()
    requirements = {requirement_artifact: _requirement_row()}

    derived = _derive_tiers(
        uuid.uuid4(),
        requirements,
        _ladder(),
        {requirement_artifact: [first, second]},
        {first: "system", second: "component"},
        {},
        {},
    )

    assert derived[requirement_artifact] == (None, None, "unresolved")


def test_a_single_allocation_needs_no_primary_flag() -> None:
    requirement_artifact = uuid.uuid4()
    only = uuid.uuid4()
    requirements = {requirement_artifact: _requirement_row()}

    derived = _derive_tiers(
        uuid.uuid4(),
        requirements,
        _ladder(),
        {requirement_artifact: [only]},
        {only: "system"},
        {},
        {},
    )

    assert derived[requirement_artifact] == ("system", 1, "derived_allocation")
