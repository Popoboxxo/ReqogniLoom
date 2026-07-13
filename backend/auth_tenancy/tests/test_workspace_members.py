"""
Tests for AuthorizationService.list_workspace_members (REQ-014).

Covers the member-directory query that backs the Item-Permission user picker:

* Distinct members with aggregated active roles.
* Suspended assignments are excluded.
* display_name falls back to the username when no first/last name is set.
* The membership access gate (AC#1) denies non-members.
"""
from __future__ import annotations

import pytest
from django.utils import timezone

from auth_tenancy.errors import PermissionDenied
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from auth_tenancy.services import AuthorizationService
from persistence.models import User

from .conftest import active_tenant


@pytest.mark.django_db
def test_list_members_aggregates_roles_and_dedupes(tenant_a, user_a, workspace_a):
    """A user with several roles appears once with all roles aggregated."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        bob = User.objects.create(
            username="bob",
            email="bob@a.test",
            first_name="Bob",
            last_name="Builder",
            tenant=tenant_a,
        )
        UserRole.objects.create(
            tenant=tenant_a, user=user_a, workspace=workspace_a, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant_a, user=bob, workspace=workspace_a, role=ROLE_EDITOR
        )
        UserRole.objects.create(
            tenant=tenant_a, user=bob, workspace=workspace_a, role=ROLE_VIEWER
        )
        members = svc.list_workspace_members(
            caller_user_id=user_a.id, workspace_id=workspace_a.id
        )

    assert {m.user_id for m in members} == {user_a.id, bob.id}
    bob_member = next(m for m in members if m.user_id == bob.id)
    assert bob_member.roles == ("editor", "viewer")
    assert bob_member.display_name == "Bob Builder"
    assert bob_member.email == "bob@a.test"
    assert bob_member.username == "bob"


@pytest.mark.django_db
def test_list_members_display_name_falls_back_to_username(
    tenant_a, user_a, workspace_a
):
    """Alice has no first/last name, so display_name is her username."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        UserRole.objects.create(
            tenant=tenant_a, user=user_a, workspace=workspace_a, role=ROLE_ADMIN
        )
        members = svc.list_workspace_members(
            caller_user_id=user_a.id, workspace_id=workspace_a.id
        )

    alice = next(m for m in members if m.user_id == user_a.id)
    assert alice.display_name == "alice"


@pytest.mark.django_db
def test_list_members_excludes_suspended_assignments(
    tenant_a, user_a, workspace_a
):
    """A user whose only role is suspended is not a member."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        UserRole.objects.create(
            tenant=tenant_a, user=user_a, workspace=workspace_a, role=ROLE_ADMIN
        )
        carol = User.objects.create(
            username="carol", email="carol@a.test", tenant=tenant_a
        )
        UserRole.objects.create(
            tenant=tenant_a,
            user=carol,
            workspace=workspace_a,
            role=ROLE_EDITOR,
            suspended_at=timezone.now(),
        )
        members = svc.list_workspace_members(
            caller_user_id=user_a.id, workspace_id=workspace_a.id
        )

    assert {m.user_id for m in members} == {user_a.id}


@pytest.mark.django_db
def test_list_members_denies_non_member_caller(tenant_a, user_a, workspace_a):
    """AC#1: a caller without an active role in the workspace is denied."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        with pytest.raises(PermissionDenied):
            svc.list_workspace_members(
                caller_user_id=user_a.id, workspace_id=workspace_a.id
            )


@pytest.mark.django_db
def test_list_members_sorted_by_display_name(tenant_a, user_a, workspace_a):
    """Members are returned sorted case-insensitively by display name."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        UserRole.objects.create(
            tenant=tenant_a, user=user_a, workspace=workspace_a, role=ROLE_ADMIN
        )
        zoe = User.objects.create(
            username="zoe",
            email="zoe@a.test",
            first_name="Zoe",
            tenant=tenant_a,
        )
        UserRole.objects.create(
            tenant=tenant_a, user=zoe, workspace=workspace_a, role=ROLE_VIEWER
        )
        members = svc.list_workspace_members(
            caller_user_id=user_a.id, workspace_id=workspace_a.id
        )

    names = [m.display_name for m in members]
    assert names == sorted(names, key=str.lower)
    # "alice" precedes "Zoe" case-insensitively.
    assert names == ["alice", "Zoe"]
