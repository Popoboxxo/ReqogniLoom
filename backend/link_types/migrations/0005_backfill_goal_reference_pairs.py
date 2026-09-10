"""Backfill the Goal / MainGoal / Interview pairs added to ``references``.

``BUILTIN_LINK_TYPES`` is only read when a tenant or workspace is *provisioned*
(``0003_seed_builtin_link_types`` / ``workspace_store.provision_workspace_link_types``),
so extending a built-in definition in code leaves every already-seeded row
behind. Without this migration, the pairs would exist for new tenants only —
the same asymmetry ``0004`` was written to avoid, mirrored.

Same two safety properties as ``0004``:

* only ``is_customized=False`` workspace rows are touched — a workspace that
  has tailored ``references`` made a deliberate decision a migration must not
  overwrite;
* ``app.current_tenant`` is armed per tenant. Both ``lt_*`` tables carry FORCE
  ROW LEVEL SECURITY with a ``NULLIF(current_setting('app.current_tenant',
  true), '')::uuid`` predicate, so an unarmed ``UPDATE`` under a
  non-``BYPASSRLS`` role matches nothing **and reports success**.

The helper pair is duplicated from ``0004`` rather than imported for the same
reason ``0004`` duplicated it from ``0003``: a future squash of an earlier
migration must not be able to break a later one.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

#: The only key this migration touches.
KEY = "references"


def _arm(schema_editor, tenant_id) -> None:
    """Point the RLS policies at *tenant_id* for the rest of this transaction."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def _disarm(schema_editor) -> None:
    """Clear the tenant GUC again so no later statement inherits it."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def _merge_missing_pairs(definition, wanted):
    """Return *definition* with every pair of *wanted* it does not have yet.

    Additive and duplicate-free, exactly like
    ``grandfathered.apply_grandfathered_pairs``: an existing pair — including a
    grandfathered one ``0004`` appended — is never dropped or reordered.
    Returns the input unchanged (same object) when nothing is missing, so the
    caller can skip the write.
    """
    pairs = list(definition.get("allowed_pairs") or [])
    seen = {(p.get("source_type"), p.get("target_type")) for p in pairs}
    missing = [
        dict(pair)
        for pair in wanted
        if (pair["source_type"], pair["target_type"]) not in seen
    ]
    if not missing:
        return definition
    merged = dict(definition)
    merged["allowed_pairs"] = pairs + missing
    return merged


def apply_pairs(apps, schema_editor):
    from link_types.builtin import BUILTIN_LINK_TYPES

    Tenant = apps.get_model("persistence", "Tenant")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )
    wanted = BUILTIN_LINK_TYPES[KEY]["allowed_pairs"]

    updated = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            rows = list(
                GlobalLinkTypeDefinition.objects.filter(tenant_id=tenant_id, key=KEY)
            ) + list(
                WorkspaceLinkTypeDefinition.objects.filter(
                    tenant_id=tenant_id, key=KEY, is_customized=False
                )
            )
            for row in rows:
                current = row.definition_json or {}
                merged = _merge_missing_pairs(current, wanted)
                if merged is current:
                    continue
                row.definition_json = merged
                row.save(update_fields=["definition_json"])
                updated += 1
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog: '%s' endpoint pairs backfilled into %d rows.", KEY, updated
    )


class Migration(migrations.Migration):

    dependencies = [("link_types", "0004_grandfather_observed_pairs")]

    operations = [
        migrations.RunPython(apply_pairs, migrations.RunPython.noop),
    ]
