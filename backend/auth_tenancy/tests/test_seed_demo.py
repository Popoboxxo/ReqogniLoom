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
def test_seed_demo_initializes_workflow_definitions():
    """#41: seed_demo left workflow definitions empty (states=[], transitions=[],
    initialized=True) until a separate POST /workflows/definition/initialize/
    per entity type. Same fix application.self_init.run_self_init() already
    applies after its own provision_admin() call."""
    from workflow.services import get_definition
    from auth_tenancy.provisioning import DEFAULT_WORKSPACE_ID

    call_command("seed_demo")

    set_request_tenant(Tenant.objects.get(slug="demo").id)
    try:
        # Raises WorkflowDefinitionError if unconfigured -- the bug this
        # regression guards against.
        definition = get_definition(
            workspace_id=DEFAULT_WORKSPACE_ID, item_type="Requirement"
        )
        assert definition.states, "Requirement workflow has no states"
        assert definition.transitions, "Requirement workflow has no transitions"
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_admin_password_is_usable(monkeypatch):
    # Default password when no admin-password env var is set.
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")
    admin = User.objects.get(username="admin")
    assert admin.check_password("admin12345") is True
    assert admin.is_active is True


@pytest.mark.django_db
def test_seed_demo_is_create_only_by_default(monkeypatch):
    """A second seed_demo run must not overwrite a changed password."""
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")

    admin = User.objects.get(username="admin")
    admin.set_password("changed-via-ui")
    admin.save(update_fields=["password", "modified_at"])

    call_command("seed_demo")  # default is create-only

    admin.refresh_from_db()
    assert admin.check_password("changed-via-ui") is True


@pytest.mark.django_db
def test_seed_demo_reset_password_flag_reapplies(monkeypatch):
    """--reset-password re-applies the demo password on an existing user."""
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")

    admin = User.objects.get(username="admin")
    admin.set_password("changed-via-ui")
    admin.save(update_fields=["password", "modified_at"])

    call_command("seed_demo", "--reset-password")

    admin.refresh_from_db()
    assert admin.check_password("admin12345") is True
