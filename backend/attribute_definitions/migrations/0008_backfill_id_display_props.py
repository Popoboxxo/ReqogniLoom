"""Backfill the generic display properties on the Artifact ``id`` attribute.

Attribut v3 WS3 (#937), spec section 5: the synthetic ``id`` system field is
the first consumer of the generic display properties — hidden by default
(``visible=False``), revealed on click (``reveal="click"``), copyable
(``copyable=True``) and rendered as an 8-character short label
(``mask="short"``) while the copy affordance still yields the full UUID.

``bootstrap_attribute_definitions`` seeds those properties for every *fresh*
tenant, but its contract is "existing rows are left alone": a tenant whose
definition rows predate WS3 — the ``id`` attribute itself already exists from
WS2 (#936), just without the display properties — would keep the unconfigured
rendering forever. This migration is that repair.

Both tables are repaired: ``WorkspaceAttributeDefinition`` is a materialized
copy, so a global-only fix would leave the rows the form load path actually
resolves still unconfigured. Only the ``id`` attribute is touched, and only
where it is the server-owned ``editable="system"`` field — an admin who reused
the name for an ordinary attribute is never affected.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

from persistence.tenancy import TenantContext

ATTRIBUTE = "id"
SYSTEM_EDITABLE = "system"

#: The spec section 5 configuration of the Artifact ``id`` field, mirrored from
#: ``bootstrap_attribute_definitions.ARTIFACT_LEVEL_CORE_ATTRIBUTES`` (the
#: fresh-seed source). Frozen here rather than imported so this migration keeps
#: repairing the same shape even if that constant is edited later.
DISPLAY_PROPS: dict[str, Any] = {
    "reveal": "click",
    "copyable": True,
    "mask": "short",
}


def _backfill(definition_json: Any) -> bool:
    """Set the display properties on the ``id`` system attribute. True on change.

    Tolerates a hand-edited/older row (non-dict entries, a broken payload) by
    returning ``False`` instead of taking the whole migration down.
    """
    if not isinstance(definition_json, dict):
        return False
    attributes = definition_json.get("attributes")
    if not isinstance(attributes, list):
        return False
    changed = False
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if attribute.get("name") != ATTRIBUTE:
            continue
        if attribute.get("editable") != SYSTEM_EDITABLE:
            continue
        for key, value in DISPLAY_PROPS.items():
            if attribute.get(key) != value:
                attribute[key] = value
                changed = True
    return changed


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Global = apps.get_model("attribute_definitions", "GlobalAttributeDefinition")
    Workspace = apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition")
    touched_workspaces: list[Any] = []

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # Arm the app-layer TenantManager: a no-op under the real executor's
        # historical plain-manager models, required when this module is run
        # directly against the live app registry (see 0003/0006 docstrings).
        TenantContext.set_tenant(tenant_id)
        try:
            for model in (Global, Workspace):
                for row in model.objects.filter(tenant_id=tenant_id):
                    if _backfill(row.definition_json):
                        row.save(update_fields=["definition_json"])
                        if model is Workspace:
                            touched_workspaces.append(row.workspace_id)
        finally:
            TenantContext.clear_tenant()

    # The resolved definition is cached per workspace; without this the shared
    # cache keeps serving the un-repaired payload. Best effort by contract, and
    # it cannot reach the in-process caches of already-running workers — those
    # still need the usual post-migrate restart (same caveat as 0005/0006).
    try:
        from application.cache_invalidation import invalidate_workspace_caches
    except Exception:  # pragma: no cover - import guard for reduced installs
        return
    for workspace_id in touched_workspaces:
        invalidate_workspace_caches(workspace_id)


def backwards(apps, schema_editor) -> None:
    """No-op: clearing the properties would restore the broken rendering."""


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0007_risk_interview_elicits_probability_impact"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
