"""Repair Requirement rows that store a preset policy as a create-time gate.

``introspect_core_attributes`` used to fold the preset's ``mandatory_fields``
into the definition as ``required=True`` for ``item_type="Requirement"``.
``field_validation.validate_values`` enforces ``required`` at **create** time,
so on ``standard``/``extended`` workspaces every Requirement create without a
``description`` **and** an ``acceptance_criteria`` was rejected with
``400 acceptance_criteria: is required`` — the UI quick-create dialog, the MCP
``requirement.create`` tool and ~15 E2E specs among them. ``mandatory_fields``
is an *approval-transition* contract (``workflow.precondition_rules`` rule 5,
which still enforces it), not a create-payload contract; the overlay has been
removed from the introspector.

Removing it from the code is not enough: ``0003_migrate_legacy_field_config``
already seeded the poisoned payload into every existing database, and the
bootstrap command's contract is "existing rows are left alone" (only the
destructive ``--reset`` rewrites them). So a fresh install is fixed by the code
change alone, while every already-migrated deployment stays broken until this
migration flips the stored flags.

Surgical on purpose — it does not rewrite the definitions from a fresh
introspection, which would also discard unrelated admin customizations. It
clears ``required`` only where all three hold:

* ``item_type == "Requirement"`` (the overlay was Requirement-only);
* the attribute name is in that preset's ``mandatory_fields`` (the overlay's
  own predicate);
* the freshly introspected attribute of that name is ``required=False``, i.e.
  the model itself does not demand it.

The third condition is what keeps ``title`` required (``blank=False``, no
default: genuinely un-fillable by the server) while releasing ``description``
and ``acceptance_criteria``. An admin who deliberately re-marked one of these
required is indistinguishable from the overlay here, which is acceptable: the
overlay never shipped outside this feature branch, so it is the only plausible
source of the flag.

Both tables are repaired. ``WorkspaceAttributeDefinition`` is a materialized
copy (see ``attribute_definitions.models``), so a global-only fix would leave
every derived workspace row — the rows the form/validation path actually
resolves — still broken, including ``is_customized=True`` ones that no future
propagation will ever reach.

RLS: same situation as 0003 — ``migrate`` authenticates as the Postgres
bootstrap/owner role, which bypasses ``FORCE ROW LEVEL SECURITY``. The
app-layer ``TenantManager`` is armed per tenant anyway so that running this
module directly against the live app registry (as the migration tests do)
behaves identically to the real executor's historical plain-manager models.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    PRESETS,
    introspect_core_attributes,
)
from persistence.tenancy import TenantContext
from presets.registry import PresetRegistry

ITEM_TYPE = "Requirement"


def _releasable_names(preset: str) -> set[str]:
    """Names the overlay forced required that the model does not require."""
    mandatory = set(PresetRegistry().get_preset_config(preset).mandatory_fields)
    introspected = {
        a["name"]: a for a in introspect_core_attributes(ITEM_TYPE, preset)
    }
    return {
        name
        for name in mandatory
        if name in introspected and not introspected[name]["required"]
    }


def _relax(definition_json: Any, releasable: set[str]) -> bool:
    """Clear ``required`` on *releasable* names. True when something changed."""
    if not isinstance(definition_json, dict):
        return False
    attributes = definition_json.get("attributes")
    if not isinstance(attributes, list):
        return False
    changed = False
    for attribute in attributes:
        # Tolerate a hand-edited/older row rather than taking the whole
        # migration down on a KeyError: a row we cannot read is a row we
        # simply do not repair.
        if not isinstance(attribute, dict):
            continue
        if attribute.get("name") in releasable and attribute.get("required") is True:
            attribute["required"] = False
            changed = True
    return changed


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Global = apps.get_model("attribute_definitions", "GlobalAttributeDefinition")
    Workspace = apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition")
    releasable_by_preset = {preset: _releasable_names(preset) for preset in PRESETS}
    touched_workspaces: list[Any] = []

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        TenantContext.set_tenant(tenant_id)
        try:
            for model in (Global, Workspace):
                for row in model.objects.filter(
                    tenant_id=tenant_id, item_type=ITEM_TYPE
                ):
                    releasable = releasable_by_preset.get(row.preset)
                    if not releasable:
                        continue
                    if _relax(row.definition_json, releasable):
                        row.save(update_fields=["definition_json"])
                        if model is Workspace:
                            touched_workspaces.append(row.workspace_id)
        finally:
            TenantContext.clear_tenant()

    # The resolved definition is cached per workspace. Without this the shared
    # Redis entry keeps serving the un-repaired payload, i.e. creates keep
    # 400ing after a successful migration — the same trap
    # `bootstrap_attribute_definitions.Command._append_missing` documents.
    # Best effort by contract (`invalidate_workspace_caches` never raises), and
    # deliberately not the whole story: it cannot reach the *in-process* caches
    # of already-running workers, so a deployment that keeps its app containers
    # up across `migrate` still needs the usual post-migrate restart. Verified
    # live on the dev stack: DB rows repaired but the warm worker kept 400ing
    # until it was restarted.
    try:
        from application.cache_invalidation import invalidate_workspace_caches
    except Exception:  # pragma: no cover - import guard for reduced installs
        return
    for workspace_id in touched_workspaces:
        invalidate_workspace_caches(workspace_id)


def backwards(apps, schema_editor) -> None:
    """Deliberately irreversible-as-a-no-op.

    Restoring ``required=True`` would re-brick Requirement creates, and the
    flag carries no marker saying whether a given row got it from the overlay
    or from an admin. Reversing the schema is a no-op; reversing the policy is
    a code change (re-add the overlay), not a data change.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0004_bootstrap_change_request"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
