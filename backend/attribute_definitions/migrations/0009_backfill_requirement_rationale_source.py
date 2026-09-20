"""Add the requirement ``rationale``/``source`` attributes to existing definitions.

Issue #871 / #583 (INCOSE Guide for Writing Requirements, IEEE 29148 §5.2.6):
``Requirement.rationale`` and ``Requirement.source`` are new model columns, so
``bootstrap_attribute_definitions.introspect_core_attributes`` produces them for
every *fresh* tenant — but its contract is "existing rows are left alone". A
tenant whose Requirement definition rows predate the columns would keep a form
that cannot show or edit them (the definition-driven RequirementArtifactForm
renders exactly the attributes a definition declares).

This migration is that repair: it merges the two newly introspected attributes
into every existing ``Requirement`` definition row that is missing them, in both
the global template and its materialized workspace copies (the form load path
resolves the workspace row), without touching any other attribute or any
customized value.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    introspect_core_attributes,
)
from persistence.tenancy import TenantContext

ITEM_TYPE = "Requirement"
#: The attributes this migration introduces. Scoped by name so a customized
#: definition keeps every other decision it made.
NEW_ATTRIBUTE_NAMES = ("rationale", "source")


def _merge(definition_json: Any, wanted: list[dict[str, Any]]) -> bool:
    """Append each wanted attribute that is not yet present. True on change.

    Tolerates a hand-edited/older row (non-dict entries, a broken payload) by
    returning ``False`` instead of taking the whole migration down.
    """
    if not isinstance(definition_json, dict):
        return False
    attributes = definition_json.get("attributes")
    if not isinstance(attributes, list):
        return False
    existing = {
        attribute.get("name")
        for attribute in attributes
        if isinstance(attribute, dict)
    }
    changed = False
    for entry in wanted:
        if entry["name"] not in existing:
            attributes.append(entry)
            changed = True
    return changed


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Global = apps.get_model("attribute_definitions", "GlobalAttributeDefinition")
    Workspace = apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition")
    touched_workspaces: list[Any] = []

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # Arm the app-layer TenantManager (see 0008's docstring for why).
        TenantContext.set_tenant(tenant_id)
        try:
            for model in (Global, Workspace):
                rows = model.objects.filter(tenant_id=tenant_id, item_type=ITEM_TYPE)
                for row in rows:
                    wanted = [
                        attribute
                        for attribute in introspect_core_attributes(
                            ITEM_TYPE, row.preset
                        )
                        if attribute["name"] in NEW_ATTRIBUTE_NAMES
                    ]
                    if wanted and _merge(row.definition_json, wanted):
                        row.save(update_fields=["definition_json"])
                        if model is Workspace:
                            touched_workspaces.append(row.workspace_id)
        finally:
            TenantContext.clear_tenant()

    # The resolved definition is cached per workspace; best effort, same caveat
    # as 0008 (already-running workers still need the post-migrate restart).
    try:
        from application.cache_invalidation import invalidate_workspace_caches
    except Exception:  # pragma: no cover - import guard for reduced installs
        return
    for workspace_id in touched_workspaces:
        invalidate_workspace_caches(workspace_id)


def backwards(apps, schema_editor) -> None:
    """No-op: removing the attributes would strip the new columns' editors."""


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0008_backfill_id_display_props"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
