"""P3 Task 3.1: the flat allocation-view read object."""
from __future__ import annotations

import pytest

from application.allocation_view_service import AllocationViewService
from application.base import ValidationError
from auth_tenancy.context import AuthContext
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


def _env(slug="alloc-view"):
    tenant = Tenant.objects.create(name=slug, slug=slug)
    user = User.objects.create(
        username=f"{slug}-user", email=f"{slug}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id, tenant_id=tenant.id, active_roles=("editor",), auth_method="test"
    )
    return tenant, workspace, ctx


def _element(tenant, workspace, title, parent=None):
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
        uid=f"E-{title}",
        parent=parent,
    )


def _requirement(tenant, workspace, title, intent="unassigned"):
    artifact = Artifact.unscoped.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement", sort_key="a0"
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=f"R-{title}",
        allocation_intent=intent,
    )


def _fixture(slug="alloc-view-fixture"):
    tenant, workspace, ctx = _env(slug)
    root = _element(tenant, workspace, "Root")
    child = _element(tenant, workspace, "Child", parent=root)
    allocated = _requirement(tenant, workspace, "Allocated", AllocationIntent.ALLOCATED)
    TraceLink.unscoped.create(
        tenant=tenant,
        source_id=allocated.artifact_id,
        target_id=child.artifact_id,
        link_type="allocated-to",
    )
    excluded = _requirement(
        tenant, workspace, "Excluded", AllocationIntent.NOT_ALLOCATABLE
    )
    return tenant, workspace, ctx, root, child, allocated, excluded


def test_rows_and_counters():
    _tenant, workspace, ctx, _root, _child, _allocated, _excluded = _fixture()

    payload = AllocationViewService().list(workspace.id, ctx)

    assert payload["meta"]["total"] == 4  # 2 requirements + 2 elements
    assert payload["meta"]["unallocated"] == 1
    assert payload["meta"]["findings"] == 0


def test_allocated_and_intent_filters():
    _tenant, workspace, ctx, _root, _child, allocated, excluded = _fixture("alloc-filters")
    service = AllocationViewService()

    only_allocated = service.list(workspace.id, ctx, allocated=True)
    assert [row["title"] for row in only_allocated["results"]] == ["Allocated"]

    excluded_rows = service.list(workspace.id, ctx, intent="not_allocatable")
    assert [row["title"] for row in excluded_rows["results"]] == ["Excluded"]
    assert excluded_rows["results"][0]["id"] == str(excluded.id)


def test_element_subtree_filter():
    _tenant, workspace, ctx, root, child, _allocated, _excluded = _fixture("alloc-subtree")

    payload = AllocationViewService().list(
        workspace.id, ctx, element_subtree=root.id
    )

    ids = {row["id"] for row in payload["results"]}
    assert str(child.id) in ids
    assert any(row["title"] == "Allocated" for row in payload["results"])


def test_page_size_cap_is_rejected():
    _tenant, workspace, ctx, *_ = _fixture("alloc-cap")
    with pytest.raises(ValidationError):
        AllocationViewService().list(workspace.id, ctx, page_size=501)
