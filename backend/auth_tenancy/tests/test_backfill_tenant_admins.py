"""Tests the data migration that gives every existing tenant its first
TenantRole(admin), driven directly (not via migrator harness, matching
this codebase's convention for testing migration RunPython functions —
see test_prompt_template_migration.py for the MigrationExecutor pattern
used elsewhere, though this one is simpler: no schema rollback needed,
just the RunPython function itself, importable directly since it has a
normal module name)."""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "migrations"
    / "0010_backfill_tenant_admins.py"
)


def _load_backfill_tenant_admins():
    spec = importlib.util.spec_from_file_location(
        "_backfill_tenant_admins_under_test", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.backfill_tenant_admins


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_earliest_workspace_admin_becomes_tenant_admin():
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="Backfill T", slug="backfill-t1")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    early_admin = User.objects.create(
        username="early-admin", email="early@t.test", tenant=tenant
    )
    later_admin = User.objects.create(
        username="later-admin", email="later@t.test", tenant=tenant
    )
    UserRole.objects.create(
        tenant=tenant, user=later_admin, workspace=ws, role=ROLE_ADMIN
    )
    early_role = UserRole.objects.create(
        tenant=tenant, user=early_admin, workspace=ws, role=ROLE_ADMIN
    )
    # Force early_role's created_at earlier than later_admin's role, since
    # both were just created in the same test with near-identical timestamps.
    from datetime import timedelta

    UserRole.objects.filter(pk=early_role.pk).update(
        created_at=early_role.created_at - timedelta(days=1)
    )

    backfill_tenant_admins(apps=None, schema_editor=None)

    tenant_admins = TenantRole.unscoped.filter(tenant=tenant, role=ROLE_ADMIN)
    assert tenant_admins.count() == 1
    assert tenant_admins.first().user_id == early_admin.id


@pytest.mark.django_db
def test_tenant_with_no_workspace_admin_gets_no_row():
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="No Admin T", slug="backfill-t2")

    backfill_tenant_admins(apps=None, schema_editor=None)

    assert TenantRole.unscoped.filter(tenant=tenant).count() == 0
