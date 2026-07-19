"""
ARCH-L1-011 AuthAndTenancy — shared admin/tenant/workspace provisioning.

Single source of truth for the base data that a ReqFlow instance needs before
anyone can log in:

* a default ``Tenant`` (slug ``demo``),
* a default ``Workspace`` within that tenant (stable id + Extended preset),
* an admin ``User`` (``is_staff``/``is_superuser``), and
* an admin ``UserRole`` for that user in the workspace.

Two management commands build on this module:

* ``bootstrap_admin`` — mandatory, runs automatically at container start. It is
  strictly *create-only* with respect to the password (``reset_password=False``):
  the password is set once, when the user is first created, and is never touched
  again. This mirrors Django's ``createsuperuser --noinput`` semantics and avoids
  silently resetting an admin password that was changed via the UI/API on every
  restart or deploy.
* ``seed_demo`` — optional demo/example data for local development and E2E. It
  may opt into ``reset_password=True`` to re-apply a known demo password.

All operations are idempotent: entities are created via get-or-create keyed on a
stable natural key, so repeated runs never duplicate rows.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from presets.models import WorkspacePresetConfig

# Default identity of the base tenant/workspace. The workspace id is fixed and
# deterministic so external clients (notably the Playwright E2E suite in
# e2e/helpers/auth.ts, which hard-codes SEEDED_WORKSPACE_ID) always target the
# exact workspace this module provisions. Without a fixed id, get_or_create
# assigns a random UUID on every fresh database, which makes list endpoints
# return an empty (still-valid) result while write/create and preset-gated
# endpoints 404 because the referenced workspace does not exist.
DEFAULT_TENANT_SLUG = "demo"
DEFAULT_TENANT_NAME = "Demo Tenant"
DEFAULT_WORKSPACE_NAME = "Demo Workspace"
DEFAULT_WORKSPACE_ID = uuid.UUID("6d20f0b9-d2cf-46a0-b916-79f8b417210f")
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_EMAIL = "admin@demo.local"


@dataclass(frozen=True)
class ProvisionResult:
    """Outcome of a :func:`provision_admin` call.

    Attributes:
        tenant: The provisioned (or pre-existing) base tenant.
        workspace: The provisioned (or pre-existing) base workspace.
        user: The admin user.
        role: The admin ``UserRole`` binding user + workspace.
        user_created: ``True`` if the admin user was created by this call.
        password_set: ``True`` if this call wrote the user's password.
    """

    tenant: Tenant
    workspace: Workspace
    user: User
    role: UserRole
    user_created: bool
    password_set: bool


class ProvisioningError(Exception):
    """Raised when provisioning cannot proceed safely (e.g. missing password)."""


def provision_admin(
    *,
    username: str = DEFAULT_ADMIN_USERNAME,
    email: str = DEFAULT_ADMIN_EMAIL,
    password: str | None = None,
    reset_password: bool = False,
) -> ProvisionResult:
    """Idempotently provision the base tenant, workspace, admin user and role.

    The password is only written when the user is created, or when
    ``reset_password`` is explicitly ``True``. For an already-existing user with
    ``reset_password=False`` the stored password hash is left untouched — this is
    the create-only guarantee the mandatory bootstrap relies on.

    Args:
        username: Admin username (natural key for the user).
        email: Admin email, applied only when the user is created.
        password: Cleartext password. Required when the user must be created or
            when ``reset_password`` is set; ignored otherwise.
        reset_password: Force-rewrite the password even if the user exists.

    Returns:
        A :class:`ProvisionResult` describing what happened.

    Raises:
        ProvisioningError: If a password write is required but ``password`` is
            empty.
    """
    tenant = _ensure_tenant()
    # Workspace and UserRole are tenant-scoped; activate the tenant so the
    # default (tenant-isolating) manager resolves to the right scope.
    set_request_tenant(tenant.id)
    try:
        user, user_created = _ensure_admin_user(tenant, username, email)

        password_set = False
        if user_created or reset_password:
            if not password:
                raise ProvisioningError(
                    "A password is required to create or reset the admin user "
                    f"'{username}', but none was provided."
                )
            user.set_password(password)
            user.save(update_fields=["password", "modified_at"])
            password_set = True

        workspace = _ensure_workspace(tenant)
        role = _ensure_admin_role(tenant, user, workspace)
    finally:
        clear_request_tenant()

    return ProvisionResult(
        tenant=tenant,
        workspace=workspace,
        user=user,
        role=role,
        user_created=user_created,
        password_set=password_set,
    )


def _ensure_tenant() -> Tenant:
    """Get-or-create the base tenant (keyed on slug)."""
    tenant, _created = Tenant.objects.get_or_create(
        slug=DEFAULT_TENANT_SLUG,
        defaults={"name": DEFAULT_TENANT_NAME, "is_active": True},
    )
    return tenant


def _ensure_admin_user(
    tenant: Tenant, username: str, email: str
) -> tuple[User, bool]:
    """Get-or-create the admin user without ever touching its password here.

    Uses the unscoped manager: ``User`` is not tenant-scoped. On creation the
    user is staff + superuser so it can reach the Django admin site at /admin/
    (REQ-L1-010). For an existing user only the tenant link is self-healed (a
    user with no tenant cannot operate); staff/superuser/active flags are left
    as the operator configured them, so a deliberately deactivated admin is not
    silently re-enabled on every restart.

    Password handling is intentionally excluded from this helper and owned by
    :func:`provision_admin`, which enforces the create-only policy.
    """
    try:
        user = User.objects.get(username=username)
        created = False
    except User.DoesNotExist:
        user = User(
            username=username,
            email=email,
            is_active=True,
            is_staff=True,
            is_superuser=True,
            tenant=tenant,
        )
        # Persist with the model's default empty password (== "no usable
        # password"); provision_admin sets the real one immediately afterwards,
        # so no usable account ever exists without a deliberately assigned
        # password.
        user.save()
        return user, True

    if user.tenant_id != tenant.id:
        user.tenant = tenant
        user.save(update_fields=["tenant", "modified_at"])
    return user, created


def _ensure_workspace(tenant: Tenant) -> Workspace:
    """Get-or-create the base workspace within the active tenant."""
    workspace, _created = Workspace.objects.get_or_create(
        tenant=tenant,
        name=DEFAULT_WORKSPACE_NAME,
        defaults={"id": DEFAULT_WORKSPACE_ID, "preset": {"name": "extended"}},
    )
    # Ensure WorkspacePresetConfig matches the workspace.preset JSONField so
    # FeatureGateService uses the correct tier instead of defaulting to minimal.
    WorkspacePresetConfig.unscoped.update_or_create(
        workspace=workspace,
        defaults={
            "tenant": tenant,
            "active_tier": "extended",
            "terminology_profile": "se_mode",
            "downgrade_policy": "warn",
        },
    )
    return workspace


def _ensure_admin_role(
    tenant: Tenant, user: User, workspace: Workspace
) -> UserRole:
    """Get-or-create the admin UserRole for the user in the workspace."""
    user_role, _created = UserRole.objects.get_or_create(
        user=user,
        workspace=workspace,
        role=ROLE_ADMIN,
        defaults={"tenant": tenant, "suspended_at": None},
    )
    if user_role.suspended_at is not None:
        user_role.suspended_at = None
        user_role.save(update_fields=["suspended_at", "modified_at"])
    return user_role
