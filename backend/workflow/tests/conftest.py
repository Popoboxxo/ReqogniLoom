import uuid

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    """Avoid TenantContext bleed between tests (REQ-L3-PL002-002)."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Outdate Test Tenant", slug="outdate-test-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="Outdate Test Workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def auth_ctx(tenant):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )


@pytest.fixture
def requirement_with_workflow(db, tenant, workspace, auth_ctx):
    """Create a Requirement with an initialised WorkflowItemState ("draft").

    Uses RequirementService.create_requirement (not a raw Requirement.objects
    .create) because Requirement has no workspace_id field of its own — the
    workspace link lives on the backing Artifact — and because the workflow
    state must actually be initialised for force_transition() to find a row
    to lock.
    """
    from application.requirement_service import RequirementService

    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )

        service = RequirementService()
        requirement = service.create_requirement(
            workspace_id=workspace.id,
            title="Test Req",
            ctx=auth_ctx,
        )
    finally:
        TenantContext.clear_tenant()
    return requirement.id, workspace.id
