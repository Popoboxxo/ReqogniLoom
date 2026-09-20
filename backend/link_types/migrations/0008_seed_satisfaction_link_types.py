"""Backfill the `satisfies` / `realizes` / `refines` link types (issue #950).

``BUILTIN_LINK_TYPES`` is only read when a tenant or workspace is *provisioned*,
so extending the catalog leaves every pre-existing tenant without the new rows.
This migration re-runs the same idempotent seed
(``link_types.migrations._seed_helpers.seed_tenant``) for every tenant, so the
three new keys reach existing globals and workspaces without touching a
customized row.

Same RLS handling as ``0003_seed_builtin_link_types``: both ``lt_*`` tables
carry FORCE ROW LEVEL SECURITY, which binds the table owner too, so the
migration iterates tenants and arms ``app.current_tenant`` per tenant before
touching either table. ``pl_tenant`` is deliberately outside RLS, so
enumerating tenants needs no arming.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

#: The keys this migration adds. Kept explicit so the reverse only removes what
#: the forward direction created.
NEW_KEYS = ("realizes", "refines", "satisfies")


def _arm(schema_editor, tenant_id) -> None:
    """Point the RLS policies at *tenant_id* for the rest of this transaction."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def _disarm(schema_editor) -> None:
    """Clear the tenant GUC again so no later statement inherits it."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def seed_satisfaction_link_types(apps, schema_editor):
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
        "LinkTypeCatalog satisfaction seed: %d global templates, "
        "%d workspace rows created.",
        total_globals,
        total_rows,
    )


def unseed(apps, schema_editor):
    """Reverse: drop only the untouched rows this migration added."""
    Tenant = apps.get_model("persistence", "Tenant")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            WorkspaceLinkTypeDefinition.objects.filter(
                tenant_id=tenant_id, key__in=NEW_KEYS, is_customized=False
            ).delete()
            GlobalLinkTypeDefinition.objects.filter(
                tenant_id=tenant_id, key__in=NEW_KEYS
            ).delete()
    finally:
        _disarm(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0007_backfill_grandfathered_pairs_issue893"),
    ]

    operations = [
        migrations.RunPython(seed_satisfaction_link_types, unseed),
    ]
