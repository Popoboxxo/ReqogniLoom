"""Seed the built-in ``validates`` link type (TestCase -> StakeholderNeed, #878).

``BUILTIN_LINK_TYPES`` is only read when a tenant or workspace is *provisioned*,
so adding a key to the catalog leaves every pre-existing tenant and workspace
without the row. This migration materialises the ``validates`` definition for
every tenant (global template) and every workspace of that tenant, leaving any
customized row untouched — the same shape as ``0008_seed_satisfaction_link_types``.

The definition is **pinned** here instead of being read from
``link_types.builtin``: the catalog entry and this data migration are two
separate changes (the migration must also run on a database whose code version
predates the entry), so importing the live dict would turn this migration into a
silent no-op — the lesson recorded in ``0009``.

Same RLS handling as ``0003``/``0008``: both ``lt_*`` tables carry FORCE ROW
LEVEL SECURITY, which binds the table owner too, so the migration iterates
tenants and arms ``app.current_tenant`` per tenant before touching either table.
``pl_tenant`` is deliberately outside RLS, so enumerating tenants needs no
arming.

Reverse deletes only the rows this migration created — global templates plus
non-customized workspace copies. It refuses to run at all while a ``TraceLink``
still references ``validates``: dropping the type would leave those links on a
key that no workspace catalog can resolve, which is silent data loss.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

from django.db import migrations

logger = logging.getLogger(__name__)

#: The only key this migration creates.
KEY = "validates"

#: Verbatim copy of the ``validates`` entry in ``link_types/builtin.py`` — see
#: the module docstring for why it is pinned rather than imported.
DEFINITION: dict[str, Any] = {
    "label": {
        "de": {
            "downstream": "validiert",
            "upstream": "wird validiert durch",
            "neutral": "Validierung",
        },
        "en": {
            "downstream": "validates",
            "upstream": "is validated by",
            "neutral": "Validation",
        },
    },
    "allowed_pairs": [{"source_type": "TestCase", "target_type": "StakeholderNeed"}],
    "coverage_relevant": True,
    "suspect_rule": "target_change_flags_source",
    "impact_weight": 1.0,
    "manual_creatable": True,
    "system_owned": False,
    "active": True,
    "built_in": True,
}


def _arm(schema_editor, tenant_id) -> None:
    """Point the RLS policies at *tenant_id* for the rest of this transaction."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def _disarm(schema_editor) -> None:
    """Clear the tenant GUC again so no later statement inherits it."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def seed_validates(apps, schema_editor):
    """Create the global template and the workspace copies, tenant by tenant."""
    Tenant = apps.get_model("persistence", "Tenant")
    Workspace = apps.get_model("persistence", "Workspace")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    total_globals = 0
    total_rows = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            global_row, created = GlobalLinkTypeDefinition.unscoped.get_or_create(
                tenant_id=tenant_id,
                key=KEY,
                defaults={
                    "definition_json": copy.deepcopy(DEFINITION),
                    "version": 1,
                },
            )
            total_globals += int(created)

            workspace_ids = list(
                Workspace.objects.filter(tenant_id=tenant_id).values_list(
                    "id", flat=True
                )
            )
            for workspace_id in workspace_ids:
                _row, row_created = WorkspaceLinkTypeDefinition.unscoped.get_or_create(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    key=KEY,
                    defaults={
                        "definition_json": copy.deepcopy(global_row.definition_json),
                        "source_global": global_row,
                        "is_customized": False,
                        "version": 1,
                    },
                )
                total_rows += int(row_created)
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog validates seed: %d global templates, "
        "%d workspace rows created.",
        total_globals,
        total_rows,
    )


def unseed(apps, schema_editor):
    """Reverse: drop the rows this migration created, unless links still use them."""
    Tenant = apps.get_model("persistence", "Tenant")
    TraceLink = apps.get_model("persistence", "TraceLink")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            linked = TraceLink.objects.filter(
                tenant_id=tenant_id, link_type=KEY
            ).count()
            if linked:
                raise RuntimeError(
                    f"Cannot reverse 0011_seed_validates_link_type: {linked} "
                    f"TraceLink row(s) still reference the '{KEY}' link type. "
                    "Delete or re-type those links before rolling back."
                )
            WorkspaceLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, key=KEY, is_customized=False
            ).delete()
            GlobalLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, key=KEY
            ).delete()
    finally:
        _disarm(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0010_workspace_definition_workspace_fk"),
    ]

    operations = [
        migrations.RunPython(seed_validates, unseed),
    ]
