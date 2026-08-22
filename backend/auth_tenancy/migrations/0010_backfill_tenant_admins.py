"""Backfill the first TenantRole(admin) for every existing tenant.

Companion migration to 0009_add_tenant_role: without this, every tenant
that existed before this deploy would have zero tenant-admins the moment
the last-admin invariant starts being enforced, permanently locking out
tenant-admin-only actions (user.create, tenant-admin assign/revoke) for
every pre-existing tenant.

Rule (deterministic, no manual step): for each Tenant, promote the User
holding the earliest-created active UserRole(role=admin, suspended_at=None)
across that tenant's workspaces. A tenant with zero workspace admins
(should not exist given 0008's own backfill, but guarded anyway) is left
without a row and must be handled manually — inventing an admin identity
would be worse than leaving a gap visible.

Reverse is a no-op, matching 0008's own reasoning: the created rows are
indistinguishable from legitimate manual assignments once applied.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

ROLE_ADMIN = "admin"


def backfill_tenant_admins(apps, schema_editor):
    """Promote each tenant's earliest workspace admin to tenant-admin."""
    Tenant = apps.get_model("persistence", "Tenant")
    TenantRole = apps.get_model("auth_tenancy", "TenantRole")
    UserRole = apps.get_model("auth_tenancy", "UserRole")

    # Historical models expose plain managers, so no tenant context is needed
    # (and must not be assumed) inside a migration — see 0008 for the same
    # pattern.
    for tenant_id in Tenant.objects.values_list("id", flat=True):
        if TenantRole.objects.filter(tenant_id=tenant_id, role=ROLE_ADMIN).exists():
            continue
        earliest_admin_role = (
            UserRole.objects.filter(
                tenant_id=tenant_id,
                role=ROLE_ADMIN,
                suspended_at__isnull=True,
                # Fix round 3 (I-2): a deactivated user must never be
                # selected as a tenant's backfilled admin — a
                # `UserRole(admin)` row survives `User.is_active=False`
                # (deactivation only flips the account flag, it does not
                # touch role rows), so without this filter the migration
                # could promote a user who can no longer even
                # authenticate, leaving the tenant with a TenantRole(admin)
                # row that satisfies the last-admin invariant while being
                # functionally useless.
                user__is_active=True,
            )
            .order_by("created_at")
            .first()
        )
        if earliest_admin_role is None:
            # Same fallback as a tenant with zero workspace admins at all
            # (module docstring): don't invent an admin identity, leave the
            # gap visible and handled manually.
            logger.warning(
                "0010_backfill_tenant_admins: tenant %s has no active "
                "workspace admin held by an active user — left without a "
                "backfilled TenantRole(admin); handle manually.",
                tenant_id,
            )
            continue
        TenantRole.objects.create(
            tenant_id=tenant_id,
            user_id=earliest_admin_role.user_id,
            role=ROLE_ADMIN,
            assigned_by=None,
        )


def noop_reverse(apps, schema_editor):
    """Intentionally does not revert the grants (see module docstring)."""


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0009_add_tenant_role"),
    ]

    operations = [
        migrations.RunPython(backfill_tenant_admins, noop_reverse),
    ]
