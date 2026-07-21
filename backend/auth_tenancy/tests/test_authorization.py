"""
COMP-AT-002 AuthorizationService — tests.

Covers REQ-L3-AT002-001 (RBAC allow/deny per role), REQ-L3-AT002-002 (Approver
preset restriction + suspension) and REQ-L3-AT002-003 (admin-guarded assignment).
"""
from __future__ import annotations

import pytest

from auth_tenancy.errors import PermissionDenied
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from auth_tenancy.services.authorization import (
    AuthorizationService,
    Operation,
    PresetPolicyValidator,
)
from persistence.models import User

from .conftest import active_tenant


# -- REQ-L3-AT002-001 RBAC matrix -----------------------------------------


def test_viewer_can_read_but_not_write():
    svc = AuthorizationService()
    assert svc.decide_access((ROLE_VIEWER,), Operation.READ).allow is True
    assert svc.decide_access((ROLE_VIEWER,), Operation.WRITE).allow is False


def test_editor_cannot_approve():
    svc = AuthorizationService()
    assert svc.decide_access((ROLE_EDITOR,), Operation.WRITE).allow is True
    assert (
        svc.decide_access((ROLE_EDITOR,), Operation.WORKFLOW_APPROVAL).allow is False
    )


def test_approver_can_approve():
    svc = AuthorizationService()
    assert (
        svc.decide_access((ROLE_APPROVER,), Operation.WORKFLOW_APPROVAL).allow is True
    )


def test_admin_can_do_everything():
    svc = AuthorizationService()
    for op in Operation:
        assert svc.decide_access((ROLE_ADMIN,), op).allow is True


def test_enforce_raises_permission_denied_for_viewer_write():
    svc = AuthorizationService()
    with pytest.raises(PermissionDenied) as exc:
        svc.enforce((ROLE_VIEWER,), Operation.WRITE)
    assert exc.value.code == "insufficient_permissions"
    assert exc.value.status_code == 403


def test_no_roles_denies_everything():
    svc = AuthorizationService()
    assert svc.decide_access((), Operation.READ).allow is False


# -- REQ-L3-AT002-002 Approver preset restriction -------------------------


def test_approver_only_allowed_in_extended_preset():
    assert PresetPolicyValidator.is_role_allowed_in_preset(ROLE_APPROVER, "extended")
    assert not PresetPolicyValidator.is_role_allowed_in_preset(ROLE_APPROVER, "standard")
    assert not PresetPolicyValidator.is_role_allowed_in_preset(ROLE_APPROVER, "minimal")


def test_non_approver_roles_allowed_in_any_preset():
    for preset in ("minimal", "standard", "extended"):
        assert PresetPolicyValidator.is_role_allowed_in_preset(ROLE_EDITOR, preset)


@pytest.mark.django_db
def test_assign_approver_in_standard_preset_fails(tenant_a, user_a, workspace_a):
    svc = AuthorizationService()
    with active_tenant(tenant_a), pytest.raises(ValueError):
        svc.assign_role(
            actor_roles=(ROLE_ADMIN,),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_APPROVER,
            preset="standard",
            assigned_by_user_id=user_a.id,
            target_is_member=True,
        )


@pytest.mark.django_db
def test_assign_approver_in_extended_preset_ok(tenant_a, user_a, workspace_a):
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        ur = svc.assign_role(
            actor_roles=(ROLE_ADMIN,),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_APPROVER,
            preset="extended",
            assigned_by_user_id=user_a.id,
            target_is_member=True,
        )
        assert ur.role == ROLE_APPROVER
        assert ur.is_active


@pytest.mark.django_db
def test_preset_downgrade_suspends_approver(tenant_a, user_a, workspace_a):
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        svc.assign_role(
            actor_roles=(ROLE_ADMIN,),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_APPROVER,
            preset="extended",
            assigned_by_user_id=user_a.id,
            target_is_member=True,
        )
        suspended = svc.suspend_approver_assignments(workspace_id=workspace_a.id)
        assert suspended == 1
        roles = svc.active_roles_for(user_id=user_a.id, workspace_id=workspace_a.id)
        assert ROLE_APPROVER not in roles


# -- REQ-L3-AT002-003 admin guard -----------------------------------------


@pytest.mark.django_db
def test_non_admin_cannot_assign_role(tenant_a, user_a, workspace_a):
    svc = AuthorizationService()
    with active_tenant(tenant_a), pytest.raises(PermissionDenied):
        svc.assign_role(
            actor_roles=(ROLE_EDITOR,),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_EDITOR,
            preset="extended",
            assigned_by_user_id=user_a.id,
            target_is_member=True,
        )


@pytest.mark.django_db
def test_non_member_target_onboarded_by_admin(tenant_a, user_a, workspace_a):
    """SEC-05: assigning a role to a non-member is onboarding, not an error."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        ur = svc.assign_role(
            actor_roles=(ROLE_ADMIN,),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_EDITOR,
            preset="extended",
            assigned_by_user_id=user_a.id,
            target_is_member=False,
        )
        assert ur.role == ROLE_EDITOR
        assert UserRole.objects.filter(
            user_id=user_a.id, workspace_id=workspace_a.id, role=ROLE_EDITOR
        ).exists()


@pytest.mark.django_db
def test_first_admin_bootstrap_self_assignment_allowed(tenant_a, user_a, workspace_a):
    """SEC-05: a caller with no admin role anywhere may self-assign admin
    when the workspace currently has zero active admin holders."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        ur = svc.assign_role(
            actor_roles=(),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_ADMIN,
            preset="extended",
            assigned_by_user_id=user_a.id,
            target_is_member=False,
        )
        assert ur.role == ROLE_ADMIN
        assert ur.is_active


@pytest.mark.django_db
def test_bootstrap_exception_does_not_apply_once_admin_exists(
    tenant_a, user_a, workspace_a
):
    """SEC-05 bootstrap is a one-time deadlock-breaker, not a standing hole:
    once a workspace has an active admin, a non-admin caller still can't
    self-assign admin."""
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        svc.assign_role(
            actor_roles=(),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_ADMIN,
            preset="extended",
            assigned_by_user_id=user_a.id,
            target_is_member=False,
        )
        second_user = User.objects.create(
            username="carol", email="carol@a.test", tenant=tenant_a
        )
        with pytest.raises(PermissionDenied):
            svc.assign_role(
                actor_roles=(),
                target_user_id=second_user.id,
                workspace_id=workspace_a.id,
                tenant_id=tenant_a.id,
                role=ROLE_ADMIN,
                preset="extended",
                assigned_by_user_id=second_user.id,
                target_is_member=False,
            )


@pytest.mark.django_db
def test_admin_assignment_persists(tenant_a, user_a, workspace_a):
    svc = AuthorizationService()
    with active_tenant(tenant_a):
        svc.assign_role(
            actor_roles=(ROLE_ADMIN,),
            target_user_id=user_a.id,
            workspace_id=workspace_a.id,
            tenant_id=tenant_a.id,
            role=ROLE_EDITOR,
            preset="extended",
            assigned_by_user_id=user_a.id,
            target_is_member=True,
        )
        assert UserRole.objects.filter(
            user_id=user_a.id, workspace_id=workspace_a.id, role=ROLE_EDITOR
        ).exists()
