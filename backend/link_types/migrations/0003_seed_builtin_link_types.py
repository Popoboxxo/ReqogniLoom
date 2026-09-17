"""Backfill the eight built-in link types for every pre-existing tenant.

Workspaces created from now on get their rows from
``application.workspace_provisioning`` (Task 7). This migration covers
everything that existed before that call did.

Both ``lt_*`` tables carry FORCE ROW LEVEL SECURITY (``0002_rls_policies``),
which binds the table owner too, so a blind cross-tenant write is impossible:
the migration iterates tenants and arms ``app.current_tenant`` per tenant
before touching either table — the same shape ``se_metrics.aggregator`` uses
for its worker threads. ``pl_tenant`` itself is deliberately outside RLS
(``persistence/0003_rls_policies``), so enumerating tenants needs no arming
and cannot be silently blinded; ``pl_workspace`` is read inside the armed
window.

This is why the house ``SET LOCAL row_security = off`` guard is *not* used
here: with the correct tenant armed the policy is satisfied, so the migration
also works under a non-``BYPASSRLS`` owner, which ``row_security = off``
would turn into a hard error.

Idempotent: ``get_or_create`` throughout, so a re-run — or a run against a
database where some workspaces were already provisioned — adds only what is
missing and never overwrites a customized row.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def _arm(schema_editor, tenant_id) -> None:
    """Point the RLS policies at *tenant_id* for the rest of this transaction."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def _disarm(schema_editor) -> None:
    """Clear the tenant GUC again so no later statement inherits it."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def seed_builtin_link_types(apps, schema_editor):
    """Create the missing global templates and workspace rows, tenant by tenant."""
    from link_types.migrations._seed_helpers import seed_tenant

    Tenant = apps.get_model("persistence", "Tenant")
    Workspace = apps.get_model("persistence", "Workspace")

    total_globals = 0
    total_rows = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            workspace_ids = list(
                Workspace.objects.filter(tenant_id=tenant_id).values_list(
                    "id", flat=True
                )
            )
            globals_created, rows_created = seed_tenant(tenant_id, workspace_ids)
            total_globals += globals_created
            total_rows += rows_created
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog seed: %d global templates, %d workspace rows created.",
        total_globals,
        total_rows,
    )


def unseed(apps, schema_editor):
    """Reverse: drop only the untouched built-in rows.

    A customized row is a user edit, not migration output, so it survives a
    rollback. Runs per tenant with the same arming as the forward direction —
    the RLS policy has no "all tenants" mode, so an unarmed delete would
    quietly remove nothing under a non-``BYPASSRLS`` role.
    """
    from link_types.builtin import BUILTIN_LINK_TYPES

    Tenant = apps.get_model("persistence", "Tenant")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )
    keys = list(BUILTIN_LINK_TYPES)

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            WorkspaceLinkTypeDefinition.objects.filter(
                tenant_id=tenant_id, key__in=keys, is_customized=False
            ).delete()
            GlobalLinkTypeDefinition.objects.filter(
                tenant_id=tenant_id, key__in=keys
            ).delete()
    finally:
        _disarm(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0002_rls_policies"),
    ]

    operations = [
        migrations.RunPython(seed_builtin_link_types, unseed),
    ]
