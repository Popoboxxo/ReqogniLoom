"""
ARCH-L1-011 AuthAndTenancy — seed_demo management command tests (REQ-L1-010).

Verifies the demo seed is idempotent and provisions a working admin login.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.mark.django_db
def test_seed_demo_creates_admin_and_is_idempotent():
    call_command("seed_demo")
    call_command("seed_demo")  # second run must not duplicate anything

    assert Tenant.objects.filter(slug="demo").count() == 1
    assert User.objects.filter(username="admin").count() == 1

    tenant = Tenant.objects.get(slug="demo")
    set_request_tenant(tenant.id)
    try:
        assert Workspace.objects.filter(name="Demo Workspace").count() == 1
        admin = User.objects.get(username="admin")
        assert UserRole.objects.filter(user=admin, role=ROLE_ADMIN).count() == 1
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_admin_password_is_usable():
    call_command("seed_demo")
    admin = User.objects.get(username="admin")
    # Default password when DEMO_ADMIN_PASSWORD is unset.
    assert admin.check_password("admin12345") is True
    assert admin.is_active is True
