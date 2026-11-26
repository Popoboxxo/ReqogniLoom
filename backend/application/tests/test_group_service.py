"""P6.1/P6.2: group artifact and ordered membership."""
from __future__ import annotations

import pytest

from application.base import PermissionDeniedError
from application.group_service import GroupService
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)

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


# ---------------------------------------------------------------------------
# Workspace boundary (review finding 2026-11-25, MAJOR)
# ---------------------------------------------------------------------------
#
# The membership row is a ``grouped-in`` TraceLink with no workspace column of
# its own, so the service — not the schema — has to keep a requirement of
# workspace B out of a group of workspace A. These tests pin that on all three
# mutating paths, and pin that the same-workspace path still works.


def _foreign_requirement(tenant, title):
    """A requirement in a SECOND workspace of the same tenant."""
    set_request_tenant(tenant.id)
    try:
        other = Workspace.objects.create(tenant=tenant, name=f"other-{title}")
        provision_workspace_link_types(
            workspace_id=other.id, tenant_id=tenant.id
        )
    finally:
        clear_request_tenant()
    return other, _requirement(tenant, other, title)


def _member_links(group):
    return TraceLink.unscoped.filter(
        target_id=group.id, link_type="grouped-in"
    ).count()


def test_add_member_rejects_a_requirement_from_another_workspace():
    tenant, workspace, ctx = _env("group-xws-add")
    service = GroupService()
    group = service.create(workspace.id, "Group A", ctx)
    _other, foreign = _foreign_requirement(tenant, "Foreign")

    with pytest.raises(PermissionDeniedError):
        service.add_member(group.id, foreign.id, ctx)

    # Nothing was written: no membership row for the foreign requirement.
    assert _member_links(group) == 0
    assert service.members(group.id, ctx) == []


def test_move_member_rejects_a_requirement_from_another_workspace():
    """A foreign requirement cannot be reordered — and cannot be read either.

    ``move_member`` would otherwise report NOT_FOUND for the foreign id (it is
    not a member), which is the workaround-free behaviour; the point here is
    that it raises the workspace error *before* touching ``sort_key`` and that
    no membership row appears.
    """
    tenant, workspace, ctx = _env("group-xws-move")
    service = GroupService()
    group = service.create(workspace.id, "Group A", ctx)
    _other, foreign = _foreign_requirement(tenant, "ForeignMove")

    with pytest.raises(PermissionDeniedError):
        service.move_member(group.id, foreign.id, ctx)

    assert _member_links(group) == 0


def test_remove_member_rejects_a_requirement_from_another_workspace():
    """A foreign requirement cannot be used to delete rows in this group.

    The delete is keyed on ``(requirement_artifact_id, group.id)``, so it can
    only ever match a row that is not there. The check runs first anyway: an
    editor of workspace A must not be able to address workspace B's objects
    through this service, and a future relaxation of the query must not turn
    that into a silent cross-workspace delete.
    """
    tenant, workspace, ctx = _env("group-xws-remove")
    service = GroupService()
    group = service.create(workspace.id, "Group A", ctx)
    member = _requirement(tenant, workspace, "Home")
    service.add_member(group.id, member.id, ctx)
    _other, foreign = _foreign_requirement(tenant, "ForeignRemove")

    with pytest.raises(PermissionDeniedError):
        service.remove_member(group.id, foreign.id, ctx)

    # The legitimate membership survives untouched.
    assert _member_links(group) == 1
    assert [row["requirement_artifact_id"] for row in service.members(group.id, ctx)] == [
        str(member.artifact_id)
    ]


def test_same_workspace_membership_still_works_after_the_check():
    """Positive control: the new guard must not narrow the legitimate path."""
    tenant, workspace, ctx = _env("group-xws-ok")
    service = GroupService()
    group = service.create(workspace.id, "Group A", ctx)
    member = _requirement(tenant, workspace, "Home")

    link = service.add_member(group.id, member.id, ctx)

    assert link.link_type == "grouped-in"
    assert _member_links(group) == 1
    service.move_member(group.id, member.id, ctx)
    service.remove_member(group.id, member.id, ctx)
    assert _member_links(group) == 0
