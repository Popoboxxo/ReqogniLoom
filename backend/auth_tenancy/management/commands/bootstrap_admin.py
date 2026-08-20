"""
ARCH-L1-011 AuthAndTenancy — mandatory admin bootstrap command (REQ-L1-010).

Provisions the minimum data a fresh ReqFlow instance needs before anyone can log
in: the base tenant, base workspace, admin user and admin role. This command is
meant to run automatically at container start, after ``migrate`` and before the
backend serves traffic (see the ``bootstrap`` service in docker-compose.yml).

Idempotent and CREATE-ONLY with respect to the password: the admin password is
set exactly once, when the user is first created, and is never rewritten on
subsequent runs. This mirrors Django's ``createsuperuser --noinput`` semantics
and prevents an admin who changed their password via the UI/API from being
silently reset back to the env-var value on every restart or deploy.

Configuration (env vars, mirroring the DJANGO_SUPERUSER_* pattern):

* ``SYSTEM_ADMIN_USERNAME`` — optional, defaults to ``admin``.
* ``SYSTEM_ADMIN_EMAIL``    — optional, defaults to ``admin@demo.local``.
* ``SYSTEM_ADMIN_PASSWORD`` — required *only when the admin user must be created*.

Fail-fast vs. skip decision (deliberate):
    We fail-fast, but scoped to the moment the admin actually has to be created.
    A missing password is only fatal when there is no admin user yet — creating
    a login-capable account without an explicit password (or inventing a
    default) would be a security hole, so we refuse loudly instead. Once the
    admin exists, the password env var is no longer needed and the command is a
    safe no-op, so an existing deployment that rotated its admin password and
    cleared the env var still boots. Skipping silently on a fresh system was
    rejected: it reintroduces the exact 401-on-first-login failure this command
    exists to prevent, only hidden behind a log line.

Usage:
    python manage.py bootstrap_admin
"""
from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from application.workspace_provisioning import provision_workspace_defaults_scoped
from auth_tenancy.provisioning import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USERNAME,
    ProvisioningError,
    provision_admin,
)
from persistence.models import User

# provision_admin()'s base workspace is always created with active_tier
# "extended" (see auth_tenancy.provisioning._ensure_workspace) -- matches
# application.self_init._DEFAULT_WORKSPACE_TIER, the same constant for the
# same reason.
_WORKSPACE_TIER = "extended"


class Command(BaseCommand):
    """Mandatory, idempotent, create-only admin/tenant/workspace bootstrap."""

    help = (
        "Provision the base tenant, workspace, admin user and admin role so a "
        "fresh instance is immediately usable. Create-only on the password "
        "(REQ-L1-010)."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        """Bootstrap the base data, failing fast only when it must create an
        admin without a password."""
        username = os.environ.get("SYSTEM_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)
        email = os.environ.get("SYSTEM_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
        # No default: an unset password is only tolerated once the admin exists.
        password = os.environ.get("SYSTEM_ADMIN_PASSWORD")

        admin_exists = User.objects.filter(username=username).exists()
        if not admin_exists and not password:
            raise CommandError(
                f"SYSTEM_ADMIN_PASSWORD is not set and no admin user "
                f"'{username}' exists yet. Refusing to create a login-capable "
                "admin without an explicit password. Set SYSTEM_ADMIN_PASSWORD "
                "and restart to bootstrap the admin account."
            )

        try:
            result = provision_admin(
                username=username,
                email=email,
                password=password,
                reset_password=False,
            )
        except ProvisioningError as exc:  # defensive: race between check + write
            raise CommandError(str(exc)) from exc

        # Issue #41 (same root cause as seed_demo's fix): provision_admin()
        # never seeded workflow definitions on the workspace it creates --
        # left `states: []`/`transitions: []` (initialized=true, but empty)
        # on every fresh instance's base workspace until someone separately
        # initialized each entity type's workflow via the API. This command
        # is the *mandatory* bootstrap (see module docstring), so this gap
        # hit every fresh deployment, not just local dev via seed_demo.
        provision_workspace_defaults_scoped(
            workspace_id=result.workspace.id,
            tenant_id=result.tenant.id,
            requirement_preset=_WORKSPACE_TIER,
        )

        if result.user_created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Bootstrapped admin user '{username}' and base workspace."
                )
            )
        else:
            self.stdout.write(
                f"Admin user '{username}' already exists — password left "
                "unchanged, base data ensured."
            )
