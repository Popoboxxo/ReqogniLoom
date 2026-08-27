from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest
from django.db import connection, transaction

from application.base import NotFoundError
from auth_tenancy.errors import PermissionDenied
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, TenantRole, UserRole
from auth_tenancy.services.authorization import (
    AuthorizationService,
    LastAdminError,
)
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


def _make_workspace_with_admin(username_suffix: str):
    tenant = Tenant.objects.create(name="LA-T", slug=f"la-t-{username_suffix}")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    admin = User.objects.create(
        username=f"admin-{username_suffix}", email=f"a-{username_suffix}@t.test", tenant=tenant
    )
    role = UserRole.objects.create(tenant=tenant, user=admin, workspace=ws, role=ROLE_ADMIN)
    return tenant, ws, admin, role


@pytest.mark.django_db
def test_revoke_role_blocks_removing_the_last_workspace_admin():
    tenant, ws, admin, _role = _make_workspace_with_admin("solo")
    service = AuthorizationService()

    with pytest.raises(LastAdminError):
        service.revoke_role(
            actor_roles=(ROLE_ADMIN,),
            target_user_id=admin.id,
            workspace_id=ws.id,
            role=ROLE_ADMIN,
        )
    assert UserRole.objects.filter(
        user=admin, workspace=ws, role=ROLE_ADMIN, suspended_at__isnull=True
    ).exists()


@pytest.mark.django_db
def test_revoke_role_allowed_when_another_admin_remains():
    tenant, ws, admin, _role = _make_workspace_with_admin("two-a")
    second_admin = User.objects.create(
        username="admin-two-b", email="two-b@t.test", tenant=tenant
    )
    UserRole.objects.create(tenant=tenant, user=second_admin, workspace=ws, role=ROLE_ADMIN)
    service = AuthorizationService()

    service.revoke_role(
        actor_roles=(ROLE_ADMIN,), target_user_id=admin.id, workspace_id=ws.id, role=ROLE_ADMIN
    )
    assert not UserRole.objects.filter(user=admin, workspace=ws, role=ROLE_ADMIN).exists()


@pytest.mark.django_db
def test_revoke_role_non_admin_role_never_blocked():
    tenant, ws, admin, _role = _make_workspace_with_admin("editor-ok")
    editor = User.objects.create(username="editor-x", email="editor-x@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=editor, workspace=ws, role=ROLE_EDITOR)
    service = AuthorizationService()

    service.revoke_role(
        actor_roles=(ROLE_ADMIN,), target_user_id=editor.id, workspace_id=ws.id, role=ROLE_EDITOR
    )
    assert not UserRole.objects.filter(user=editor, workspace=ws, role=ROLE_EDITOR).exists()


@pytest.mark.django_db
def test_suspend_role_blocks_suspending_the_last_workspace_admin():
    tenant, ws, admin, _role = _make_workspace_with_admin("suspend-solo")
    service = AuthorizationService()

    with pytest.raises(LastAdminError):
        service.suspend_role(
            actor_roles=(ROLE_ADMIN,),
            actor_is_tenant_admin=False,
            target_user_id=admin.id,
            workspace_id=ws.id,
            role=ROLE_ADMIN,
        )
    role = UserRole.objects.get(user=admin, workspace=ws, role=ROLE_ADMIN)
    assert role.suspended_at is None


@pytest.mark.django_db
def test_reactivate_role_has_no_last_admin_check():
    tenant, ws, admin, role = _make_workspace_with_admin("reactivate")
    role.suspended_at = role.created_at
    role.save(update_fields=["suspended_at"])
    service = AuthorizationService()

    service.reactivate_role(
        actor_roles=(ROLE_ADMIN,),
        actor_is_tenant_admin=False,
        target_user_id=admin.id,
        workspace_id=ws.id,
        role=ROLE_ADMIN,
    )
    role.refresh_from_db()
    assert role.suspended_at is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_revoke_of_last_two_admins_only_one_succeeds():
    """Race-condition guard: two threads try to revoke the last two admins
    of the same workspace simultaneously. select_for_update() must ensure
    only one succeeds and the workspace never drops to zero admins."""
    tenant = Tenant.objects.create(name="Race-T", slug="race-t")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="Race-WS")
    admin_a = User.objects.create(username="race-a", email="race-a@t.test", tenant=tenant)
    admin_b = User.objects.create(username="race-b", email="race-b@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=admin_a, workspace=ws, role=ROLE_ADMIN)
    UserRole.objects.create(tenant=tenant, user=admin_b, workspace=ws, role=ROLE_ADMIN)
    tenant_id, ws_id, a_id, b_id = tenant.id, ws.id, admin_a.id, admin_b.id
    TenantContext.clear_tenant()

    results = {}

    def _revoke(target_user_id, key):
        connection.close()  # force a fresh connection per thread
        TenantContext.set_tenant(tenant_id)
        service = AuthorizationService()
        try:
            service.revoke_role(
                actor_roles=(ROLE_ADMIN,),
                target_user_id=target_user_id,
                workspace_id=ws_id,
                role=ROLE_ADMIN,
            )
            results[key] = "ok"
        except LastAdminError:
            results[key] = "blocked"
        finally:
            TenantContext.clear_tenant()
            connection.close()

    t1 = threading.Thread(target=_revoke, args=(a_id, "a"))
    t2 = threading.Thread(target=_revoke, args=(b_id, "b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    TenantContext.set_tenant(tenant_id)
    remaining = UserRole.objects.filter(
        workspace_id=ws_id, role=ROLE_ADMIN, suspended_at__isnull=True
    ).count()
    assert remaining == 1, "workspace must retain exactly one admin, not zero"
    assert sorted(results.values()) == ["blocked", "ok"]


def _make_tenant_with_admin(slug_suffix: str):
    tenant = Tenant.objects.create(name="TA-T", slug=f"ta-t-{slug_suffix}")
    TenantContext.set_tenant(tenant.id)
    admin = User.objects.create(
        username=f"ta-{slug_suffix}", email=f"ta-{slug_suffix}@t.test", tenant=tenant
    )
    role = TenantRole.objects.create(tenant=tenant, user=admin, role=TenantRole.ROLE_ADMIN)
    return tenant, admin, role


@pytest.mark.django_db
def test_is_tenant_admin_true_for_active_row():
    tenant, admin, _role = _make_tenant_with_admin("is-admin")
    service = AuthorizationService()
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is True


@pytest.mark.django_db
def test_is_tenant_admin_false_for_no_row():
    tenant = Tenant.objects.create(name="TA-none", slug="ta-none")
    TenantContext.set_tenant(tenant.id)
    non_admin = User.objects.create(username="ta-none-u", email="ta-none@t.test", tenant=tenant)
    service = AuthorizationService()
    assert service.is_tenant_admin(user_id=non_admin.id, tenant_id=tenant.id) is False


@pytest.mark.django_db
def test_is_tenant_admin_false_for_deactivated_user():
    """C-2 regression: a deactivated user's TenantRole row is still
    ``suspended_at=None`` (deactivation doesn't touch the role row), so
    ``is_tenant_admin`` must reject on ``user.is_active`` explicitly —
    otherwise a deactivated admin's still-valid API key keeps evaluating
    tenant-admin checks as True, letting them undo their own deactivation.
    """
    tenant, admin, _role = _make_tenant_with_admin("deactivated")
    admin.is_active = False
    admin.save(update_fields=["is_active"])
    service = AuthorizationService()
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is False


@pytest.mark.django_db
def test_assign_tenant_admin_requires_tenant_admin_actor():
    tenant, admin, _role = _make_tenant_with_admin("assign-guard")
    target = User.objects.create(username="ta-target", email="ta-target@t.test", tenant=tenant)
    service = AuthorizationService()

    with pytest.raises(PermissionDenied):
        service.assign_tenant_admin(
            actor_is_tenant_admin=False,
            target_user_id=target.id,
            tenant_id=tenant.id,
            assigned_by_user_id=admin.id,
        )


@pytest.mark.django_db
def test_assign_tenant_admin_succeeds_for_tenant_admin_actor():
    tenant, admin, _role = _make_tenant_with_admin("assign-ok")
    target = User.objects.create(username="ta-target2", email="ta-target2@t.test", tenant=tenant)
    service = AuthorizationService()

    result = service.assign_tenant_admin(
        actor_is_tenant_admin=True,
        target_user_id=target.id,
        tenant_id=tenant.id,
        assigned_by_user_id=admin.id,
    )
    assert result.user_id == target.id
    assert service.is_tenant_admin(user_id=target.id, tenant_id=tenant.id) is True


@pytest.mark.django_db
def test_revoke_tenant_admin_blocks_removing_the_last_one():
    tenant, admin, _role = _make_tenant_with_admin("revoke-solo")
    service = AuthorizationService()

    with pytest.raises(LastAdminError):
        service.revoke_tenant_admin(
            actor_is_tenant_admin=True, target_user_id=admin.id, tenant_id=tenant.id
        )
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is True


@pytest.mark.django_db
def test_revoke_tenant_admin_allowed_when_another_remains():
    tenant, admin, _role = _make_tenant_with_admin("revoke-two")
    second = User.objects.create(username="ta-second", email="ta-second@t.test", tenant=tenant)
    TenantRole.objects.create(tenant=tenant, user=second, role=TenantRole.ROLE_ADMIN)
    service = AuthorizationService()

    service.revoke_tenant_admin(
        actor_is_tenant_admin=True, target_user_id=admin.id, tenant_id=tenant.id
    )
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is False


@pytest.mark.django_db
def test_revoke_tenant_admin_blocked_when_other_admin_is_deactivated():
    """Issue #708: a deactivated user's ``TenantRole`` row must not count
    towards the last-admin invariant. Without filtering on
    ``user__is_active``, the sole remaining *active* tenant-admin could
    revoke their own admin role as long as another, already-deactivated
    user still held a tenant-admin row — stranding the tenant with zero
    active admins, recoverable only via a direct DB fix.
    """
    tenant, admin, _role = _make_tenant_with_admin("revoke-deactivated-other")
    second = User.objects.create(
        username="ta-second-deactivated", email="ta-second-deactivated@t.test", tenant=tenant
    )
    TenantRole.objects.create(tenant=tenant, user=second, role=TenantRole.ROLE_ADMIN)
    second.is_active = False
    second.save(update_fields=["is_active"])
    service = AuthorizationService()

    with pytest.raises(LastAdminError):
        service.revoke_tenant_admin(
            actor_is_tenant_admin=True, target_user_id=admin.id, tenant_id=tenant.id
        )
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is True


@pytest.mark.django_db(transaction=True)
def test_concurrent_revoke_of_last_two_tenant_admins_only_one_succeeds():
    """Tenant-level race-condition guard: two threads try to revoke the last
    two tenant-admins of the same tenant simultaneously. select_for_update()
    must ensure only one succeeds and the tenant never drops to zero admins."""
    tenant = Tenant.objects.create(name="Race-TA-T", slug="race-ta-t")
    TenantContext.set_tenant(tenant.id)
    admin_a = User.objects.create(username="race-ta-a", email="race-ta-a@t.test", tenant=tenant)
    admin_b = User.objects.create(username="race-ta-b", email="race-ta-b@t.test", tenant=tenant)
    TenantRole.objects.create(tenant=tenant, user=admin_a, role=TenantRole.ROLE_ADMIN)
    TenantRole.objects.create(tenant=tenant, user=admin_b, role=TenantRole.ROLE_ADMIN)
    tenant_id, a_id, b_id = tenant.id, admin_a.id, admin_b.id
    TenantContext.clear_tenant()

    results = {}

    def _revoke(target_user_id, key):
        connection.close()  # force a fresh connection per thread
        TenantContext.set_tenant(tenant_id)
        service = AuthorizationService()
        try:
            service.revoke_tenant_admin(
                actor_is_tenant_admin=True,
                target_user_id=target_user_id,
                tenant_id=tenant_id,
            )
            results[key] = "ok"
        except LastAdminError:
            results[key] = "blocked"
        finally:
            TenantContext.clear_tenant()
            connection.close()

    t1 = threading.Thread(target=_revoke, args=(a_id, "a"))
    t2 = threading.Thread(target=_revoke, args=(b_id, "b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    TenantContext.set_tenant(tenant_id)
    remaining = TenantRole.objects.filter(
        tenant_id=tenant_id, role=TenantRole.ROLE_ADMIN, suspended_at__isnull=True
    ).count()
    assert remaining == 1, "tenant must retain exactly one admin, not zero"
    assert sorted(results.values()) == ["blocked", "ok"]


@pytest.mark.django_db
def test_revoke_tenant_admin_requires_tenant_admin_actor():
    tenant, admin, _role = _make_tenant_with_admin("revoke-guard")
    service = AuthorizationService()

    with pytest.raises(PermissionDenied):
        service.revoke_tenant_admin(
            actor_is_tenant_admin=False, target_user_id=admin.id, tenant_id=tenant.id
        )
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is True


@pytest.mark.django_db
def test_is_tenant_admin_false_for_suspended_row():
    tenant, admin, role = _make_tenant_with_admin("suspended")
    role.suspended_at = datetime.now(timezone.utc)
    role.save(update_fields=["suspended_at"])
    service = AuthorizationService()

    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is False


# -- Tenant-admin elevation on workspace-scoped role mutations -------------
#
# Interstitial fix (2026-08-21): AuthorizationService.assign_role/
# suspend_role/reactivate_role previously only ever checked the caller's
# workspace-scoped actor_roles, so a caller holding ONLY a tenant-wide
# TenantRole(admin) (no UserRole in any workspace) was incorrectly denied,
# contradicting the shared REST/MCP permission matrix
# (auth_tenancy/tests/user_management_matrix.py: "workspace.assign_role" /
# "workspace.suspend_role" / "workspace.reactivate_role" all list
# tenant-admin: True). These tests prove the elevation now works, and that
# a caller with neither a workspace-admin role nor tenant-admin is still
# correctly denied.


@pytest.mark.django_db
def test_assign_role_allowed_for_pure_tenant_admin_with_no_workspace_role():
    tenant, ws, _existing_admin, _role = _make_workspace_with_admin("ta-assign")
    tenant_admin = User.objects.create(
        username="ta-assign-caller", email="ta-assign-caller@t.test", tenant=tenant
    )
    TenantRole.objects.create(tenant=tenant, user=tenant_admin, role=TenantRole.ROLE_ADMIN)
    target = User.objects.create(
        username="ta-assign-target", email="ta-assign-target@t.test", tenant=tenant
    )
    service = AuthorizationService()
    actor_is_tenant_admin = service.is_tenant_admin(
        user_id=tenant_admin.id, tenant_id=tenant.id
    )

    ur = service.assign_role(
        actor_roles=(),
        actor_is_tenant_admin=actor_is_tenant_admin,
        target_user_id=target.id,
        workspace_id=ws.id,
        tenant_id=tenant.id,
        role=ROLE_EDITOR,
        preset="extended",
        assigned_by_user_id=tenant_admin.id,
        target_is_member=False,
    )
    assert ur.role == ROLE_EDITOR
    assert UserRole.objects.filter(user=target, workspace=ws, role=ROLE_EDITOR).exists()


@pytest.mark.django_db
def test_assign_role_denied_for_actor_with_neither_workspace_admin_nor_tenant_admin():
    tenant, ws, _admin, _role = _make_workspace_with_admin("ta-assign-deny")
    target = User.objects.create(
        username="ta-assign-deny-target", email="ta-assign-deny@t.test", tenant=tenant
    )
    service = AuthorizationService()

    with pytest.raises(PermissionDenied):
        service.assign_role(
            actor_roles=(ROLE_EDITOR,),
            actor_is_tenant_admin=False,
            target_user_id=target.id,
            workspace_id=ws.id,
            tenant_id=tenant.id,
            role=ROLE_EDITOR,
            preset="extended",
            assigned_by_user_id=target.id,
            target_is_member=False,
        )
    assert not UserRole.objects.filter(user=target, workspace=ws, role=ROLE_EDITOR).exists()


@pytest.mark.django_db
def test_suspend_role_allowed_for_pure_tenant_admin_with_no_workspace_role():
    tenant, ws, admin, _role = _make_workspace_with_admin("ta-suspend")
    second_admin = User.objects.create(
        username="ta-suspend-second", email="ta-suspend-second@t.test", tenant=tenant
    )
    UserRole.objects.create(tenant=tenant, user=second_admin, workspace=ws, role=ROLE_ADMIN)
    tenant_admin = User.objects.create(
        username="ta-suspend-caller", email="ta-suspend-caller@t.test", tenant=tenant
    )
    TenantRole.objects.create(tenant=tenant, user=tenant_admin, role=TenantRole.ROLE_ADMIN)
    service = AuthorizationService()
    actor_is_tenant_admin = service.is_tenant_admin(
        user_id=tenant_admin.id, tenant_id=tenant.id
    )

    service.suspend_role(
        actor_roles=(),
        actor_is_tenant_admin=actor_is_tenant_admin,
        target_user_id=admin.id,
        workspace_id=ws.id,
        role=ROLE_ADMIN,
    )
    role = UserRole.objects.get(user=admin, workspace=ws, role=ROLE_ADMIN)
    assert role.suspended_at is not None


@pytest.mark.django_db
def test_suspend_role_denied_for_actor_with_neither_workspace_admin_nor_tenant_admin():
    tenant, ws, admin, _role = _make_workspace_with_admin("ta-suspend-deny")
    service = AuthorizationService()

    with pytest.raises(PermissionDenied):
        service.suspend_role(
            actor_roles=(ROLE_EDITOR,),
            actor_is_tenant_admin=False,
            target_user_id=admin.id,
            workspace_id=ws.id,
            role=ROLE_ADMIN,
        )
    role = UserRole.objects.get(user=admin, workspace=ws, role=ROLE_ADMIN)
    assert role.suspended_at is None


@pytest.mark.django_db
def test_reactivate_role_allowed_for_pure_tenant_admin_with_no_workspace_role():
    tenant, ws, admin, role = _make_workspace_with_admin("ta-reactivate")
    role.suspended_at = role.created_at
    role.save(update_fields=["suspended_at"])
    tenant_admin = User.objects.create(
        username="ta-reactivate-caller", email="ta-reactivate-caller@t.test", tenant=tenant
    )
    TenantRole.objects.create(tenant=tenant, user=tenant_admin, role=TenantRole.ROLE_ADMIN)
    service = AuthorizationService()
    actor_is_tenant_admin = service.is_tenant_admin(
        user_id=tenant_admin.id, tenant_id=tenant.id
    )

    service.reactivate_role(
        actor_roles=(),
        actor_is_tenant_admin=actor_is_tenant_admin,
        target_user_id=admin.id,
        workspace_id=ws.id,
        role=ROLE_ADMIN,
    )
    role.refresh_from_db()
    assert role.suspended_at is None


@pytest.mark.django_db
def test_reactivate_role_denied_for_actor_with_neither_workspace_admin_nor_tenant_admin():
    tenant, ws, admin, role = _make_workspace_with_admin("ta-reactivate-deny")
    role.suspended_at = role.created_at
    role.save(update_fields=["suspended_at"])
    service = AuthorizationService()

    with pytest.raises(PermissionDenied):
        service.reactivate_role(
            actor_roles=(ROLE_EDITOR,),
            actor_is_tenant_admin=False,
            target_user_id=admin.id,
            workspace_id=ws.id,
            role=ROLE_ADMIN,
        )
    role.refresh_from_db()
    assert role.suspended_at is not None


# -- Fix round 1 (code review): I-1 workspace/tenant integrity, I-2 --------
# suspend_role/reactivate_role must not silently no-op on a mismatch -------


@pytest.mark.django_db
def test_assign_role_rejects_workspace_from_a_different_tenant():
    """I-1: a workspace_id from a DIFFERENT tenant than tenant_id must be
    rejected, even for a caller who genuinely IS a tenant-admin of
    ``tenant_id`` — tenant-admin elevation is scoped to that tenant's own
    workspaces, not to any workspace_id the caller happens to supply."""
    tenant_a = Tenant.objects.create(name="I1-A", slug="i1-tenant-a")
    tenant_b = Tenant.objects.create(name="I1-B", slug="i1-tenant-b")

    TenantContext.set_tenant(tenant_b.id)
    foreign_ws = Workspace.objects.create(tenant=tenant_b, name="Foreign WS")

    TenantContext.set_tenant(tenant_a.id)
    tenant_admin = User.objects.create(
        username="i1-admin", email="i1-admin@t.test", tenant=tenant_a
    )
    TenantRole.objects.create(tenant=tenant_a, user=tenant_admin, role=TenantRole.ROLE_ADMIN)
    target = User.objects.create(username="i1-target", email="i1-target@t.test", tenant=tenant_a)
    service = AuthorizationService()
    actor_is_tenant_admin = service.is_tenant_admin(
        user_id=tenant_admin.id, tenant_id=tenant_a.id
    )
    assert actor_is_tenant_admin is True

    with pytest.raises(NotFoundError):
        service.assign_role(
            actor_roles=(),
            actor_is_tenant_admin=actor_is_tenant_admin,
            target_user_id=target.id,
            workspace_id=foreign_ws.id,
            tenant_id=tenant_a.id,
            role=ROLE_EDITOR,
            preset="extended",
            assigned_by_user_id=tenant_admin.id,
            target_is_member=False,
        )
    assert not UserRole.objects.filter(user=target, role=ROLE_EDITOR).exists()


@pytest.mark.django_db
def test_suspend_role_raises_not_found_for_nonexistent_assignment():
    tenant, ws, _admin, _role = _make_workspace_with_admin("i2-suspend-missing")
    other = User.objects.create(
        username="i2-suspend-other", email="i2-suspend-other@t.test", tenant=tenant
    )
    service = AuthorizationService()

    with pytest.raises(NotFoundError):
        service.suspend_role(
            actor_roles=(ROLE_ADMIN,),
            actor_is_tenant_admin=False,
            target_user_id=other.id,
            workspace_id=ws.id,
            role=ROLE_EDITOR,
        )


@pytest.mark.django_db
def test_suspend_role_already_suspended_is_a_noop_not_an_error():
    """A role that IS suspended already must be a legitimate no-op, distinct
    from a role that doesn't exist at all (which raises NotFoundError)."""
    tenant, ws, _admin, _role = _make_workspace_with_admin("i2-suspend-noop")
    editor = User.objects.create(
        username="i2-suspend-noop-editor",
        email="i2-suspend-noop-editor@t.test",
        tenant=tenant,
    )
    editor_role = UserRole.objects.create(
        tenant=tenant, user=editor, workspace=ws, role=ROLE_EDITOR
    )
    editor_role.suspended_at = editor_role.created_at
    editor_role.save(update_fields=["suspended_at"])
    service = AuthorizationService()

    service.suspend_role(
        actor_roles=(ROLE_ADMIN,),
        actor_is_tenant_admin=False,
        target_user_id=editor.id,
        workspace_id=ws.id,
        role=ROLE_EDITOR,
    )
    editor_role.refresh_from_db()
    assert editor_role.suspended_at is not None


@pytest.mark.django_db
def test_reactivate_role_raises_not_found_for_nonexistent_assignment():
    tenant, ws, _admin, _role = _make_workspace_with_admin("i2-reactivate-missing")
    other = User.objects.create(
        username="i2-reactivate-other", email="i2-reactivate-other@t.test", tenant=tenant
    )
    service = AuthorizationService()

    with pytest.raises(NotFoundError):
        service.reactivate_role(
            actor_roles=(ROLE_ADMIN,),
            actor_is_tenant_admin=False,
            target_user_id=other.id,
            workspace_id=ws.id,
            role=ROLE_EDITOR,
        )


@pytest.mark.django_db
def test_reactivate_role_already_active_is_a_noop_not_an_error():
    """A role that is already active must be a legitimate no-op, distinct
    from a role that doesn't exist at all (which raises NotFoundError)."""
    tenant, ws, _admin, _role = _make_workspace_with_admin("i2-reactivate-noop")
    editor = User.objects.create(
        username="i2-reactivate-noop-editor",
        email="i2-reactivate-noop-editor@t.test",
        tenant=tenant,
    )
    UserRole.objects.create(tenant=tenant, user=editor, workspace=ws, role=ROLE_EDITOR)
    service = AuthorizationService()

    service.reactivate_role(
        actor_roles=(ROLE_ADMIN,),
        actor_is_tenant_admin=False,
        target_user_id=editor.id,
        workspace_id=ws.id,
        role=ROLE_EDITOR,
    )
    role = UserRole.objects.get(user=editor, workspace=ws, role=ROLE_EDITOR)
    assert role.suspended_at is None
