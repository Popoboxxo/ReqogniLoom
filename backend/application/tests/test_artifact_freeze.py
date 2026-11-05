"""P4: workflow-driven freeze for move and allocation."""
from __future__ import annotations

import pytest

from application.artifact_freeze import is_frozen
from application.artifact_service import ArtifactService
from application.base import WorkflowFrozenError
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from workflow.models import WorkflowEngineDefinition, WorkflowItemState

pytestmark = pytest.mark.django_db


def _env(slug="freeze-p4"):
    tenant = Tenant.objects.create(name=slug, slug=slug)
    user = User.objects.create(
        username=f"{slug}-user", email=f"{slug}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id, tenant_id=tenant.id, active_roles=("editor",), auth_method="test"
    )
    return tenant, workspace, ctx


def _definition(tenant, workspace, item_type="Requirement"):
    return WorkflowEngineDefinition.unscoped.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type=item_type,
        preset="standard",
        workflow_json={
            "states": ["draft", "frozen"],
            "transitions": [],
            "state_meta": {"frozen": {"freeze_on_enter": True}},
        },
    )


def _requirement(tenant, workspace):
    artifact = Artifact.unscoped.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement", sort_key="a0"
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="Req",
        uid="R-FREEZE",
    )


def _element(tenant, workspace):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="ArchitectureElement",
        sort_key="a0",
    )
    return ArchitectureElement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="El",
        uid="E-FREEZE",
    )


def _freeze(tenant, workspace, item_id, item_type="Requirement"):
    definition = _definition(tenant, workspace, item_type)
    WorkflowItemState.unscoped.create(
        tenant=tenant,
        item_id=item_id,
        item_type=item_type,
        workspace_id=workspace.id,
        definition=definition,
        current_state="frozen",
    )


def test_frozen_requirement_cannot_move_or_allocate():
    tenant, workspace, ctx = _env()
    req = _requirement(tenant, workspace)
    element = _element(tenant, workspace)
    _freeze(tenant, workspace, req.id)

    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant.id)
    try:
        info = is_frozen(req.artifact)
        assert info is not None and info.state_name == "frozen"

        with pytest.raises(WorkflowFrozenError):
            ArtifactService().move(
                artifact_id=req.artifact_id,
                new_parent_id=None,
                ctx=ctx,
            )
        with pytest.raises(WorkflowFrozenError):
            TraceLinkService().allocate(
                requirement_id=req.id,
                architecture_element_id=element.id,
                ctx=ctx,
            )
    finally:
        TenantContext.clear_tenant()


def test_frozen_element_still_accepts_allocation():
    tenant, workspace, ctx = _env("freeze-target")
    req = _requirement(tenant, workspace)
    element = _element(tenant, workspace)
    _freeze(tenant, workspace, element.id, item_type="ArchitectureElement")

    link = TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=element.id, ctx=ctx
    )

    assert link.target_id == element.artifact_id


def test_unfrozen_requirement_is_writable():
    tenant, workspace, ctx = _env("freeze-open")
    req = _requirement(tenant, workspace)

    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant.id)
    try:
        assert is_frozen(req.artifact) is None
    finally:
        TenantContext.clear_tenant()
