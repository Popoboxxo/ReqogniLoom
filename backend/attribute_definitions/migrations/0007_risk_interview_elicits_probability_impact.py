"""Mark ``Risk.probability`` / ``Risk.impact`` as ``ai_elicit`` on seeded rows.

``RiskService.create_risk`` declares both without a default, so an interview
that never asks for them produces a session ``formalize()`` can only reject
("cannot formalize 'Risk' from the collected answers: 'probability'").
``interview_protocol._EXTRA_REQUIRED_FIELDS`` fixed that for the hardcoded
factory-default protocol (tier 3) — but ``get_protocol()`` prefers the
attribute-definition-derived protocol (tier 2) whenever a definition exists,
and ``application.self_init`` bootstraps one for every new tenant. Tier 3 is
therefore unreachable on a real deployment, and Risk interviews stayed broken.

``bootstrap_attribute_definitions`` now marks both attributes (see
``PER_ITEM_TYPE_AI_ELICIT_FIELDS``), which is enough for a tenant bootstrapped
from here on. It is not enough for an already-seeded database: the command's
contract is "existing rows are left alone", and neither ``--sync-new-fields``
(appends missing attributes only, never edits one) nor the destructive
``--reset`` (discards every admin customization) is the right repair. This
migration flips exactly the two flags, using the same surgical shape as
``0006_relax_adr_description_required`` — one item type, two attributes, and
only where a fresh introspection agrees they should be elicited.

Both tables are repaired: ``WorkspaceAttributeDefinition`` is a materialized
copy, so a global-only fix would leave the rows ``get_protocol()`` actually
resolves still broken.

Known trade-off: an admin who deliberately cleared ``ai_elicit`` on one of
these two attributes gets it back. That is intentional — the alternative is a
Risk interview that cannot be formalized at all, and ``ai_elicit`` remains
editable through the admin API afterwards.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    PRESETS,
    introspect_core_attributes,
)
from persistence.tenancy import TenantContext

ITEM_TYPE = "Risk"
ATTRIBUTES = ("probability", "impact")


def _elicitable(preset: str) -> set[str]:
    """The subset of :data:`ATTRIBUTES` a fresh introspection marks ai_elicit."""
    return {
        attribute["name"]
        for attribute in introspect_core_attributes(ITEM_TYPE, preset)
        if attribute["name"] in ATTRIBUTES and attribute.get("ai_elicit")
    }


def _mark_elicited(definition_json: Any, names: set[str]) -> bool:
    """Set ``ai_elicit`` on *names*. True when something changed."""
    if not isinstance(definition_json, dict):
        return False
    attributes = definition_json.get("attributes")
    if not isinstance(attributes, list):
        return False
    changed = False
    for attribute in attributes:
        # Tolerate a hand-edited/older row rather than taking the whole
        # migration down on a KeyError.
        if not isinstance(attribute, dict):
            continue
        if attribute.get("name") in names and attribute.get("ai_elicit") is not True:
            attribute["ai_elicit"] = True
            changed = True
    return changed


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Global = apps.get_model("attribute_definitions", "GlobalAttributeDefinition")
    Workspace = apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition")
    elicitable_by_preset = {preset: _elicitable(preset) for preset in PRESETS}
    touched_workspaces: list[Any] = []

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # Arm the app-layer TenantManager: a no-op under the real executor's
        # historical plain-manager models, required when this module is run
        # directly against the live app registry (see 0003's module docstring).
        TenantContext.set_tenant(tenant_id)
        try:
            for model in (Global, Workspace):
                for row in model.objects.filter(tenant_id=tenant_id, item_type=ITEM_TYPE):
                    names = elicitable_by_preset.get(row.preset) or set()
                    if not names:
                        continue
                    if _mark_elicited(row.definition_json, names):
                        row.save(update_fields=["definition_json"])
                        if model is Workspace:
                            touched_workspaces.append(row.workspace_id)
        finally:
            TenantContext.clear_tenant()

    # The resolved definition is cached per workspace; without this the shared
    # cache keeps serving the un-repaired payload and Risk interviews keep
    # skipping the two questions after a successful migration. Best effort by
    # contract, and it cannot reach the in-process caches of already-running
    # workers — those still need the usual post-migrate restart (same caveat
    # as 0005/0006).
    try:
        from application.cache_invalidation import invalidate_workspace_caches
    except Exception:  # pragma: no cover - import guard for reduced installs
        return
    for workspace_id in touched_workspaces:
        invalidate_workspace_caches(workspace_id)


def backwards(apps, schema_editor) -> None:
    """No-op: clearing ``ai_elicit`` again would re-break Risk interviews."""


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0006_relax_adr_description_required"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
