"""
ARCH-L1-011 AuthAndTenancy — OPTIONAL demo seed command (REQ-L1-010).

This command is **optional**. The base data required for login (tenant,
workspace, admin user, admin role) plus the workspace's default workflow and
attribute definitions are provisioned automatically by
``application.self_init`` (the ``post_migrate`` hook that runs inside the
``migrate`` service of docker-compose.yml). ``seed_demo`` is kept as a
convenience entry point for local development and the Playwright E2E suite: it
delegates to the shared :func:`auth_tenancy.provisioning.provision_admin` helper
so a developer who runs only ``seed_demo`` still gets a working login.

Unlike ``bootstrap_admin`` this command may re-apply a known demo password on
demand via ``--reset-password`` — a dev-only convenience for recovering demo
credentials. Without that flag it is also create-only and never rewrites an
existing password.

The password is read from ``SYSTEM_ADMIN_PASSWORD`` (falling back to the legacy
``DEMO_ADMIN_PASSWORD`` for backward compatibility), so it stays aligned with the
mandatory bootstrap configuration. The built-in demo password is only used with
the explicit, DEBUG-independent opt-in ``SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1``
(issue #89): without it — and without an env password — the command refuses to
run instead of provisioning a known credential.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --reset-password   # force demo password
"""
from __future__ import annotations

import os
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from application.attribute_bootstrap import bootstrap_attribute_definitions_for_tenant
from application.workspace_provisioning import provision_workspace_defaults_scoped
from auth_tenancy.provisioning import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USERNAME,
    provision_admin,
)

_DEFAULT_ADMIN_PASSWORD = "admin12345"

# Issue #89: the built-in demo password is a known credential, so using it is an
# explicit opt-in — DELIBERATELY independent of DEBUG. The dev overlay sets
# DEBUG=True while still being reachable/productive, so gating on `not DEBUG`
# would leave a production-shaped deployment that merely forgot to flip DEBUG
# with a publicly known admin password.
_ALLOW_DEFAULT_PASSWORD_ENV = "SEED_DEMO_ALLOW_DEFAULT_PASSWORD"
_REFUSE_DEFAULT_PASSWORD_MESSAGE = (
    "seed_demo refuses the built-in demo password; set SYSTEM_ADMIN_PASSWORD "
    "or SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1 (test only)."
)

# provision_admin()'s base workspace is always created with active_tier
# "extended" (see auth_tenancy.provisioning._ensure_workspace) -- matches
# application.self_init._DEFAULT_WORKSPACE_TIER, the same constant for the
# same reason.
_WORKSPACE_TIER = "extended"


class Command(BaseCommand):
    """Optionally seed the demo tenant, workspace, admin user and admin role."""

    help = (
        "Optionally seed the demo tenant, workspace and admin user for local "
        "development / E2E. Base login data is provisioned by "
        "application.self_init during migrate; this command is not required "
        "(REQ-L1-010)."
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
        password = os.environ.get("SYSTEM_ADMIN_PASSWORD") or os.environ.get(
            "DEMO_ADMIN_PASSWORD"
        )
        using_default_password = False
        if not password:
            # Issue #89: no credential configured -> only the built-in demo
            # password is left, and that needs the explicit opt-in. Applies to
            # --reset-password too (it re-applies this same resolved password).
            if os.environ.get(_ALLOW_DEFAULT_PASSWORD_ENV) != "1":
                raise CommandError(_REFUSE_DEFAULT_PASSWORD_MESSAGE)
            password = _DEFAULT_ADMIN_PASSWORD
            using_default_password = True

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
            # Issue #89: never echo a configured secret. The password is only
            # printed when it is the built-in demo default, which the operator
            # explicitly opted into above.
            shown_password = (
                _DEFAULT_ADMIN_PASSWORD
                if using_default_password
                else "<password from SYSTEM_ADMIN_PASSWORD>"
            )
            self.stdout.write(
                "Login: POST /api/v1/auth/login/ "
                f'{{"username": "{username}", "password": "{shown_password}"}}'
            )
        else:
            self.stdout.write(
                f"Admin user '{username}' already existed — password left "
                "unchanged (use --reset-password to force the demo password)."
            )
