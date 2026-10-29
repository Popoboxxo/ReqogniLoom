"""Mark Requirement's ``acceptance_criteria``/``verification_method``/``rationale``
as ``ai_elicit`` on already-seeded rows (#272, Plan B B1-T1).

``interview_protocol.get_protocol()`` prefers the attribute-definition-derived
protocol (tier 2) whenever a definition exists, and ``application.self_init``
bootstraps one for every new tenant. Tier 2 asks exactly the attributes marked
``ai_elicit``, so before this repair every Requirement interview collected
title + description only: the resulting artifact had an empty
``acceptance_criteria``, no ``verification_method`` and no ``rationale`` — the
interview was the one path into the model that skipped the SE attributes.

``bootstrap_attribute_definitions`` now marks the three
(``PER_ITEM_TYPE_AI_ELICIT_FIELDS["Requirement"]``), which is enough for a
tenant bootstrapped from here on. It is not enough for an already-seeded
database: the command's contract is "existing rows are left alone", and neither
``--sync-new-fields`` (appends missing attributes only, never edits one) nor the
destructive ``--reset`` (discards every admin customization) is the right
repair. This migration flips exactly the three flags, using the same surgical
shape as ``0007_risk_interview_elicits_probability_impact``.

Both tables are repaired: ``WorkspaceAttributeDefinition`` is a materialized
copy, so a global-only fix would leave the rows ``get_protocol()`` actually
resolves still broken.

Only the ``standard``/``extended`` presets are touched. In ``minimal`` the SE
tail is not part of the lightweight backlog the preset stands for, and a fresh
bootstrap marks none of the three there (``AI_ELICIT_MIN_STAGE`` in the
bootstrap command, stage 2 = standard/extended), so repairing a minimal row
would make an already-seeded workspace diverge from what a re-bootstrap
produces.

The names and the preset list are pinned here on purpose (no import of the
registry/constant): a later change to ``PER_ITEM_TYPE_AI_ELICIT_FIELDS`` must
not retroactively rewrite what this historic migration does.

Known trade-off: an admin who deliberately cleared ``ai_elicit`` on one of
these three attributes gets it back. That is intentional — the alternative is a
Requirement interview that cannot fill the SE attributes at all, and
``ai_elicit`` remains editable through the admin API afterwards.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

ITEM_TYPE = "Requirement"
ATTRIBUTES = ("acceptance_criteria", "verification_method", "rationale")
#: Pinned: the presets in which the three attributes are visible (see above).
PRESETS = ("standard", "extended")


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
    names = set(ATTRIBUTES)
    touched_workspaces: list[Any] = []

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # Arm the app-layer TenantManager: a no-op under the real executor's
        # historical plain-manager models, required when this module is run
        # directly against the live app registry (see 0003's module docstring).
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(tenant_id)
        try:
            for model in (Global, Workspace):
                for row in model.objects.filter(tenant_id=tenant_id, item_type=ITEM_TYPE):
                    if row.preset not in PRESETS:
                        continue
                    if _mark_elicited(row.definition_json, names):
                        row.save(update_fields=["definition_json"])
                        if model is Workspace:
                            touched_workspaces.append(row.workspace_id)
        finally:
            TenantContext.clear_tenant()

    # The resolved definition is cached per workspace; without this the shared
    # cache keeps serving the un-repaired payload. Best effort by contract, and
    # it cannot reach the in-process caches of already-running workers -- those
    # still need the usual post-migrate restart (same caveat as 0005/0006/0007).
    try:
        from application.cache_invalidation import invalidate_workspace_caches
    except Exception:  # noqa: BLE001 — import guard  # pragma: no cover - reduced installs
        return
    for workspace_id in touched_workspaces:
        invalidate_workspace_caches(workspace_id)


def backwards(apps, schema_editor) -> None:
    """No-op: clearing ``ai_elicit`` again would re-break Requirement interviews."""


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0010_workspace_definition_workspace_fk"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
