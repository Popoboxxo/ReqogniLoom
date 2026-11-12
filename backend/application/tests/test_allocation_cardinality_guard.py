"""D9 switch guard: a workspace cannot go back to ``single`` with live conflicts."""

from __future__ import annotations

import pytest

from application.base import AllocationConflictError
from application.preference_service import PreferenceService
from auth_tenancy.context import AuthContext
from persistence.models import (
    Allocation,
    AllocationStatus,
    Artifact,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Cardinality Guard Tenant", slug="card-guard")


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
        username="card-guard-user", email="card@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return Workspace.objects.create(tenant=tenant, name="Card-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("admin",),
        auth_method="test",
        api_key_id=None,
    )


def _multi_allocate(tenant: Tenant, workspace: Workspace) -> None:
    requirement = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    for index in range(2):
        element = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        Allocation.objects.create(
            tenant=tenant,
            workspace=workspace,
            requirement_artifact=requirement,
            element_artifact=element,
            status=AllocationStatus.DRAFT,
            is_primary=index == 0,
        )


def _set(service: PreferenceService, ctx: AuthContext, workspace: Workspace, value: str):
    return service.set_level(
        ctx,
        scope="workspace",
        workspace_id=workspace.id,
        values={"allocation.cardinality": value},
    )


def test_multiple_can_be_enabled_on_a_clean_workspace(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    result = _set(PreferenceService(), ctx, workspace, "multiple")

    assert result["values"]["allocation.cardinality"] == "multiple"


def test_switching_back_to_single_is_refused_with_the_conflict_count(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    service = PreferenceService()
    _set(service, ctx, workspace, "multiple")
    _multi_allocate(tenant, workspace)

    with pytest.raises(AllocationConflictError) as excinfo:
        _set(service, ctx, workspace, "single")

    assert "1 requirement(s)" in str(excinfo.value)


def test_switching_back_works_once_the_extra_allocation_is_withdrawn(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    service = PreferenceService()
    _set(service, ctx, workspace, "multiple")
    _multi_allocate(tenant, workspace)

    Allocation.objects.filter(
        workspace=workspace,
        status=AllocationStatus.DRAFT,
        is_primary=False,
    ).update(status=AllocationStatus.REVOKED)

    result = _set(service, ctx, workspace, "single")

    assert result["values"]["allocation.cardinality"] == "single"
