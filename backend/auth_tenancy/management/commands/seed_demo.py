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

from application.attribute_bootstrap import bootstrap_attribute_definitions_for_tenant
from application.workspace_provisioning import provision_workspace_defaults_scoped
from auth_tenancy.provisioning import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USERNAME,
    provision_admin,
)

_DEFAULT_ADMIN_PASSWORD = "admin12345"

# provision_admin()'s base workspace is always created with active_tier
# "extended" (see auth_tenancy.provisioning._ensure_workspace) -- matches
# application.self_init._DEFAULT_WORKSPACE_TIER, the same constant for the
# same reason.
_WORKSPACE_TIER = "extended"


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

        # Issue #41: provision_admin() creates the tenant/workspace/user but
        # never seeded workflow definitions -- a workspace it provisions was
        # left with `states: []`/`transitions: []` (initialized=true, but
        # empty) until someone separately called POST
        # /api/v1/workflows/definition/initialize/ per entity type. Same fix
        # application.self_init.run_self_init() already applies after its own
        # provision_admin() call, for the same reason.
        provision_workspace_defaults_scoped(
            workspace_id=result.workspace.id,
            tenant_id=result.tenant.id,
            requirement_preset=_WORKSPACE_TIER,
        )

        # Issue #29: a workspace provisioned only via seed_demo had ZERO
        # GlobalAttributeDefinition rows, so the custom-fields/attribute feature
        # rendered empty ("No global attribute definition for '<type>/<preset>'").
        # application.self_init.run_self_init() already bootstraps them for its
        # own tenants; reuse the same shared helper here so the two provisioning
        # paths cannot diverge. It is idempotent (get-then-initialize), so a
        # re-run creates no duplicates.
        #
        # Intentional fail-loud divergence from self_init: that path runs inside
        # post_migrate and must never raise (its wrapper catches and logs so a
        # failure cannot abort the whole `migrate`). This call deliberately lets
        # an exception propagate — seed_demo is operator-invoked, so a bootstrap
        # failure should fail loudly with a non-zero exit instead of silently
        # shipping an empty attribute set. handle() runs outside a transaction,
        # so if it raises, the tenant/workspace/user provisioned above stay
        # committed; only the bootstrap command's own atomic block rolls back.
        # The nested call_command also prints its own
        # "bootstrap_attribute_definitions: N created, ..." SUCCESS line to
        # stdout, in addition to seed_demo's final message below.
        bootstrap_attribute_definitions_for_tenant(result.tenant.id)

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
