"""
ARCH-L1-011 AuthAndTenancy — bootstrap_admin management command tests.

Covers the mandatory, create-only admin provisioning contract (REQ-L1-010):
idempotency, create-only password handling and the fail-fast guard when an
admin must be created without a password.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.mark.django_db
def test_bootstrap_creates_base_data_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "s3cure-bootstrap-pw")
    call_command("bootstrap_admin")
    call_command("bootstrap_admin")  # second run must not duplicate anything

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

    admin = User.objects.get(username="admin")
    assert admin.check_password("s3cure-bootstrap-pw") is True
    assert admin.is_staff is True
    assert admin.is_superuser is True


@pytest.mark.django_db
def test_bootstrap_is_create_only_on_password(monkeypatch):
    """A password changed after creation must survive later bootstrap runs."""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "initial-pw")
    call_command("bootstrap_admin")

    admin = User.objects.get(username="admin")
    admin.set_password("rotated-via-ui")
    admin.save(update_fields=["password", "modified_at"])

    # Even if the env var still holds the old value, the existing password wins.
    call_command("bootstrap_admin")

    admin.refresh_from_db()
    assert admin.check_password("rotated-via-ui") is True
    assert admin.check_password("initial-pw") is False


@pytest.mark.django_db
def test_bootstrap_fails_fast_when_creating_without_password(monkeypatch):
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)

    with pytest.raises(CommandError):
        call_command("bootstrap_admin")

    assert User.objects.filter(username="admin").exists() is False


@pytest.mark.django_db
def test_bootstrap_noop_without_password_when_admin_exists(monkeypatch):
    """Once the admin exists, a missing password is tolerated (no-op)."""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "initial-pw")
    call_command("bootstrap_admin")

    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    call_command("bootstrap_admin")  # must not raise

    admin = User.objects.get(username="admin")
    assert admin.check_password("initial-pw") is True
