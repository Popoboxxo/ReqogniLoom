"""
ARCH-L1-011 AuthAndTenancy — demo seed command (REQ-L1-010).

Idempotently provisions the minimum data needed to exercise the password-login
flow end-to-end:

* a default ``Tenant`` (slug ``demo``),
* a default ``Workspace`` within that tenant,
* an admin ``User`` (username ``admin``) with a hashed password, and
* an admin ``UserRole`` for that user in the workspace.

Re-running the command is safe: every entity is created via get-or-update keyed on
a stable natural key, so a second run makes no duplicate rows. The admin username,
email and password are configurable via the ``SYSTEM_ADMIN_USERNAME``,
``SYSTEM_ADMIN_EMAIL`` and ``SYSTEM_ADMIN_PASSWORD`` env vars (defaults ``admin``,
``admin@demo.local`` and ``admin12345`` respectively) and are re-applied on every
run so the demo credentials always work.

Usage:
    python manage.py seed_demo
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from django.core.management.base import BaseCommand

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from presets.models import WorkspacePresetConfig

_DEMO_TENANT_SLUG = "demo"
_DEMO_TENANT_NAME = "Demo Tenant"
_DEMO_WORKSPACE_NAME = "Demo Workspace"
# Stable, deterministic id for the demo workspace so external clients (notably
# the Playwright E2E suite in e2e/helpers/auth.ts, which hard-codes
# SEEDED_WORKSPACE_ID) always target the exact workspace this command seeds.
# Without a fixed id, get_or_create assigns a random UUID on every fresh
# database, which makes list endpoints return an empty (still-valid) result
# while write/create and preset-gated endpoints 404 because the referenced
# workspace does not exist.
_DEMO_WORKSPACE_ID = uuid.UUID("6d20f0b9-d2cf-46a0-b916-79f8b417210f")
_SYSTEM_ADMIN_USERNAME = os.environ.get("SYSTEM_ADMIN_USERNAME", "admin")
_SYSTEM_ADMIN_EMAIL = os.environ.get("SYSTEM_ADMIN_EMAIL", "admin@demo.local")
_DEFAULT_ADMIN_PASSWORD = "admin12345"


class Command(BaseCommand):
    """Seed an idempotent demo tenant, workspace, admin user and admin role."""

    help = "Idempotently seed a demo tenant, workspace and admin user (REQ-L1-010)."

    def handle(self, *args: Any, **options: Any) -> None:
        """Create or update the demo data set and print a login hint."""
        password = os.environ.get("SYSTEM_ADMIN_PASSWORD", _DEFAULT_ADMIN_PASSWORD)

        tenant = self._ensure_tenant()
        # Workspace and UserRole are tenant-scoped; activate the tenant so the
        # default (tenant-isolating) manager resolves to the right scope.
        set_request_tenant(tenant.id)
        try:
            user = self._ensure_admin_user(tenant, password)
            workspace = self._ensure_workspace(tenant)
            self._ensure_admin_role(tenant, user, workspace)
        finally:
            clear_request_tenant()

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        self.stdout.write(
            "Login: POST /api/v1/auth/login/ "
            f'{{"username": "{_SYSTEM_ADMIN_USERNAME}", "password": "{password}"}}'
        )

    def _ensure_tenant(self) -> Tenant:
        """Get-or-create the demo tenant (keyed on slug)."""
        tenant, _created = Tenant.objects.get_or_create(
            slug=_DEMO_TENANT_SLUG,
            defaults={"name": _DEMO_TENANT_NAME, "is_active": True},
        )
        return tenant

    def _ensure_admin_user(self, tenant: Tenant, password: str) -> User:
        """Get-or-create the admin user and (re)apply the demo password.

        Uses the unscoped manager: ``User`` is not tenant-scoped.
        Sets is_staff=True, is_superuser=True so the admin user can access
        the Django admin site at /admin/ (REQ-L1-010).
        """
        user, _created = User.objects.get_or_create(
            username=_SYSTEM_ADMIN_USERNAME,
            defaults={
                "email": _SYSTEM_ADMIN_EMAIL,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
                "tenant": tenant,
            },
        )
        # Keep the user attached to the demo tenant, active and staff across reruns.
        user.tenant = tenant
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save(
            update_fields=[
                "tenant",
                "is_active",
                "is_staff",
                "is_superuser",
                "password",
                "modified_at",
            ]
        )
        return user

    def _ensure_workspace(self, tenant: Tenant) -> Workspace:
        """Get-or-create the demo workspace within the active tenant."""
        workspace, _created = Workspace.objects.get_or_create(
            tenant=tenant,
            name=_DEMO_WORKSPACE_NAME,
            defaults={"id": _DEMO_WORKSPACE_ID, "preset": {"name": "extended"}},
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
        self, tenant: Tenant, user: User, workspace: Workspace
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
