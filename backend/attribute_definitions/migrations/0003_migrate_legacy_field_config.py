"""Fold AttributeVisibilityConfig + CustomFieldDefinition into the new model.

Spec section 4, hard migration:

* ``AttributeVisibilityConfig`` -> ``visible``/``required`` on the matching CORE
  attribute of all three presets of ``(tenant, entity_type)``. A ``locked``
  attribute is skipped: its ``visible``/``required`` are invariants, and a
  legacy row that hid the status field would break the workflow UI.
* ``CustomFieldDefinition`` -> ``kind="extended"`` entries in section
  ``"custom"``, appended to the WORKSPACE definition of every item type (the
  legacy model's own docstring: "a definition applies to *all* artifacts of the
  workspace"). Those workspace rows are marked ``is_customized=True`` so a
  later global edit does not silently wipe the migrated custom fields.
* ``CustomFieldValue`` keeps every value; only its link changes, in the
  persistence migration that drops the legacy tables (Decision D3).

Introspection caveat, accepted deliberately: seeding uses the *live* models via
``introspect_core_attributes`` rather than the historical models this migration
is handed. That is safe here because the seeded rows are configuration, not
user data, and it keeps the rollout reproducible from a single ``migrate`` —
the alternative (require an out-of-band management-command run first) makes a
fresh install order-dependent.

RLS/tenant-arming: Postgres RLS itself is a non-issue here — the ``migrate``
service authenticates as ``DB_USER`` (default ``reqogniloom``, the Postgres
bootstrap/superuser role, see ``persistence/migrations/0048_app_role.py``),
and a superuser bypasses ``FORCE ROW LEVEL SECURITY`` unconditionally.

The *app-layer* isolation manager (``TenantManager``, COMP-PL-002) is a
separate concern and DOES need arming here, verified live (not just inferred):
when the real migration executor hands ``forwards`` a historical ``StateApps``,
``apps.get_model(...)`` returns models with a plain (non-tenant-scoped)
manager — neither ``TenantManager`` nor ``UnscopedManager`` sets
``use_in_migrations = True`` — so ``TenantContext`` is irrelevant there. But
this module is *also* exercised directly against the live app registry
(``attribute_definitions/tests/test_legacy_migration.py``, same idiom as
``workflow.migrations.0013_seed_issue_resolved_auto_approve_target``'s test),
where ``apps.get_model`` returns the real models with the real
``TenantManager`` — running the brief's original per-tenant loop unmodified
against live models raised ``TenantContextNotSetError`` on the very first
tenant-scoped query. Fixed by arming/clearing ``TenantContext`` per
``tenant_id`` inside the loop (mirroring
``bootstrap_attribute_definitions.Command.handle``'s per-tenant pattern) —
a no-op under the real executor's plain-manager historical models, and
required for the direct-live-apps path this module's own tests exercise.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    BOOTSTRAP_ITEM_TYPES,
    PRESETS,
    introspect_core_attributes,
)
from attribute_definitions.schema import normalize_attribute
from persistence.tenancy import TenantContext

FIELD_TYPE_MAP: dict[str, str] = {
    "text": "text",
    "number": "number",
    "dropdown": "enum",
}

CUSTOM_FIELD_SECTION = "custom"


def apply_visibility_config(
    global_row_attributes: list[dict[str, Any]], config_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return *global_row_attributes* with the legacy visibility flags applied."""
    by_name = {a["name"]: a for a in global_row_attributes}
    for row in config_rows:
        attribute = by_name.get(row["attribute_name"])
        if attribute is None or attribute["locked"]:
            continue
        attribute["visible"] = bool(row["is_visible"])
        attribute["required"] = bool(row["is_required"])
    return list(by_name.values())


def custom_field_to_attribute(row: dict[str, Any], order: int) -> dict[str, Any]:
    """Convert one legacy CustomFieldDefinition row into an extended attribute."""
    field_type = FIELD_TYPE_MAP.get(row["field_type"], "text")
    options = (
        [
            {"value": str(o), "label_de": str(o), "label_en": str(o)}
            for o in (row.get("options") or [])
        ]
        if field_type == "enum"
        else []
    )
    return normalize_attribute(
        {
            "name": row["name"],
            "kind": "extended",
            "type": field_type,
            "options": options,
            "required": bool(row["is_required"]),
            "visible": True,
            "editable": True,
            "section": CUSTOM_FIELD_SECTION,
            "order": order,
            "label": {"de": row["name"], "en": row["name"]},
            "export": True,
        }
    )


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Workspace = apps.get_model("persistence", "Workspace")
    AttributeVisibilityConfig = apps.get_model("persistence", "AttributeVisibilityConfig")
    CustomFieldDefinition = apps.get_model("persistence", "CustomFieldDefinition")
    GlobalAttributeDefinition = apps.get_model(
        "attribute_definitions", "GlobalAttributeDefinition"
    )
    WorkspaceAttributeDefinition = apps.get_model(
        "attribute_definitions", "WorkspaceAttributeDefinition"
    )

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # AttributeVisibilityConfig/CustomFieldDefinition/GlobalAttributeDefinition/
        # WorkspaceAttributeDefinition are all TenantScopedModel: their default
        # manager's get_queryset() calls TenantContext.get_tenant() unconditionally
        # (COMP-PL-002), regardless of an explicit tenant_id= filter/kwarg chained
        # after it. Historical model classes handed in by the real migration
        # executor use a plain (non-tenant-scoped) manager (see module docstring),
        # so this is a no-op there - but this function is also exercised directly
        # against the LIVE app registry (attribute_definitions/tests/
        # test_legacy_migration.py, same idiom as workflow.migrations.
        # 0013_seed_issue_resolved_auto_approve_target's test), where the real
        # TenantManager applies and a per-tenant arm/clear is required for
        # correctness with more than one tenant - verified live: omitting this
        # raised TenantContextNotSetError on the very first tenant-scoped query.
        TenantContext.set_tenant(tenant_id)
        try:
            visibility_by_type: dict[str, list[dict[str, Any]]] = {}
            for row in AttributeVisibilityConfig.objects.filter(tenant_id=tenant_id).values(
                "entity_type", "attribute_name", "is_visible", "is_required"
            ):
                visibility_by_type.setdefault(row["entity_type"], []).append(row)

            globals_by_key: dict[tuple[str, str], Any] = {}
            for item_type in BOOTSTRAP_ITEM_TYPES:
                for preset in PRESETS:
                    attributes = apply_visibility_config(
                        introspect_core_attributes(item_type, preset),
                        visibility_by_type.get(item_type, []),
                    )
                    attributes.sort(key=lambda a: (a["section"], a["order"], a["name"]))
                    obj, created = GlobalAttributeDefinition.objects.get_or_create(
                        tenant_id=tenant_id,
                        item_type=item_type,
                        preset=preset,
                        defaults={"definition_json": {"attributes": attributes}},
                    )
                    if not created:
                        obj.definition_json = {"attributes": attributes}
                        obj.save(update_fields=["definition_json"])
                    globals_by_key[(item_type, preset)] = obj

            for workspace in Workspace.objects.filter(tenant_id=tenant_id):
                custom_rows = list(
                    CustomFieldDefinition.objects.filter(workspace_id=workspace.id)
                    .order_by("order", "name")
                    .values("name", "field_type", "is_required", "options", "order")
                )
                if not custom_rows:
                    continue
                preset = (workspace.preset or {}).get("tier") or "standard"
                extended = [
                    custom_field_to_attribute(row, index)
                    for index, row in enumerate(custom_rows)
                ]
                for item_type in BOOTSTRAP_ITEM_TYPES:
                    source = globals_by_key[(item_type, preset)]
                    attributes = list(source.definition_json["attributes"]) + [
                        dict(a) for a in extended
                    ]
                    attributes.sort(key=lambda a: (a["section"], a["order"], a["name"]))
                    WorkspaceAttributeDefinition.objects.update_or_create(
                        tenant_id=tenant_id,
                        workspace_id=workspace.id,
                        item_type=item_type,
                        defaults={
                            "preset": preset,
                            "definition_json": {"attributes": attributes},
                            "source_global": source,
                            "is_customized": True,
                        },
                    )
        finally:
            TenantContext.clear_tenant()


def backwards(apps, schema_editor) -> None:
    """Drop everything this migration created.

    Reversible on purpose: the legacy tables still exist at this point (they are
    dropped one migration later), so a rollback loses no configuration.
    """
    apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition").objects.all().delete()
    apps.get_model("attribute_definitions", "GlobalAttributeDefinition").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0002_attribute_definition_rls_policies"),
        ("persistence", "0079_drop_glossary_term_version"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
