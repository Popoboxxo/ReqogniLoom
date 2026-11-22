"""Mark the create-tool fields from issue #1991 as ``ai_elicit`` on seeded rows.

``get_protocol()`` prefers the attribute-definition-derived protocol (tier 2)
whenever a definition exists, and ``application.self_init`` bootstraps one for
every new tenant. A definition-derived interview asks exactly the attributes
flagged ``ai_elicit``. Before this repair, an Adr interview never asked for
``context``/``decision``/``consequences`` (they are only rendered by the
``decision_record`` widget), and Issue/Risk/TestCase/Architecture interviews
never asked for their documented optional fields -- the create service applied
its default silently.

``bootstrap_attribute_definitions`` now marks these fields, but its contract
is "existing rows are left alone", so an already-seeded tenant keeps the old
payload forever. This migration flips exactly the new flags, in both the
global and the materialized workspace table (the latter is what
``get_protocol()`` resolves), and only for the ``standard``/``extended``
presets: a minimal workspace keeps its lightweight interview, matching what a
fresh bootstrap produces there.

Reversibility is EXACT, not blanket. ``forwards`` records each flag's original
value under the private ``_issue1991_ai_elicit_backup`` key of the same JSON
payload and only records flags it actually changed; ``backwards`` restores
those values and removes the key. A field that was already ``ai_elicit=True``
before this migration is never touched, so reversing cannot destroy a
pre-existing flag. If the marker is absent (e.g. an admin re-saved the
definition through the validated write path, which drops unknown top-level
keys), ``backwards`` is a no-op for that row -- fail safe rather than clear
flags we cannot prove we set. No domain-table schema is altered.

Names, presets and the marker key are pinned here on purpose (no import of the
bootstrap constants): a later change to that registry must not retroactively
rewrite what this historic migration does.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

#: item type -> fields newly elicited by issue #1991 (stage 2+ only).
FIELDS_BY_ITEM_TYPE: dict[str, tuple[str, ...]] = {
    "Adr": ("context", "decision", "consequences"),
    "Issue": ("severity", "category"),
    "Risk": ("mitigation_strategy", "category", "detection"),
    "TestCase": ("test_type",),
    "ArchitectureElement": ("element_type",),
}
PRESETS = ("standard", "extended")
_BACKUP_KEY = "_issue1991_ai_elicit_backup"


def _capture_and_set(definition_json: Any, names: set[str]) -> bool:
    """Set *names* to ``ai_elicit=True``, recording original values in place.

    Only flags that actually change are recorded, so ``backwards`` restores
    exactly what this migration altered and leaves pre-existing True flags
    alone. Returns True when the payload was modified.
    """
    if not isinstance(definition_json, dict):
        return False
    attributes = definition_json.get("attributes")
    if not isinstance(attributes, list):
        return False
    backup: dict[str, bool] = {}
    for attribute in attributes:
        # Tolerate a hand-edited/older row rather than taking the migration
        # down on a KeyError.
        if not isinstance(attribute, dict):
            continue
        name = attribute.get("name")
        if name in names and attribute.get("ai_elicit") is not True:
            backup[name] = bool(attribute.get("ai_elicit", False))
            attribute["ai_elicit"] = True
    if not backup:
        return False
    existing = definition_json.get(_BACKUP_KEY)
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.update(backup)
    definition_json[_BACKUP_KEY] = merged
    return True


def _restore(definition_json: Any) -> bool:
    """Restore the flags captured by ``_capture_and_set`` and drop the marker.

    A row without a marker was not changed by ``forwards`` (or its marker was
    lost to a validated admin re-save) and is left untouched.
    """
    if not isinstance(definition_json, dict):
        return False
    backup = definition_json.get(_BACKUP_KEY)
    if not isinstance(backup, dict) or not backup:
        return False
    attributes = definition_json.get("attributes")
    if not isinstance(attributes, list):
        return False
    restored: set[str] = set()
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        name = attribute.get("name")
        if name in backup:
            attribute["ai_elicit"] = bool(backup[name])
            restored.add(name)
    definition_json.pop(_BACKUP_KEY, None)
    return bool(restored)


def _process_definition_row(
    row: Any,
    model: Any,
    *,
    workspace_model: Any,
    names: set[str],
    reverse: bool,
    touched_workspaces: list[Any],
) -> None:
    """Apply this migration's flag edit to one definition row.

    This is the original in-loop body lifted out verbatim: choose ``_restore``
    (reverse) or ``_capture_and_set`` (forward), persist only a changed row and
    remember a changed Workspace row for the post-pass cache invalidation.
    Keeping it here flattens ``_run`` so the TenantContext set/clear bracket and
    the item-type -> model -> row ordering stay visible and unmodified.
    """
    changed = (
        _restore(row.definition_json)
        if reverse
        else _capture_and_set(row.definition_json, names)
    )
    if changed:
        row.save(update_fields=["definition_json"])
        if model is workspace_model:
            touched_workspaces.append(row.workspace_id)


def _invalidate_caches(touched_workspaces: list[Any]) -> None:
    """Best-effort per-workspace invalidation after the data pass.

    The import guard and the iteration order are copied verbatim from the
    original driver, so the post-pass behavior is unchanged.
    """
    # The resolved definition is cached per workspace; without this the shared
    # cache keeps serving the pre-/post-repair payload. Best effort by contract,
    # and it cannot reach the in-process caches of already-running workers --
    # those still need the usual post-migrate restart (same caveat as 0007/0011).
    try:
        from application.cache_invalidation import invalidate_workspace_caches
    except Exception:  # noqa: BLE001 — import guard  # pragma: no cover - reduced installs
        return
    for workspace_id in touched_workspaces:
        invalidate_workspace_caches(workspace_id)


def _run(apps, schema_editor, *, reverse: bool) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Global = apps.get_model("attribute_definitions", "GlobalAttributeDefinition")
    Workspace = apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition")
    touched_workspaces: list[Any] = []

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        # Arm the app-layer TenantManager: a no-op under the real executor's
        # historical plain-manager models, required when this module is run
        # directly against the live app registry (see 0003's module docstring).
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(tenant_id)
        try:
            for item_type, fields in FIELDS_BY_ITEM_TYPE.items():
                names = set(fields)
                for model in (Global, Workspace):
                    for row in model.objects.filter(
                        tenant_id=tenant_id, item_type=item_type, preset__in=PRESETS
                    ):
                        _process_definition_row(
                            row,
                            model,
                            workspace_model=Workspace,
                            names=names,
                            reverse=reverse,
                            touched_workspaces=touched_workspaces,
                        )
        finally:
            TenantContext.clear_tenant()

    _invalidate_caches(touched_workspaces)


def forwards(apps, schema_editor) -> None:
    _run(apps, schema_editor, reverse=False)


def backwards(apps, schema_editor) -> None:
    """Restore exactly the flags ``forwards`` captured; never clear others."""
    _run(apps, schema_editor, reverse=True)


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0011_requirement_interview_elicits_se_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
