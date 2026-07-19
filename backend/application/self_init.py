"""First-start self-initialisation of a fresh deployment (REQ-188).

Replaces the two former, easy-to-forget bootstrap mechanisms — the dedicated
``bootstrap`` docker-compose service (``manage.py bootstrap_admin``, admin only)
and the manual ``provision_workflow_definitions`` command (workflows only) — with
a single self-provisioning step that runs automatically at first start and
establishes BOTH the admin account AND the base workspace's default workflow /
permission definitions.

Trigger (see ``application.apps.ApplicationConfig.ready``): a ``post_migrate``
receiver, connected with the ``application`` app config as ``sender`` so it fires
exactly once per ``migrate`` invocation. In docker-compose only the one-shot
``migrate`` service runs migrations, so this executes in a single process, once
per deploy — no cross-worker race with the ``backend``/``celery`` containers,
which never migrate. All work is idempotent (get-or-create throughout), so a
re-run on an already-initialised database is a safe no-op.

Configuration mirrors the former ``bootstrap`` service (env vars):

* ``SYSTEM_ADMIN_USERNAME`` — optional, defaults to ``admin``.
* ``SYSTEM_ADMIN_EMAIL``    — optional, defaults to ``admin@demo.local``.
* ``SYSTEM_ADMIN_PASSWORD`` — required *only when the admin must be created*.

Missing-password handling differs deliberately from the old ``bootstrap_admin``
command: that command ran in its own container where a non-zero exit was the
intended failure signal, so it raised ``CommandError``. Here the code runs inside
``post_migrate``; raising would abort the whole ``migrate`` step (a far larger
blast radius). Instead, a fresh database with no ``SYSTEM_ADMIN_PASSWORD`` is
logged loudly and skipped, leaving migrations intact. The create-only password
guarantee is unchanged: an existing admin's password is never rewritten.
"""
from __future__ import annotations

import logging
import os

from auth_tenancy.provisioning import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USERNAME,
    ProvisioningError,
    provision_admin,
)
from persistence.models import User
from presets.models import WorkspacePresetConfig

from application.workspace_provisioning import (
    provision_workspace_defaults_scoped,
)

logger = logging.getLogger("reqflow")

# Fallback tier for the base workspace's Requirement workflow if — for any
# reason — the WorkspacePresetConfig cannot be read. provision_admin creates the
# base workspace as "extended", so this matches the expected default.
_DEFAULT_WORKSPACE_TIER = "extended"


def run_self_init() -> None:
    """Provision admin + base-workspace defaults on a fresh database (REQ-188).

    Idempotent. Safe to call on every ``migrate``; only a genuinely fresh
    database (no admin user) performs creating work, and even then repeated runs
    converge to the same state.
    """
    username = os.environ.get("SYSTEM_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)
    email = os.environ.get("SYSTEM_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    # No default: an unset password is only tolerated once the admin exists.
    password = os.environ.get("SYSTEM_ADMIN_PASSWORD")

    admin_exists = User.objects.filter(username=username).exists()
    if not admin_exists and not password:
        # Fresh database but no password to create the admin with. Do NOT raise:
        # this runs inside post_migrate and must not abort the migrate step.
        logger.error(
            "Self-init skipped: SYSTEM_ADMIN_PASSWORD is not set and no admin "
            "user '%s' exists yet. Set SYSTEM_ADMIN_PASSWORD and restart to "
            "provision the admin account and base workspace (REQ-188).",
            username,
        )
        return

    try:
        result = provision_admin(
            username=username,
            email=email,
            password=password,
            reset_password=False,
        )
    except ProvisioningError as exc:  # defensive: race between check + write
        logger.error("Self-init admin provisioning failed: %s", exc)
        return

    requirement_preset = _resolve_workspace_tier(result.workspace.id)

    # Seed the base workspace's default workflows + permission defaults so a
    # fresh instance is workflow-complete without any manual command. This is the
    # gap the old bootstrap service left open: provision_admin creates the
    # workspace but never seeded its workflows.
    provision_workspace_defaults_scoped(
        workspace_id=result.workspace.id,
        tenant_id=result.tenant.id,
        requirement_preset=requirement_preset,
    )

    if result.user_created:
        logger.info(
            "Self-init: provisioned admin '%s', base workspace and default "
            "workflow/permission definitions (REQ-188).",
            username,
        )
    else:
        logger.info(
            "Self-init: admin '%s' already present; ensured base workspace "
            "workflow/permission definitions (REQ-188).",
            username,
        )


def _resolve_workspace_tier(workspace_id) -> str:
    """Return the active preset tier of the base workspace for its Requirement
    workflow, falling back to ``extended`` if the config row is missing."""
    config = WorkspacePresetConfig.unscoped.filter(
        workspace_id=workspace_id
    ).first()
    if config and config.active_tier:
        return config.active_tier
    return _DEFAULT_WORKSPACE_TIER


__all__ = ["run_self_init"]
