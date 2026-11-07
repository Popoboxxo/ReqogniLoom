"""P6.1/P6.2: group artifact and ordered membership."""
from __future__ import annotations

import pytest

from application.group_service import GroupService
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _env(slug="group-p6"):
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


def _requirement(tenant, workspace, title):
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


def test_membership_order_and_multi_group():
    tenant, workspace, ctx = _env()
    service = GroupService()
    first = _requirement(tenant, workspace, "First")
    second = _requirement(tenant, workspace, "Second")
    group_a = service.create(workspace.id, "Group A", ctx)
    group_b = service.create(workspace.id, "Group B", ctx)

    service.add_member(group_a.id, second.id, ctx)
    service.add_member(group_a.id, first.id, ctx)
    service.add_member(group_b.id, first.id, ctx)

    order = [row["requirement_artifact_id"] for row in service.members(group_a.id, ctx)]
    assert order == [str(second.artifact_id), str(first.artifact_id)]
    assert len(service.members(group_b.id, ctx)) == 1


def test_move_member_reorders_without_touching_tiers():
    tenant, workspace, ctx = _env("group-move")
    service = GroupService()
    first = _requirement(tenant, workspace, "First")
    second = _requirement(tenant, workspace, "Second")
    group = service.create(workspace.id, "Group", ctx)
    service.add_member(group.id, first.id, ctx)
    service.add_member(group.id, second.id, ctx)

    Requirement.unscoped.filter(pk=first.pk).update(
        tier_key="dazwischen", level=2, allocation_intent="allocated"
    )
    links = service.members(group.id, ctx)
    service.move_member(group.id, first.id, ctx, after_id=links[1]["trace_link_id"])

    order = [row["requirement_artifact_id"] for row in service.members(group.id, ctx)]
    assert order == [str(second.artifact_id), str(first.artifact_id)]
    row = Requirement.unscoped.get(pk=first.pk)
    assert (row.tier_key, row.level, row.allocation_intent) == (
        "dazwischen",
        2,
        "allocated",
    )
