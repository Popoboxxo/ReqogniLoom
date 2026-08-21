from __future__ import annotations

import pytest
from django.db import IntegrityError

from auth_tenancy.models import TenantRole
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_tenant_role_admin_can_be_created():
    tenant = Tenant.objects.create(name="T", slug="tr-model-t")
    user = User.objects.create(username="tr-user", email="tr@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    role = TenantRole.objects.create(
        tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN
    )
    assert role.role == "admin"
    assert role.suspended_at is None
    assert role.is_active is True


@pytest.mark.django_db
def test_tenant_role_unique_together_blocks_duplicate():
    tenant = Tenant.objects.create(name="T2", slug="tr-model-t2")
    user = User.objects.create(username="tr-user2", email="tr2@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    with pytest.raises(IntegrityError):
        TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)


@pytest.mark.django_db
def test_tenant_role_is_active_reflects_suspension():
    from datetime import datetime, timezone

    tenant = Tenant.objects.create(name="T3", slug="tr-model-t3")
    user = User.objects.create(username="tr-user3", email="tr3@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    role = TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    role.suspended_at = datetime.now(timezone.utc)
    role.save(update_fields=["suspended_at"])
    assert role.is_active is False
