"""Extend the seeded definitions with the pairs live data already relies on.

Runs after ``0003_seed_builtin_link_types``. Only ``is_customized=False`` rows
are touched: a workspace that has already tailored a type has made a
deliberate decision that a migration must not overwrite.

Like ``0003``, this iterates tenants and arms ``app.current_tenant`` before
touching either ``lt_*`` table. Both carry FORCE ROW LEVEL SECURITY with a
``NULLIF(current_setting('app.current_tenant', true), '')::uuid`` predicate,
so an unarmed ``UPDATE`` matches no rows *and reports success* — the migration
would log "0 rows" on a fully seeded database and the always-on validation of
Task 11 would then reject data this migration was supposed to legalize.
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


def apply_pairs(apps, schema_editor):
    from link_types.grandfathered import GRANDFATHERED_PAIRS, apply_grandfathered_pairs

    Tenant = apps.get_model("persistence", "Tenant")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )
    keys = list(GRANDFATHERED_PAIRS)

    updated = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            for key in keys:
                rows = list(
                    GlobalLinkTypeDefinition.objects.filter(
                        tenant_id=tenant_id, key=key
                    )
                ) + list(
                    WorkspaceLinkTypeDefinition.objects.filter(
                        tenant_id=tenant_id, key=key, is_customized=False
                    )
                )
                for row in rows:
                    merged = apply_grandfathered_pairs(row.definition_json, key)
                    if merged == row.definition_json:
                        continue
                    row.definition_json = merged
                    row.save(update_fields=["definition_json"])
                    updated += 1
    finally:
        _disarm(schema_editor)

    logger.info("LinkTypeCatalog: grandfathered pairs applied to %d rows.", updated)


class Migration(migrations.Migration):

    dependencies = [("link_types", "0003_seed_builtin_link_types")]

    operations = [
        migrations.RunPython(apply_pairs, migrations.RunPython.noop),
    ]
