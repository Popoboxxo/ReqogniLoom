"""
ARCH-L1-011 AuthAndTenancy — provision_admin tenant-role provisioning tests.

Covers that provision_admin (used by the mandatory bootstrap_admin management
command) also creates the tenant's first TenantRole(admin), not just the
workspace-level UserRole(admin), and does so idempotently.
"""
from __future__ import annotations

import pytest

from auth_tenancy.models import TenantRole
from auth_tenancy.provisioning import provision_admin


@pytest.mark.django_db
def test_provision_admin_creates_first_tenant_admin_role():
    result = provision_admin(
        username="bootstrap-test-admin",
        email="bootstrap-test@demo.local",
        password="a-real-password-123",
    )
    assert result.tenant_role.user_id == result.user.id
    assert result.tenant_role.tenant_id == result.tenant.id
    assert result.tenant_role.role == TenantRole.ROLE_ADMIN
    assert TenantRole.unscoped.filter(
        tenant_id=result.tenant.id, user_id=result.user.id, role=TenantRole.ROLE_ADMIN
    ).exists()


@pytest.mark.django_db
def test_provision_admin_is_idempotent_for_tenant_role_too():
    first = provision_admin(
        username="bootstrap-test-admin2",
        email="bootstrap-test2@demo.local",
        password="a-real-password-123",
    )
    second = provision_admin(
        username="bootstrap-test-admin2",
        email="bootstrap-test2@demo.local",
        password="unused-on-second-call",
    )
    assert TenantRole.unscoped.filter(
        tenant_id=first.tenant.id, user_id=first.user.id, role=TenantRole.ROLE_ADMIN
    ).count() == 1
    assert second.tenant_role.id == first.tenant_role.id
