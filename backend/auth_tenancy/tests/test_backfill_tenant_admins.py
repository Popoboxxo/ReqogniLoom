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
from datetime import datetime, timedelta, timezone

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

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


@pytest.fixture(scope="module")
def historical_apps(django_db_blocker):
    """Build a real historical (``StateApps``) registry, the same kind of
    ``apps`` argument Django's migration executor actually passes into a
    ``RunPython`` function.

    This is deliberately NOT ``django.apps.apps`` (the live registry):
    ``django.apps.apps.get_model(...)`` returns the real, imported model
    classes complete with their custom managers (e.g. ``TenantManager`` as
    ``TenantRole.objects``/``UserRole.objects``), which require an active
    ``TenantContext`` and would make this tenant-agnostic backfill function
    behave incorrectly (or raise) under test even though it works fine in
    a real migration run. ``TenantManager``/``UnscopedManager`` do not set
    ``use_in_migrations = True``, so genuine historical models built from
    migration *state* (as produced here, mirroring
    ``test_prompt_template_migration.py``'s pattern) fall back to Django's
    plain, unfiltered default manager — matching what
    ``0010_backfill_tenant_admins.py`` (and its sibling ``0008``) actually
    receive in production.

    No schema rollback is needed here (unlike
    ``test_prompt_template_migration.py``): the test DB is already fully
    migrated to head, and ``project_state()`` with no target computes the
    full-graph state purely from migration operations, without touching
    the DB. Session/module-scoped because building it replays every
    migration's state operations and does not depend on any test's data.
    """
    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        return executor.loader.project_state().apps


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_earliest_workspace_admin_becomes_tenant_admin(historical_apps):
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
    UserRole.objects.filter(pk=early_role.pk).update(
        created_at=early_role.created_at - timedelta(days=1)
    )

    backfill_tenant_admins(historical_apps, None)

    tenant_admins = TenantRole.unscoped.filter(tenant=tenant, role=ROLE_ADMIN)
    assert tenant_admins.count() == 1
    assert tenant_admins.first().user_id == early_admin.id


@pytest.mark.django_db
def test_tenant_with_no_workspace_admin_gets_no_row(historical_apps):
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="No Admin T", slug="backfill-t2")

    backfill_tenant_admins(historical_apps, None)

    assert TenantRole.unscoped.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_suspended_workspace_admin_is_not_used_as_backfill_source(historical_apps):
    """A suspended workspace-admin role must be treated the same as no
    admin at all — it must never become the backfill source."""
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="Suspended Admin T", slug="backfill-t3")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    suspended_admin = User.objects.create(
        username="suspended-admin", email="suspended@t.test", tenant=tenant
    )
    UserRole.objects.create(
        tenant=tenant,
        user=suspended_admin,
        workspace=ws,
        role=ROLE_ADMIN,
        suspended_at=datetime.now(timezone.utc),
    )

    backfill_tenant_admins(historical_apps, None)

    assert TenantRole.unscoped.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_deactivated_workspace_admin_is_not_used_as_backfill_source(historical_apps):
    """Fix round 3 (I-2): a deactivated user's active, non-suspended
    ``UserRole(admin)`` row must never become the backfill source — the
    role row survives deactivation (only ``User.is_active`` flips), so
    without the ``user__is_active`` filter the migration could promote a
    user who can no longer even authenticate."""
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="Deactivated Admin T", slug="backfill-t3b")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    deactivated_admin = User.objects.create(
        username="deactivated-admin",
        email="deactivated@t.test",
        tenant=tenant,
        is_active=False,
    )
    UserRole.objects.create(
        tenant=tenant, user=deactivated_admin, workspace=ws, role=ROLE_ADMIN
    )

    backfill_tenant_admins(historical_apps, None)

    assert TenantRole.unscoped.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_deactivated_earliest_admin_is_skipped_for_next_active_one(historical_apps):
    """When the earliest-created admin role belongs to a deactivated user,
    the backfill must fall through to the next active-user admin role,
    not just skip the tenant entirely."""
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="Mixed Admin T", slug="backfill-t3c")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    deactivated_admin = User.objects.create(
        username="mixed-deactivated",
        email="mixed-deactivated@t.test",
        tenant=tenant,
        is_active=False,
    )
    active_admin = User.objects.create(
        username="mixed-active", email="mixed-active@t.test", tenant=tenant
    )
    deactivated_role = UserRole.objects.create(
        tenant=tenant, user=deactivated_admin, workspace=ws, role=ROLE_ADMIN
    )
    UserRole.objects.filter(pk=deactivated_role.pk).update(
        created_at=deactivated_role.created_at - timedelta(days=1)
    )
    UserRole.objects.create(
        tenant=tenant, user=active_admin, workspace=ws, role=ROLE_ADMIN
    )

    backfill_tenant_admins(historical_apps, None)

    tenant_admins = TenantRole.unscoped.filter(tenant=tenant, role=ROLE_ADMIN)
    assert tenant_admins.count() == 1
    assert tenant_admins.first().user_id == active_admin.id


@pytest.mark.django_db
def test_backfill_is_idempotent_on_second_run(historical_apps):
    """Running the backfill twice must not create a duplicate or replace
    the already-promoted admin."""
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="Idempotent T", slug="backfill-t4")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    admin = User.objects.create(
        username="idempotent-admin", email="idempotent@t.test", tenant=tenant
    )
    UserRole.objects.create(tenant=tenant, user=admin, workspace=ws, role=ROLE_ADMIN)

    backfill_tenant_admins(historical_apps, None)
    backfill_tenant_admins(historical_apps, None)

    tenant_admins = TenantRole.unscoped.filter(tenant=tenant, role=ROLE_ADMIN)
    assert tenant_admins.count() == 1
    assert tenant_admins.first().user_id == admin.id


@pytest.mark.django_db
def test_backfill_promotes_each_tenants_own_admin_not_globally_earliest(historical_apps):
    """Each tenant must get its own workspace admin promoted, not the
    globally-earliest admin across all tenants."""
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant_a = Tenant.objects.create(name="Tenant A", slug="backfill-t5a")
    tenant_b = Tenant.objects.create(name="Tenant B", slug="backfill-t5b")

    TenantContext.set_tenant(tenant_a.id)
    ws_a = Workspace.objects.create(tenant=tenant_a, name="WS A")
    admin_a = User.objects.create(
        username="admin-a", email="admin-a@t.test", tenant=tenant_a
    )
    role_a = UserRole.objects.create(
        tenant=tenant_a, user=admin_a, workspace=ws_a, role=ROLE_ADMIN
    )
    # Backdate tenant A's admin role so it is earlier than tenant B's, even
    # though tenant B's role is created second below — the backfill must
    # still pick each tenant's own admin, not the globally-earliest one.
    UserRole.objects.filter(pk=role_a.pk).update(
        created_at=role_a.created_at - timedelta(days=1)
    )

    TenantContext.set_tenant(tenant_b.id)
    ws_b = Workspace.objects.create(tenant=tenant_b, name="WS B")
    admin_b = User.objects.create(
        username="admin-b", email="admin-b@t.test", tenant=tenant_b
    )
    UserRole.objects.create(
        tenant=tenant_b, user=admin_b, workspace=ws_b, role=ROLE_ADMIN
    )

    backfill_tenant_admins(historical_apps, None)

    tenant_a_admins = TenantRole.unscoped.filter(tenant=tenant_a, role=ROLE_ADMIN)
    tenant_b_admins = TenantRole.unscoped.filter(tenant=tenant_b, role=ROLE_ADMIN)
    assert tenant_a_admins.count() == 1
    assert tenant_a_admins.first().user_id == admin_a.id
    assert tenant_b_admins.count() == 1
    assert tenant_b_admins.first().user_id == admin_b.id
