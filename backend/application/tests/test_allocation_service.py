"""P2: N:1 allocation, one write service, allocation_intent."""
from __future__ import annotations

import pytest
from django.db import IntegrityError

from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    AllocationIntent,
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)

pytestmark = pytest.mark.django_db


def _env(slug="alloc-p2"):
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
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )
    return tenant, workspace, ctx


def _requirement(tenant, workspace, title="Req"):
    artifact = Artifact.unscoped.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement", sort_key="a0"
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=f"R-{title}",
    )


def _element(tenant, workspace, title="El", parent=None, uid=None):
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
        title=title,
        uid=uid or f"E-{title}",
        parent=parent,
    )


def test_second_allocated_to_edge_is_rejected_by_the_service_not_the_db():
    """ADR-028 D9: the cardinality is a per-workspace setting, not a DB rule.

    The edge table therefore accepts a second allocation; the service rejects
    it under the default ``single``. (Migration 0142 removed the old unique
    constraint for exactly this reason.)
    """
    from application.base import AllocationConflictError

    tenant, workspace, ctx = _env("alloc-unique")
    req = _requirement(tenant, workspace)
    first = _element(tenant, workspace, "First")
    second = _element(tenant, workspace, "Second")

    TraceLink.unscoped.create(
        tenant=tenant,
        source_id=req.artifact_id,
        target_id=first.artifact_id,
        link_type="allocated-to",
    )
    # The DB accepts it now; the application layer is the authority.
    TraceLink.unscoped.create(
        tenant=tenant,
        source_id=req.artifact_id,
        target_id=second.artifact_id,
        link_type="allocated-to",
    )

    with pytest.raises(AllocationConflictError):
        TraceLinkService().allocate(req.id, second.id, ctx, mode="add")


def test_allocate_replaces_and_sets_intent():
    tenant, workspace, ctx = _env("alloc-replace")
    req = _requirement(tenant, workspace)
    first = _element(tenant, workspace, "First")
    second = _element(tenant, workspace, "Second")
    service = TraceLinkService()

    service.allocate(
        requirement_id=req.id, architecture_element_id=first.id, ctx=ctx
    )
    service.allocate(
        requirement_id=req.id, architecture_element_id=second.id, ctx=ctx
    )

    edges = list(
        TraceLink.unscoped.filter(
            source_id=req.artifact_id, link_type="allocated-to"
        )
    )
    assert len(edges) == 1
    assert edges[0].target_id == second.artifact_id
    assert (
        Requirement.unscoped.get(pk=req.pk).allocation_intent
        == AllocationIntent.ALLOCATED
    )


def test_generic_second_target_is_conflict():
    tenant, workspace, ctx = _env("alloc-generic")
    req = _requirement(tenant, workspace)
    first = _element(tenant, workspace, "First")
    second = _element(tenant, workspace, "Second")
    service = TraceLinkService()
    service.allocate(
        requirement_id=req.id, architecture_element_id=first.id, ctx=ctx
    )

    from application.base import AllocationConflictError

    with pytest.raises(AllocationConflictError):
        service.create_trace_link(
            source_id=req.id,
            target_id=second.id,
            link_type="allocated-to",
            ctx=ctx,
        )


def test_deallocate_removes_edge_and_resets_intent():
    tenant, workspace, ctx = _env("alloc-dealloc")
    req = _requirement(tenant, workspace)
    element = _element(tenant, workspace)
    service = TraceLinkService()
    service.allocate(
        requirement_id=req.id, architecture_element_id=element.id, ctx=ctx
    )

    service.deallocate(requirement_id=req.id, ctx=ctx)

    assert not TraceLink.unscoped.filter(
        source_id=req.artifact_id, link_type="allocated-to"
    ).exists()
    assert (
        Requirement.unscoped.get(pk=req.pk).allocation_intent
        == AllocationIntent.UNASSIGNED
    )


def test_not_allocatable_requires_no_edge():
    from application.base import ValidationError
    from application.requirement_service import RequirementService

    tenant, workspace, ctx = _env("alloc-intent")
    req = _requirement(tenant, workspace)
    element = _element(tenant, workspace)
    service = TraceLinkService()
    service.allocate(
        requirement_id=req.id, architecture_element_id=element.id, ctx=ctx
    )

    with pytest.raises(ValidationError):
        RequirementService().update_requirement(
            requirement_id=req.id,
            ctx=ctx,
            allocation_intent=AllocationIntent.NOT_ALLOCATABLE,
        )
