"""
ARCH-L1-011 AuthAndTenancy — OPTIONAL demo seed command (REQ-L1-010).

This command is **optional**. The base data required for login (tenant,
workspace, admin user, admin role) is provisioned automatically at container
start by ``bootstrap_admin`` (see the ``bootstrap`` service in
docker-compose.yml). ``seed_demo`` is kept as a convenience entry point for
local development and the Playwright E2E suite: it delegates to the shared
:func:`auth_tenancy.provisioning.provision_admin` helper so a developer who runs
only ``seed_demo`` still gets a working login.

Unlike ``bootstrap_admin`` this command may re-apply a known demo password on
demand via ``--reset-password`` — a dev-only convenience for recovering demo
credentials. Without that flag it is also create-only and never rewrites an
existing password.

The password is read from ``SYSTEM_ADMIN_PASSWORD`` (falling back to the legacy
``DEMO_ADMIN_PASSWORD`` for backward compatibility, then to a fixed demo
default), so it stays aligned with the mandatory bootstrap configuration.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --reset-password   # force demo password
"""
from __future__ import annotations

import os
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from auth_tenancy.provisioning import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USERNAME,
    provision_admin,
)

_DEFAULT_ADMIN_PASSWORD = "admin12345"


class Command(BaseCommand):
    """Optionally seed the demo tenant, workspace, admin user and admin role."""

    help = (
        "Optionally seed the demo tenant, workspace and admin user for local "
        "development / E2E. Base login data is provisioned by bootstrap_admin "
        "at startup; this command is not required (REQ-L1-010)."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Register the optional ``--reset-password`` flag."""
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help=(
                "Re-apply the demo password even if the admin user already "
                "exists (dev-only convenience; off by default)."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Provision the demo data set and print a login hint."""
        username = os.environ.get("SYSTEM_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)
        email = os.environ.get("SYSTEM_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
        password = (
            os.environ.get("SYSTEM_ADMIN_PASSWORD")
            or os.environ.get("DEMO_ADMIN_PASSWORD")
            or _DEFAULT_ADMIN_PASSWORD
        )

        result = provision_admin(
            username=username,
            email=email,
            password=password,
            reset_password=bool(options.get("reset_password")),
        )

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        if result.password_set:
            self.stdout.write(
                "Login: POST /api/v1/auth/login/ "
                f'{{"username": "{username}", "password": "{password}"}}'
            )
        else:
            self.stdout.write(
                f"Admin user '{username}' already existed — password left "
                "unchanged (use --reset-password to force the demo password)."
            )
