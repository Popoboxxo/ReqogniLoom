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
        service.deactivate(
            actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=target.id
        )
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
        service.deactivate(
            actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=target.id
        )
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_deactivate_succeeds_for_a_non_admin_user():
    tenant = Tenant.objects.create(name="UA-T5", slug="ua-t5")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(username="ua-target3", email="ua-target3@t.test", tenant=tenant)
    service = UserAccountService()

    service.deactivate(
        actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=target.id
    )
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
        service.activate(
            actor_is_tenant_admin=False, actor_tenant_id=tenant.id, target_user_id=target.id
        )

    service.activate(
        actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=target.id
    )
    target.refresh_from_db()
    assert target.is_active is True


# -- Fix Round 1: connecting case, real second-admin coverage, Fix 1/2/3 ------


@pytest.mark.django_db
def test_deactivate_blocked_when_target_is_last_admin_in_both_scopes_at_once():
    """Connecting case: one user is simultaneously the last workspace-admin
    AND the last tenant-admin. Deactivating them must raise LastAdminError
    (either scope is a sufficient blocker on its own)."""
    tenant = Tenant.objects.create(name="UA-Conn", slug="ua-conn")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    target = User.objects.create(username="ua-conn", email="ua-conn@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=target, workspace=ws, role=ROLE_ADMIN)
    TenantRole.objects.create(tenant=tenant, user=target, role=TenantRole.ROLE_ADMIN)
    service = UserAccountService()

    with pytest.raises(LastAdminError):
        service.deactivate(
            actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=target.id
        )
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_deactivate_allowed_when_a_second_workspace_admin_exists():
    tenant = Tenant.objects.create(name="UA-2WS", slug="ua-2ws")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    first = User.objects.create(username="ua-2ws-a", email="ua-2ws-a@t.test", tenant=tenant)
    second = User.objects.create(username="ua-2ws-b", email="ua-2ws-b@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=first, workspace=ws, role=ROLE_ADMIN)
    UserRole.objects.create(tenant=tenant, user=second, workspace=ws, role=ROLE_ADMIN)
    service = UserAccountService()

    service.deactivate(
        actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=first.id
    )
    first.refresh_from_db()
    assert first.is_active is False


@pytest.mark.django_db
def test_deactivate_allowed_when_a_second_tenant_admin_exists():
    tenant = Tenant.objects.create(name="UA-2TA", slug="ua-2ta")
    TenantContext.set_tenant(tenant.id)
    first = User.objects.create(username="ua-2ta-a", email="ua-2ta-a@t.test", tenant=tenant)
    second = User.objects.create(username="ua-2ta-b", email="ua-2ta-b@t.test", tenant=tenant)
    TenantRole.objects.create(tenant=tenant, user=first, role=TenantRole.ROLE_ADMIN)
    TenantRole.objects.create(tenant=tenant, user=second, role=TenantRole.ROLE_ADMIN)
    service = UserAccountService()

    service.deactivate(
        actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=first.id
    )
    first.refresh_from_db()
    assert first.is_active is False


@pytest.mark.django_db
def test_deactivate_already_inactive_user_is_a_noop():
    tenant = Tenant.objects.create(name="UA-Noop", slug="ua-noop")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(
        username="ua-noop", email="ua-noop@t.test", tenant=tenant, is_active=False
    )
    service = UserAccountService()

    service.deactivate(
        actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=target.id
    )
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_deactivate_already_inactive_last_admin_is_a_noop_not_an_error():
    """Fix 1 companion: an already-deactivated admin's stale role row must
    not spuriously trip the last-admin guard on a repeat/no-op deactivate."""
    tenant = Tenant.objects.create(name="UA-NoopAdmin", slug="ua-noop-admin")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    target = User.objects.create(
        username="ua-noop-admin", email="ua-noop-admin@t.test", tenant=tenant, is_active=False
    )
    UserRole.objects.create(tenant=tenant, user=target, workspace=ws, role=ROLE_ADMIN)
    service = UserAccountService()

    service.deactivate(
        actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=target.id
    )
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_sequential_deactivation_of_two_co_admins_blocks_the_second():
    """Fix 1: deactivating co-admins one at a time must not silently drop
    the workspace to zero *usable* admins — the second deactivation has to
    see that the first admin's role row no longer counts (User.is_active is
    now False) and block."""
    tenant = Tenant.objects.create(name="UA-Seq", slug="ua-seq")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    first = User.objects.create(username="ua-seq-a", email="ua-seq-a@t.test", tenant=tenant)
    second = User.objects.create(username="ua-seq-b", email="ua-seq-b@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=first, workspace=ws, role=ROLE_ADMIN)
    UserRole.objects.create(tenant=tenant, user=second, workspace=ws, role=ROLE_ADMIN)
    service = UserAccountService()

    service.deactivate(
        actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=first.id
    )
    first.refresh_from_db()
    assert first.is_active is False

    with pytest.raises(LastAdminError):
        service.deactivate(
            actor_is_tenant_admin=True, actor_tenant_id=tenant.id, target_user_id=second.id
        )
    second.refresh_from_db()
    assert second.is_active is True


@pytest.mark.django_db
def test_deactivate_rejects_cross_tenant_target():
    tenant_a = Tenant.objects.create(name="UA-XA", slug="ua-xa")
    tenant_b = Tenant.objects.create(name="UA-XB", slug="ua-xb")
    TenantContext.set_tenant(tenant_b.id)
    target = User.objects.create(username="ua-xb-target", email="ua-xb@t.test", tenant=tenant_b)
    service = UserAccountService()

    with pytest.raises(PermissionDenied):
        service.deactivate(
            actor_is_tenant_admin=True, actor_tenant_id=tenant_a.id, target_user_id=target.id
        )
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_activate_rejects_cross_tenant_target():
    tenant_a = Tenant.objects.create(name="UA-YA", slug="ua-ya")
    tenant_b = Tenant.objects.create(name="UA-YB", slug="ua-yb")
    TenantContext.set_tenant(tenant_b.id)
    target = User.objects.create(
        username="ua-yb-target", email="ua-yb@t.test", tenant=tenant_b, is_active=False
    )
    service = UserAccountService()

    with pytest.raises(PermissionDenied):
        service.activate(
            actor_is_tenant_admin=True, actor_tenant_id=tenant_a.id, target_user_id=target.id
        )
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_create_rejects_duplicate_username_with_a_clear_error():
    tenant = Tenant.objects.create(name="UA-Dup1", slug="ua-dup1")
    service = UserAccountService()
    service.create(
        actor_is_tenant_admin=True,
        tenant_id=tenant.id,
        username="dup-user",
        email="dup-a@t.test",
        password="a-real-password-123",
    )

    with pytest.raises(ValueError):
        service.create(
            actor_is_tenant_admin=True,
            tenant_id=tenant.id,
            username="dup-user",
            email="dup-b@t.test",
            password="a-real-password-123",
        )


@pytest.mark.django_db
def test_create_rejects_duplicate_email_with_a_clear_error():
    tenant = Tenant.objects.create(name="UA-Dup2", slug="ua-dup2")
    service = UserAccountService()
    service.create(
        actor_is_tenant_admin=True,
        tenant_id=tenant.id,
        username="dup-email-a",
        email="dup-shared@t.test",
        password="a-real-password-123",
    )

    with pytest.raises(ValueError):
        service.create(
            actor_is_tenant_admin=True,
            tenant_id=tenant.id,
            username="dup-email-b",
            email="dup-shared@t.test",
            password="a-real-password-123",
        )


@pytest.mark.django_db
def test_create_rejects_too_short_password():
    tenant = Tenant.objects.create(name="UA-ShortPw", slug="ua-shortpw")
    service = UserAccountService()

    with pytest.raises(ValueError):
        service.create(
            actor_is_tenant_admin=True,
            tenant_id=tenant.id,
            username="short-pw-user",
            email="short-pw@t.test",
            password="short1",
        )


# -- Fix Round 2: overlong username/email -> clean ValueError, not a 500 -----


@pytest.mark.django_db
def test_create_rejects_username_over_max_length():
    """Fix round 2 / Fix 1: an overlong username must be rejected with a
    clean ValueError before it ever reaches the DB insert (Postgres'
    varchar(150) column would otherwise raise an uncaught DataError)."""
    tenant = Tenant.objects.create(name="UA-LongUser", slug="ua-longuser")
    service = UserAccountService()

    with pytest.raises(ValueError):
        service.create(
            actor_is_tenant_admin=True,
            tenant_id=tenant.id,
            username="u" * 151,
            email="long-username@t.test",
            password="a-real-password-123",
        )


@pytest.mark.django_db
def test_create_rejects_email_over_max_length():
    """Fix round 2 / Fix 1: an overlong email must be rejected with a clean
    ValueError before it ever reaches the DB insert (the EmailField column
    is varchar(254))."""
    tenant = Tenant.objects.create(name="UA-LongEmail", slug="ua-longemail")
    service = UserAccountService()

    with pytest.raises(ValueError):
        service.create(
            actor_is_tenant_admin=True,
            tenant_id=tenant.id,
            username="long-email-user",
            email=("a" * 250) + "@t.test",
            password="a-real-password-123",
        )
