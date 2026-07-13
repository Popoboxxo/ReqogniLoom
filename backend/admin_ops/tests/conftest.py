"""
admin_ops — shared test fixtures (REQ-L1-046).

Provides:

* ``tenant_a`` — an active tenant (re-exported from auth_tenancy's conftest).
* ``user_a``   — a user in tenant_a.
* ``admin_user`` / ``regular_user`` / ``superuser`` — fixture users covering
  the three auth surface levels used by the admin-ops services.
* ``admin_ctx`` / ``regular_ctx`` / ``viewer_ctx`` — :class:`AuthContext`
  for the admin, editor and viewer users, so the admin gate is exercised
  end-to-end.
* ``active_tenant`` — re-exported context manager that wires both the
  thread-local TenantContext and the PostgreSQL ``app.current_tenant``
  session variable used by the audit log.
* An autouse ``_isolate_backup_files`` fixture that points the backup
  file storage at a per-test temporary directory so no test ever
  pollutes the working tree.
"""
from __future__ import annotations

from typing import Iterator

import pytest
from django.test import override_settings

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER
from persistence.models import Tenant, User


# Re-export auth_tenancy fixtures so a single `from admin_ops.tests.conftest`
# import is enough for the test files.
from auth_tenancy.tests.conftest import active_tenant, tenant_a  # noqa: F401


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db, tenant_a: Tenant) -> User:
    """A regular user with the ``admin`` role in tenant_a.

    Distinct from a Django ``is_superuser`` — RBAC is enforced at the
    service layer via :class:`AuthContext`, not via the legacy
    ``is_superuser`` flag.
    """
    return User.objects.create(
        username="admin-1",
        email="admin-1@a.test",
        tenant=tenant_a,
    )


@pytest.fixture
def regular_user(db, tenant_a: Tenant) -> User:
    """A non-admin user (editor role) in tenant_a."""
    return User.objects.create(
        username="editor-1",
        email="editor-1@a.test",
        tenant=tenant_a,
    )


@pytest.fixture
def superuser(db, tenant_a: Tenant) -> User:
    """A Django superuser — used to verify the gate is RBAC-driven, not
    :attr:`is_superuser`-driven.
    """
    return User.objects.create(
        username="super-1",
        email="super-1@a.test",
        tenant=tenant_a,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def admin_ctx(admin_user: User, tenant_a: Tenant) -> AuthContext:
    """An AuthContext carrying the ``admin`` role."""
    return AuthContext(
        user_id=admin_user.id,
        tenant_id=tenant_a.id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def regular_ctx(regular_user: User, tenant_a: Tenant) -> AuthContext:
    """An AuthContext carrying the ``editor`` role (no admin)."""
    return AuthContext(
        user_id=regular_user.id,
        tenant_id=tenant_a.id,
        active_roles=(ROLE_EDITOR,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def viewer_ctx(regular_user: User, tenant_a: Tenant) -> AuthContext:
    """An AuthContext carrying only the ``viewer`` role."""
    return AuthContext(
        user_id=regular_user.id,
        tenant_id=tenant_a.id,
        active_roles=(ROLE_VIEWER,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def empty_roles_ctx(regular_user: User, tenant_a: Tenant) -> AuthContext:
    """An AuthContext with no roles at all (no admin)."""
    return AuthContext(
        user_id=regular_user.id,
        tenant_id=tenant_a.id,
        active_roles=(),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


# ---------------------------------------------------------------------------
# File-system isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_backup_files(tmp_path) -> Iterator[None]:
    """Point MEDIA_ROOT at a per-test tmp directory for the whole test run.

    The backup services derive their on-disk directory from
    ``settings.MEDIA_ROOT``; overriding it here guarantees that no
    service write ever escapes into the project working tree. The
    override is scoped to the test, so subsequent tests start from the
    original settings.
    """
    media_root = tmp_path / "media"
    media_root.mkdir()
    with override_settings(MEDIA_ROOT=str(media_root)):
        yield


@pytest.fixture
def tmp_backups_dir() -> str:
    """Return the absolute path of the per-test MEDIA_ROOT used by the
    autouse :func:`_isolate_backup_files` fixture.

    Exposed as a named fixture so tests can assert that backup files
    landed in the expected place without re-deriving the path.
    """
    from django.conf import settings

    return str(settings.MEDIA_ROOT)
