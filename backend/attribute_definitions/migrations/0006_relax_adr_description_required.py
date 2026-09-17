"""Release the create-time ``required`` flag on ``Adr.description``.

``introspect_core_attributes`` derives ``required`` from the model alone
(``not field.blank and not field.has_default()``). ``Adr.description`` was
declared ``TextField(max_length=10000)`` — no ``blank``, no default — even
though every shipped write path treats it as optional:
``AdrSerializer.description`` is ``allow_blank=True, default=""`` and the ADR
quick-create form posts a title only. The definition therefore demanded a field
no client sends, and ``field_validation.validate_values`` rejected the create
with ``400 description: is required`` (``e2e/tests/waterkettle-fullblown.spec.ts``
Phase 6c). ``persistence.0081_adr_description_blank`` fixes the model, which is
enough for a fresh install.

It is not enough for an already-seeded database: the stored definition keeps
the flag, and ``bootstrap_attribute_definitions``' contract is "existing rows
are left alone". This migration flips it, using the same surgical shape as
``0005_relax_requirement_create_required`` — one item type, one attribute, and
only where a fresh introspection agrees the model does not require it, so an
admin who deliberately marked something else required is untouched.

Both tables are repaired: ``WorkspaceAttributeDefinition`` is a materialized
copy, so a global-only fix would leave the rows the create path actually
resolves still broken.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    PRESETS,
    introspect_core_attributes,
)
from persistence.tenancy import TenantContext

ITEM_TYPE = "Adr"
ATTRIBUTE = "description"


def _is_releasable(preset: str) -> bool:
    """True when a fresh introspection says the model does not require it."""
    for attribute in introspect_core_attributes(ITEM_TYPE, preset):
        if attribute["name"] == ATTRIBUTE:
            return not attribute["required"]
    return False


def _relax(definition_json: Any) -> bool:
    """Clear ``required`` on the ADR description. True when something changed."""
    if not isinstance(definition_json, dict):
        return False
    attributes = definition_json.get("attributes")
    if not isinstance(attributes, list):
        return False
    for attribute in attributes:
        # Tolerate a hand-edited/older row rather than taking the whole
        # migration down on a KeyError.
        if not isinstance(attribute, dict):
            continue
        if attribute.get("name") == ATTRIBUTE and attribute.get("required") is True:
            attribute["required"] = False
            return True
    return False


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Global = apps.get_model("attribute_definitions", "GlobalAttributeDefinition")
    Workspace = apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition")
    releasable_by_preset = {preset: _is_releasable(preset) for preset in PRESETS}
    touched_workspaces: list[Any] = []

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # Arm the app-layer TenantManager: a no-op under the real executor's
        # historical plain-manager models, required when this module is run
        # directly against the live app registry (see 0003's module docstring).
        TenantContext.set_tenant(tenant_id)
        try:
            for model in (Global, Workspace):
                for row in model.objects.filter(
                    tenant_id=tenant_id, item_type=ITEM_TYPE
                ):
                    if not releasable_by_preset.get(row.preset):
                        continue
                    if _relax(row.definition_json):
                        row.save(update_fields=["definition_json"])
                        if model is Workspace:
                            touched_workspaces.append(row.workspace_id)
        finally:
            TenantContext.clear_tenant()

    # The resolved definition is cached per workspace; without this the shared
    # cache keeps serving the un-repaired payload and creates keep 400ing after
    # a successful migration. Best effort by contract, and it cannot reach the
    # in-process caches of already-running workers — those still need the usual
    # post-migrate restart (same caveat as 0005).
    try:
        from application.cache_invalidation import invalidate_workspace_caches
    except Exception:  # pragma: no cover - import guard for reduced installs
        return
    for workspace_id in touched_workspaces:
        invalidate_workspace_caches(workspace_id)


def backwards(apps, schema_editor) -> None:
    """No-op: restoring ``required=True`` would re-brick ADR creates."""


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0005_relax_requirement_create_required"),
        ("persistence", "0081_adr_description_blank"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
