"""
Tests for the universal outdate()/reactivate() escape hatch (Task 2, Phase 0
status-unification).

Covers:
  - outdate() transitions an item to "outdated" from any current state,
    bypassing the normal preset-transition-list validation.
  - reactivate() restores the state the item was in immediately before it was
    outdated (read from the most recent WorkflowHistoryEntry into "outdated").
  - reactivate() raises ValueError when the item is not currently outdated.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowHistoryEntry, WorkflowItemState
from workflow.services import create_default_workflow, outdate, reactivate


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


@pytest.mark.django_db
def test_outdate_transitions_from_any_current_state(requirement_with_workflow, auth_ctx):
    item_id, workspace_id = requirement_with_workflow

    # workflow.services operates on the tenant-scoped manager directly — the
    # caller (normally an application-layer service) must set TenantContext
    # before invoking any StateLifecycleManager method.
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        result = outdate(
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace_id,
            ctx=auth_ctx,
            reason="superseded by REQ-99",
        )

        assert result.new_state == "outdated"
        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert item_state.current_state == "outdated"
        history = (
            WorkflowHistoryEntry.objects.filter(item_state=item_state)
            .order_by("-transitioned_at")
            .first()
        )
        assert history.to_state == "outdated"
        assert history.change_reason == "superseded by REQ-99"
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_reactivate_restores_previous_state(requirement_with_workflow, auth_ctx):
    item_id, workspace_id = requirement_with_workflow

    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        outdate(
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace_id,
            ctx=auth_ctx,
            reason="test",
        )

        result = reactivate(
            item_id=item_id, item_type="Requirement", workspace_id=workspace_id, ctx=auth_ctx
        )

        assert result.new_state == "draft"  # the state it was in before outdate()
        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert item_state.current_state == "draft"
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_reactivate_raises_if_not_currently_outdated(requirement_with_workflow, auth_ctx):
    item_id, workspace_id = requirement_with_workflow

    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        with pytest.raises(ValueError, match="item is not outdated"):
            reactivate(
                item_id=item_id,
                item_type="Requirement",
                workspace_id=workspace_id,
                ctx=auth_ctx,
            )
    finally:
        TenantContext.clear_tenant()
