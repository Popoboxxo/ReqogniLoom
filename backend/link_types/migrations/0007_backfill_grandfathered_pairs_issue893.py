"""Re-apply ``GRANDFATHERED_PAIRS`` after issue #893 extended it.

``0004_grandfather_observed_pairs`` merged the allowlist into every seeded
definition once. An installation that has already run it keeps the contents of
that day forever, so adding a pair to ``link_types.grandfathered`` in code
legalizes it for *new* tenants only — the rows this migration exists for would
survive ``persistence/0081`` and then still be rejected by the always-on
validation when someone tries to edit them. Same reason ``0005`` and ``0006``
exist for their built-in pairs.

Deliberately shaped as a re-run of ``0004`` rather than a one-pair patch: the
merge is additive and duplicate-free, so replaying it is idempotent on a
database that already has the pairs, and the next entry added to the allowlist
needs a copy of this file rather than an edit of the migration that has already
been applied everywhere.

Same two safety properties as ``0004``/``0005``/``0006``:

* only ``is_customized=False`` workspace rows are touched — a workspace that
  tailored a type made a decision a migration must not overwrite;
* ``app.current_tenant`` is armed per tenant, because both ``lt_*`` tables
  carry FORCE ROW LEVEL SECURITY and an unarmed ``UPDATE`` under a
  non-``BYPASSRLS`` role matches nothing **and reports success**.

No dependency on ``persistence/0081`` in either direction. It is already
applied on a beta.7 installation (which would make a dependency an
``InconsistentMigrationHistory``), and on a beta.6 one the order does not
matter: ``verify_migrated_links`` checks against the allowlist *in code*, not
against these rows.
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

    logger.info("LinkTypeCatalog: grandfathered pairs re-applied to %d rows.", updated)


class Migration(migrations.Migration):

    dependencies = [("link_types", "0006_backfill_issue_reference_pairs")]

    operations = [
        migrations.RunPython(apply_pairs, migrations.RunPython.noop),
    ]
