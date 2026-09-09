"""Seed GlobalAttributeDefinition rows for the 11th bootstrapped item type.

Gap #4a (ledger): ``ChangeRequest`` was carved out of the original ten-type
rollout wave (Task 19/20 findings routed straight into ``EXCLUDED_MODEL_FIELDS``
/ ``READ_ONLY_MODEL_FIELDS`` instead). It is now added the same way the other
ten were: via ``bootstrap_attribute_definitions.introspect_core_attributes``,
one ``GlobalAttributeDefinition`` row per ``(tenant, "ChangeRequest", preset)``.

Idempotency (Task-brief requirement, mirrors the bootstrap command's own
"existing rows are left alone" contract rather than 0003's overwrite
contract): ``0003_migrate_legacy_field_config`` imports ``BOOTSTRAP_ITEM_TYPES``
directly from the live command module — not from a historical model snapshot
— so on a **fresh** database ``0003`` already loops over ``ChangeRequest``
once this migration's ``ITEM_TYPES`` entry exists in the checked-out code, and
seeds these exact rows itself. On an **already-migrated** database ``0003``
ran back when ``ChangeRequest`` was not yet in ``ITEM_TYPES``, so the rows are
still missing. ``get_or_create`` covers both: creates the row where 0003
didn't reach it, no-ops where 0003 already did — never a duplicate, never an
IntegrityError on the ``uq_ad_global_def_tenant_type_preset`` constraint.
"""
from __future__ import annotations

from django.db import migrations

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    PRESETS,
    introspect_core_attributes,
)
from persistence.tenancy import TenantContext

ITEM_TYPE = "ChangeRequest"


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    GlobalAttributeDefinition = apps.get_model(
        "attribute_definitions", "GlobalAttributeDefinition"
    )

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # TenantScopedModel's default manager requires TenantContext to be
        # armed even for a plain get_or_create(tenant_id=...) kwarg — same
        # per-tenant arm/clear pattern as 0003_migrate_legacy_field_config
        # and bootstrap_attribute_definitions.Command.handle.
        TenantContext.set_tenant(tenant_id)
        try:
            for preset in PRESETS:
                attributes = introspect_core_attributes(ITEM_TYPE, preset)
                GlobalAttributeDefinition.objects.get_or_create(
                    tenant_id=tenant_id,
                    item_type=ITEM_TYPE,
                    preset=preset,
                    defaults={"definition_json": {"attributes": attributes}},
                )
        finally:
            TenantContext.clear_tenant()


def backwards(apps, schema_editor) -> None:
    """Remove only the rows this migration (or 0003, on a fresh DB) owns.

    Scoped to ``item_type="ChangeRequest"`` — unlike 0003's blanket delete,
    this migration never touches any other item type's rows, so there is no
    ambiguity about what "this migration's rows" means.
    """
    apps.get_model("attribute_definitions", "GlobalAttributeDefinition").unscoped.filter(
        item_type=ITEM_TYPE
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0003_migrate_legacy_field_config"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
