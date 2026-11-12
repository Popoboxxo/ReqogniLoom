"""ADR-028: the Allocation object stays in sync with the allocated-to edge.

These tests pin the dual-write invariant on the service paths, not on a
particular caller: allocate, generic link creation, replacement, deallocation
and generic link deletion.
"""

from __future__ import annotations

import pytest

from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
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
    return Tenant.objects.create(name="Allocation Object Tenant", slug="alloc-object")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="alloc-object-user", email="alloc@example.com", tenant=tenant
    )


@pytest.fixture(autouse=True)
def _tenant_context(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    from link_types.workspace_store import provision_workspace_link_types

    workspace = Workspace.objects.create(tenant=tenant, name="Alloc-WS")
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


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str = "R") -> Requirement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant, workspace=workspace, artifact=artifact, title=title, type="SyReq"
    )


def _make_element(tenant: Tenant, workspace: Workspace, title: str = "E") -> ArchitectureElement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    return ArchitectureElement.objects.create(
        tenant=tenant, workspace=workspace, artifact=artifact, title=title
    )


def _active(requirement: Requirement) -> list[Allocation]:
    return list(
        Allocation.objects.filter(
            requirement_artifact_id=requirement.artifact_id,
            status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
        )
    )


def test_allocate_creates_the_object_next_to_the_edge(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    TenantContext.set_tenant(tenant.id)
    requirement = _make_requirement(tenant, workspace)
    element = _make_element(tenant, workspace)

    TraceLinkService().allocate(requirement.id, element.id, ctx)

    allocations = _active(requirement)
    assert len(allocations) == 1
    assert allocations[0].element_artifact_id == element.artifact_id
    assert allocations[0].status == AllocationStatus.DRAFT
    assert allocations[0].is_primary is True
    assert allocations[0].workspace_id == workspace.id


def test_generic_link_creation_also_creates_the_object(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    TenantContext.set_tenant(tenant.id)
    requirement = _make_requirement(tenant, workspace)
    element = _make_element(tenant, workspace)

    TraceLinkService().create_trace_link(
        source_id=requirement.id,
        target_id=element.id,
        link_type=LinkType.ALLOCATED_TO.value,
        ctx=ctx,
    )

    assert len(_active(requirement)) == 1


def test_reallocation_revokes_the_previous_object(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    TenantContext.set_tenant(tenant.id)
    requirement = _make_requirement(tenant, workspace)
    first = _make_element(tenant, workspace, "A")
    second = _make_element(tenant, workspace, "B")

    service = TraceLinkService()
    service.allocate(requirement.id, first.id, ctx)
    service.allocate(requirement.id, second.id, ctx)

    active = _active(requirement)
    assert len(active) == 1
    assert active[0].element_artifact_id == second.artifact_id
    revoked = Allocation.objects.filter(
        requirement_artifact_id=requirement.artifact_id,
        status=AllocationStatus.REVOKED,
    )
    assert revoked.count() == 1
    assert revoked.first().revocation_reason


def test_deallocate_revokes_the_object(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    TenantContext.set_tenant(tenant.id)
    requirement = _make_requirement(tenant, workspace)
    element = _make_element(tenant, workspace)
    service = TraceLinkService()
    service.allocate(requirement.id, element.id, ctx)

    service.deallocate(requirement_id=requirement.id, ctx=ctx)

    assert _active(requirement) == []
    assert not TraceLink.objects.filter(
        source_id=requirement.artifact_id, link_type=LinkType.ALLOCATED_TO
    ).exists()


def test_generic_link_deletion_revokes_the_object(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    TenantContext.set_tenant(tenant.id)
    requirement = _make_requirement(tenant, workspace)
    element = _make_element(tenant, workspace)
    service = TraceLinkService()
    link = service.allocate(requirement.id, element.id, ctx)

    service.delete_trace_link(link_id=link.id, ctx=ctx)

    assert _active(requirement) == []
