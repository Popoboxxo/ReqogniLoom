"""
Shared test-factory helpers for tenant/user/workspace/requirement setup and
auth-context construction, used across app test suites (not app-specific).

This module exists so every app's tests can share a single, real convention
for building tenant-scoped fixtures via plain function calls (as opposed to
pytest fixtures declared in a ``conftest.py``), which is what's needed when a
test module wants these helpers WITHOUT pytest fixture injection.

IMPORTANT — ``active_tenant()`` here is deliberately a DIFFERENT SHAPE from
``auth_tenancy.tests.conftest.active_tenant(tenant)``:

* ``auth_tenancy.tests.conftest.active_tenant(tenant)`` takes an EXISTING
  ``Tenant`` (created by a separate ``tenant_a`` pytest fixture) and only
  *activates* it for the duration of the ``with`` block. It is meant to be
  reused across several test methods that all share one fixture-created
  tenant.
* :func:`active_tenant` in THIS module is zero-arg: it CREATES a new
  ``Tenant`` row, activates it and yields it, all in one call — for tests
  that don't need a shared tenant fixture and just want
  ``with active_tenant() as tenant: ...`` inline in a test body.

Do not conflate the two; do not modify ``auth_tenancy/tests/conftest.py`` to
match this one.
"""
from __future__ import annotations

import contextlib
from typing import Iterator
from uuid import uuid4

from django.utils import timezone

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_EDITOR, TenantRole, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

# Password used for the throwaway users created by *_user_and_token(); these
# users only ever exist for the lifetime of a single test.
_FACTORY_PASSWORD = "factory-test-pass1"  # noqa: S105 - test-only fixture value


@contextlib.contextmanager
def active_tenant() -> Iterator[Tenant]:
    """Create a ``Tenant``, activate it, yield it, deactivate on exit.

    Self-contained: unlike
    ``auth_tenancy.tests.conftest.active_tenant(tenant)`` (which activates an
    ALREADY-created tenant fixture), this creates the ``Tenant`` row itself,
    so a test body can do ``with active_tenant() as tenant: ...`` without any
    pytest fixture wiring.
    """
    tenant = Tenant.objects.create(
        name=f"Factory Tenant {uuid4().hex[:8]}",
        slug=f"factory-tenant-{uuid4().hex[:12]}",
        is_active=True,
    )
    set_request_tenant(tenant.id)
    try:
        yield tenant
    finally:
        clear_request_tenant()


def make_user(tenant: Tenant, **kwargs) -> User:
    """Create a ``User`` in ``tenant``. ``kwargs`` override the defaults.

    ``User`` is not tenant-scoped at the DB-manager level (it has a nullable
    ``tenant`` FK, not ``TenantScopedModel``), so this does not require an
    active tenant context.
    """
    suffix = uuid4().hex[:12]
    defaults = {
        "username": f"user-{suffix}",
        "email": f"user-{suffix}@factory.test",
        "tenant": tenant,
    }
    defaults.update(kwargs)
    return User.objects.create(**defaults)


def make_workspace(tenant: Tenant, **kwargs) -> Workspace:
    """Create a ``Workspace`` in ``tenant``. ``kwargs`` override the defaults.

    ``Workspace`` is a ``TenantScopedModel``; call this inside an active
    tenant context (e.g. ``with active_tenant() as tenant:``).
    """
    defaults = {
        "tenant": tenant,
        "name": f"WS-{uuid4().hex[:8]}",
    }
    defaults.update(kwargs)
    return Workspace.objects.create(**defaults)


def assign_role(user: User, workspace: Workspace, role: str, *, suspended: bool = False) -> None:
    """Create a ``UserRole`` row for ``user`` in ``workspace`` with ``role``.

    ``role`` is one of the ``UserRole.ROLE_CHOICES`` values
    (``"editor"``/``"viewer"``/``"admin"``/``"approver"``). If
    ``suspended=True``, ``suspended_at`` is set to ``now()`` (soft-suspended,
    REQ-L2-AT-006 semantics); otherwise it stays ``None``.

    ``UserRole`` is a ``TenantScopedModel``; call this inside an active
    tenant context (e.g. ``with active_tenant() as tenant:``).
    """
    UserRole.objects.create(
        tenant=workspace.tenant,
        user=user,
        workspace=workspace,
        role=role,
        suspended_at=timezone.now() if suspended else None,
    )


def editor_ctx(tenant: Tenant, workspace: Workspace | None = None, *, user: User | None = None) -> AuthContext:
    """Return an ``AuthContext`` with the ``"editor"`` role.

    Uses ``user`` if given, else creates a fresh one. If ``workspace`` is
    given, also persists a matching ``UserRole`` row (requires an active
    tenant context, see :func:`assign_role`); if ``workspace`` is ``None``,
    only the in-memory ``AuthContext`` is built (no role row to persist —
    ``UserRole`` requires a workspace).
    """
    if user is None:
        user = make_user(tenant)
    if workspace is not None:
        assign_role(user, workspace, ROLE_EDITOR)
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        tenant_name=tenant.name,
        workspace_id=workspace.id if workspace else None,
    )


def ctx_for_user(
    tenant: Tenant,
    user: User,
    *,
    workspace: Workspace | None = None,
    roles: tuple[str, ...] = ("editor",),
) -> AuthContext:
    """Return an ``AuthContext`` for an EXISTING ``user``.

    Used when a test needs two contexts for two different pre-created users
    (e.g. permission-denial checks). If ``workspace`` is given, also persists
    a matching ``UserRole`` row per role in ``roles`` (requires an active
    tenant context, see :func:`assign_role`).
    """
    if workspace is not None:
        for role in roles:
            assign_role(user, workspace, role)
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=tuple(roles),
        auth_method=AuthMethod.BEARER_TOKEN,
        tenant_name=tenant.name,
        workspace_id=workspace.id if workspace else None,
    )


def _login_for_token(username: str, password: str) -> str:
    """POST to the real login endpoint and return the issued JWT."""
    # Imported lazily to keep this module importable in non-DRF-test contexts.
    from rest_framework.test import APIClient

    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert response.status_code == 200, response.content
    return response.json()["token"]


def admin_user_and_token(tenant: Tenant) -> tuple[User, str]:
    """Create a tenant-admin user, log in for real, return ``(user, token)``.

    Grants a tenant-wide ``TenantRole`` (admin) via the ``unscoped`` manager
    (mirrors ``admin_ops/tests/test_theme_palette_rest.py``'s ``_client_for``)
    so this works without requiring an already-active tenant context.
    """
    user = make_user(tenant)
    user.set_password(_FACTORY_PASSWORD)
    user.save(update_fields=["password"])
    TenantRole.unscoped.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    token = _login_for_token(user.username, _FACTORY_PASSWORD)
    return user, token


def editor_user_and_token(tenant: Tenant, workspace: Workspace | None = None) -> tuple[User, str]:
    """Create a non-admin (editor) user, log in for real, return ``(user, token)``.

    If ``workspace`` is given, grants a workspace-scoped ``UserRole``
    (editor) via the ``unscoped`` manager (same rationale as
    :func:`admin_user_and_token` — works without an already-active tenant
    context); otherwise the user has no workspace role at all.
    """
    user = make_user(tenant)
    user.set_password(_FACTORY_PASSWORD)
    user.save(update_fields=["password"])
    if workspace is not None:
        UserRole.unscoped.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
    token = _login_for_token(user.username, _FACTORY_PASSWORD)
    return user, token


def make_requirement(workspace: Workspace, **kwargs) -> Requirement:
    """Create a ``Requirement`` (with its backing ``Artifact``) in ``workspace``.

    ``kwargs`` override the ``Requirement`` defaults (e.g. ``title``,
    ``description``). Requires an active tenant context (both ``Artifact``
    and ``Requirement`` are ``TenantScopedModel``), matching the pattern in
    ``persistence/tests/test_tenant_isolation.py``.
    """
    tenant = workspace.tenant
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="requirement"
    )
    defaults = {
        "tenant": tenant,
        "artifact": artifact,
        "title": "Factory Requirement",
    }
    defaults.update(kwargs)
    return Requirement.objects.create(**defaults)


__all__ = [
    "active_tenant",
    "make_user",
    "make_workspace",
    "assign_role",
    "editor_ctx",
    "ctx_for_user",
    "admin_user_and_token",
    "editor_user_and_token",
    "make_requirement",
]
