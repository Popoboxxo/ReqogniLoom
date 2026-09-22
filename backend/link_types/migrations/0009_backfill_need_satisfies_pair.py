"""Backfill the ``StakeholderNeed -> Goal`` pair into the ``satisfies`` rows.

Cluster 5, #402 (spec section 5.2). ``BUILTIN_LINK_TYPES['satisfies']`` gains
the direct ``StakeholderNeed -> Goal`` edge, but a built-in definition is only
materialised when a tenant/workspace is *provisioned*, so every already-seeded
``lt_*`` row keeps the old pair list. Without this migration the new edge exists
for new tenants only - the same asymmetry ``0005`` was written to avoid.

Same two safety properties as ``0005``:

* only ``is_customized=False`` workspace rows are touched - a workspace that
  tailored ``satisfies`` made a deliberate decision a migration must not
  overwrite;
* ``app.current_tenant`` is armed per tenant. Both ``lt_*`` tables carry FORCE
  ROW LEVEL SECURITY, so an unarmed ``UPDATE`` under a non-``BYPASSRLS`` role
  matches nothing **and reports success**.

The wanted pair is pinned here rather than read from ``BUILTIN_LINK_TYPES``:
the catalog change that adds it to ``allowed_pairs`` is a separate, later code
change, so reading the live dict would make this migration a silent no-op. The
pinned value is a verbatim copy of the spec section 5.2 contract. The merge
helper is duplicated from ``0005`` (itself duplicated from ``0004``) for the
same reason: a future squash of an earlier migration must not be able to break a
later one.

Reverse: ``RunPython.noop``, mirroring ``0005``. Removing a pair on reverse
could delete a deliberately added tenant customization and would leave existing
``StakeholderNeed -> Goal`` links on a no-longer-allowed pair, so the reverse is
deliberately inert.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

#: The only key this migration touches.
KEY = "satisfies"

#: Exactly the new edge from spec section 5.2, in the ``allowed_pairs`` shape
#: stored in ``definition_json``.
WANTED_PAIRS = [{"source_type": "StakeholderNeed", "target_type": "Goal"}]


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
    ``grandfathered.apply_grandfathered_pairs``: an existing pair is never
    dropped or reordered. Returns the input unchanged (same object) when nothing
    is missing, so the caller can skip the write.
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
    """Append the Need -> Goal pair to global + non-customized workspace rows."""
    Tenant = apps.get_model("persistence", "Tenant")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

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
                merged = _merge_missing_pairs(current, WANTED_PAIRS)
                if merged is current:
                    continue
                row.definition_json = merged
                row.save(update_fields=["definition_json"])
                updated += 1
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog: '%s' StakeholderNeed->Goal pair backfilled into %d rows.",
        KEY,
        updated,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0008_seed_satisfaction_link_types"),
    ]

    operations = [
        migrations.RunPython(apply_pairs, migrations.RunPython.noop),
    ]
