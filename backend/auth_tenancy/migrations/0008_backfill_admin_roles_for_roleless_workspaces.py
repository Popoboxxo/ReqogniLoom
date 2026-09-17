"""GitHub #103 — Backfill admin roles into workspaces that have none.

Companion data migration to the workspace-scoped role resolution fix.

Why this is needed
------------------
Role resolution on the REST path used to aggregate ``UserRole`` across the whole
tenant, so a workspace with zero role assignments was still fully usable by
anyone holding a role anywhere in the tenant. That masked a gap: before #232 /
PR #241, ``create_workspace`` / ``clone_workspace`` did not grant the creator a
role, so every workspace created before that fix has zero ``UserRole`` rows.

Once roles are resolved against the targeted workspace, those role-less
workspaces would answer 403 for every caller — nobody could even re-assign
roles, because the RBAC gate rejects the request before the service runs.

What it does
------------
For every workspace with no active (non-suspended) role assignment, grant
``admin`` to every user who already holds an active ``admin`` role somewhere in
the same tenant.

Why that grant is the safe choice:

* No new authority. Under the old tenant-wide aggregation those admins were
  already effective admins in these workspaces; this only makes the pre-existing
  grant explicit, per-workspace and auditable.
* No lockout. Every affected workspace keeps at least one admin who can then
  assign the correct per-workspace roles.
* The escalation is still removed. Editor/viewer/approver assignments are NOT
  backfilled, so non-admin roles stop leaking across workspaces — which is the
  actual vulnerability.

Tenants with no active admin anywhere are left untouched: there is no identity
that could legitimately be promoted, and such a workspace had no administrator
before either.

``assigned_by`` is left NULL to mark these as system-generated grants rather
than an action attributable to a user.

Reverse is a no-op: the created rows are indistinguishable from legitimate
manual assignments once applied, and deleting them could remove grants an admin
has since come to rely on.
"""
from __future__ import annotations

from django.db import migrations

ROLE_ADMIN = "admin"


def backfill_admin_roles(apps, schema_editor):
    """Grant ``admin`` in every role-less workspace to the tenant's admins."""
    Workspace = apps.get_model("persistence", "Workspace")
    UserRole = apps.get_model("auth_tenancy", "UserRole")

    # Historical models expose plain managers, so no tenant context is needed
    # (and must not be assumed) inside a migration.
    active_roles = UserRole.objects.filter(suspended_at__isnull=True)

    workspaces_with_roles = set(
        active_roles.values_list("workspace_id", flat=True).distinct()
    )

    # tenant_id -> [user_id, ...] holding an active admin role in that tenant.
    admins_by_tenant: dict[object, set] = {}
    for tenant_id, user_id in active_roles.filter(role=ROLE_ADMIN).values_list(
        "tenant_id", "user_id"
    ):
        admins_by_tenant.setdefault(tenant_id, set()).add(user_id)

    new_rows = []
    for workspace_id, tenant_id in Workspace.objects.values_list("id", "tenant_id"):
        if workspace_id in workspaces_with_roles:
            continue
        for user_id in admins_by_tenant.get(tenant_id, ()):
            new_rows.append(
                UserRole(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role=ROLE_ADMIN,
                    suspended_at=None,
                    assigned_by_id=None,
                )
            )

    if new_rows:
        # ignore_conflicts guards the uq_userrole_ws_user_role constraint in case
        # a concurrent/partial run already created some of these rows.
        UserRole.objects.bulk_create(new_rows, ignore_conflicts=True, batch_size=500)


def noop_reverse(apps, schema_editor):
    """Intentionally does not revert the grants (see module docstring)."""


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0007_flip_enforcement_authoritative"),
        ("persistence", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_admin_roles, noop_reverse),
    ]
