"""Backfill of admin roles into role-less workspaces (GitHub #103).

Exercises the data-migration function
``auth_tenancy.migrations.0008_backfill_admin_roles_for_roleless_workspaces``
against the **historical** app registry, reconstructed via ``MigrationLoader``.

Using the historical registry matters: the live models expose the tenant-scoped
``TenantManager`` as ``objects``, whereas historical models get a plain manager.
Running the migration against the live registry would therefore raise
``TenantContextNotSetError`` and prove nothing about the real migration.

The backfill is what stops the workspace-scoping fix from locking everybody out
of workspaces created before #232 / PR #241 (which had zero ``UserRole`` rows).
"""
from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_MIGRATION_NAME = "0008_backfill_admin_roles_for_roleless_workspaces"
_MIGRATION = importlib.import_module(f"auth_tenancy.migrations.{_MIGRATION_NAME}")


def _historical_apps():
    """Return the app registry as of the migration's dependency state."""
    loader = MigrationLoader(connection)
    state = loader.project_state(
        ("auth_tenancy", "0007_flip_enforcement_authoritative")
    )
    return state.apps


def _run_backfill() -> None:
    """Invoke the migration's forward function against the historical registry."""
    _MIGRATION.backfill_admin_roles(_historical_apps(), None)


def _make_tenant(prefix: str) -> Tenant:
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    return Tenant.objects.create(name=slug, slug=slug, is_active=True)


def _make_user(tenant: Tenant, label: str) -> User:
    slug = f"{label}-{uuid.uuid4().hex[:8]}"
    return User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )


def _make_workspace(tenant: Tenant, name: str) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


def _grant(tenant: Tenant, user: User, workspace: Workspace, role: str, **extra):
    """Create a role assignment (needs an active tenant context to write)."""
    set_request_tenant(tenant.id)
    try:
        return UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role, **extra
        )
    finally:
        clear_request_tenant()


def _active_roles(workspace: Workspace) -> list[tuple]:
    return sorted(
        UserRole.unscoped.filter(
            workspace_id=workspace.id, suspended_at__isnull=True
        ).values_list("user_id", "role")
    )


@pytest.mark.django_db
def test_roleless_workspace_gets_tenant_admins() -> None:
    """A workspace with no assignments receives every admin of its tenant."""
    tenant = _make_tenant("bf-admins")
    admin_a = _make_user(tenant, "admin-a")
    admin_b = _make_user(tenant, "admin-b")
    editor = _make_user(tenant, "editor")

    anchor = _make_workspace(tenant, "anchor")
    orphan = _make_workspace(tenant, "orphan")

    _grant(tenant, admin_a, anchor, ROLE_ADMIN)
    _grant(tenant, admin_b, anchor, ROLE_ADMIN)
    _grant(tenant, editor, anchor, ROLE_EDITOR)

    _run_backfill()

    assert _active_roles(orphan) == sorted(
        [(admin_a.id, ROLE_ADMIN), (admin_b.id, ROLE_ADMIN)]
    ), "every tenant admin must be granted admin in the role-less workspace"


@pytest.mark.django_db
def test_editor_is_not_backfilled() -> None:
    """Only admin is backfilled — editor reach must not survive the fix."""
    tenant = _make_tenant("bf-editor")
    admin = _make_user(tenant, "admin")
    editor = _make_user(tenant, "editor")
    anchor = _make_workspace(tenant, "anchor")
    orphan = _make_workspace(tenant, "orphan")

    _grant(tenant, admin, anchor, ROLE_ADMIN)
    _grant(tenant, editor, anchor, ROLE_EDITOR)

    _run_backfill()

    assert _active_roles(orphan) == [(admin.id, ROLE_ADMIN)]


@pytest.mark.django_db
def test_workspace_with_existing_roles_is_untouched() -> None:
    """A managed workspace keeps exactly its assignments — no admin injected."""
    tenant = _make_tenant("bf-managed")
    admin = _make_user(tenant, "admin")
    editor = _make_user(tenant, "editor")
    anchor = _make_workspace(tenant, "anchor")
    managed = _make_workspace(tenant, "managed")

    _grant(tenant, admin, anchor, ROLE_ADMIN)
    _grant(tenant, editor, managed, ROLE_EDITOR)

    _run_backfill()

    assert _active_roles(managed) == [(editor.id, ROLE_EDITOR)]


@pytest.mark.django_db
def test_suspended_assignment_does_not_count_as_managed() -> None:
    """Only suspended rows means the workspace is still effectively role-less."""
    from django.utils import timezone

    tenant = _make_tenant("bf-suspended")
    admin = _make_user(tenant, "admin")
    anchor = _make_workspace(tenant, "anchor")
    orphan = _make_workspace(tenant, "orphan")

    _grant(tenant, admin, anchor, ROLE_ADMIN)
    _grant(tenant, admin, orphan, ROLE_EDITOR, suspended_at=timezone.now())

    _run_backfill()

    assert (admin.id, ROLE_ADMIN) in _active_roles(orphan)


@pytest.mark.django_db
def test_tenant_without_admin_is_left_alone() -> None:
    """No identity may legitimately be promoted, so nothing is granted."""
    tenant = _make_tenant("bf-noadmin")
    editor = _make_user(tenant, "editor")
    anchor = _make_workspace(tenant, "anchor")
    orphan = _make_workspace(tenant, "orphan")

    _grant(tenant, editor, anchor, ROLE_EDITOR)

    _run_backfill()

    assert _active_roles(orphan) == []


@pytest.mark.django_db
def test_admins_do_not_leak_across_tenants() -> None:
    """An admin of tenant A must never be granted a role in tenant B."""
    tenant_a = _make_tenant("bf-tenant-a")
    tenant_b = _make_tenant("bf-tenant-b")
    admin_a = _make_user(tenant_a, "admin-a")
    admin_b = _make_user(tenant_b, "admin-b")

    anchor_a = _make_workspace(tenant_a, "anchor-a")
    anchor_b = _make_workspace(tenant_b, "anchor-b")
    orphan_b = _make_workspace(tenant_b, "orphan-b")

    _grant(tenant_a, admin_a, anchor_a, ROLE_ADMIN)
    _grant(tenant_b, admin_b, anchor_b, ROLE_ADMIN)

    _run_backfill()

    assert _active_roles(orphan_b) == [(admin_b.id, ROLE_ADMIN)]


@pytest.mark.django_db
def test_backfill_is_idempotent() -> None:
    """Re-running must not raise on the unique constraint nor duplicate rows."""
    tenant = _make_tenant("bf-idempotent")
    admin = _make_user(tenant, "admin")
    anchor = _make_workspace(tenant, "anchor")
    orphan = _make_workspace(tenant, "orphan")

    _grant(tenant, admin, anchor, ROLE_ADMIN)

    _run_backfill()
    first = _active_roles(orphan)
    _run_backfill()

    assert _active_roles(orphan) == first == [(admin.id, ROLE_ADMIN)]
