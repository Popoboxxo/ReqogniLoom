from __future__ import annotations

import pytest

from auth_tenancy.errors import PermissionDenied
from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from auth_tenancy.services.authorization import LastAdminError
from auth_tenancy.services.user_account import UserAccountService
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_create_requires_tenant_admin_actor():
    tenant = Tenant.objects.create(name="UA-T", slug="ua-t1")
    service = UserAccountService()
    with pytest.raises(PermissionDenied):
        service.create(
            actor_is_tenant_admin=False,
            tenant_id=tenant.id,
            username="new-user",
            email="new@t.test",
            password="a-real-password-123",
        )


@pytest.mark.django_db
def test_create_succeeds_and_sets_a_usable_password():
    tenant = Tenant.objects.create(name="UA-T2", slug="ua-t2")
    service = UserAccountService()
    user = service.create(
        actor_is_tenant_admin=True,
        tenant_id=tenant.id,
        username="new-user2",
        email="new2@t.test",
        password="a-real-password-123",
    )
    assert user.is_active is True
    assert user.check_password("a-real-password-123") is True


@pytest.mark.django_db
def test_deactivate_blocked_when_target_is_last_workspace_admin():
    tenant = Tenant.objects.create(name="UA-T3", slug="ua-t3")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    target = User.objects.create(username="ua-target", email="ua-target@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=target, workspace=ws, role=ROLE_ADMIN)
    service = UserAccountService()

    with pytest.raises(LastAdminError):
        service.deactivate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_deactivate_blocked_when_target_is_last_tenant_admin():
    tenant = Tenant.objects.create(name="UA-T4", slug="ua-t4")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(username="ua-target2", email="ua-target2@t.test", tenant=tenant)
    TenantRole.objects.create(tenant=tenant, user=target, role=TenantRole.ROLE_ADMIN)
    service = UserAccountService()

    with pytest.raises(LastAdminError):
        service.deactivate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_deactivate_succeeds_for_a_non_admin_user():
    tenant = Tenant.objects.create(name="UA-T5", slug="ua-t5")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(username="ua-target3", email="ua-target3@t.test", tenant=tenant)
    service = UserAccountService()

    service.deactivate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_activate_has_no_last_admin_check_and_requires_tenant_admin():
    tenant = Tenant.objects.create(name="UA-T6", slug="ua-t6")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(
        username="ua-target4", email="ua-target4@t.test", tenant=tenant, is_active=False
    )
    service = UserAccountService()

    with pytest.raises(PermissionDenied):
        service.activate(actor_is_tenant_admin=False, target_user_id=target.id)

    service.activate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is True
