"""Retire AttributeVisibilityConfig / CustomFieldDefinition (spec section 4).

Decision D3: ``CustomFieldValue`` keeps every value, but its link changes from
``definition`` (FK into the dropped table) to ``attribute_name`` (the attribute
key that now lives in ``definition_json``). The spec's "CustomFieldValue stays
unchanged" and "CustomFieldDefinition is removed" cannot both hold literally —
an FK cannot outlive its target. This is the minimum change that keeps the
values.

Ordered steps in one migration so no state exists where a value has neither a
definition nor a name:
  1. add the nullable ``attribute_name`` column,
  2. backfill it from ``CustomFieldDefinition.name`` (``backfill_attribute_names``)
     and drop rows whose definition vanished entirely,
  3. drop rows orphaned by a name collision Task 8 skipped
     (``drop_collision_orphans`` — binding (m), see below),
  4. make the column non-null, swap the unique constraint, drop the two legacy
     tables.

Binding (m) (Task 8 review, tracked in the SDD ledger): Task 8's data
migration (``attribute_definitions/migrations/0003_migrate_legacy_field_config``)
deliberately SKIPPED folding a ``CustomFieldDefinition`` into the new
``WorkspaceAttributeDefinition`` when its name collided with a core attribute
of the same ``(workspace, item_type)`` — "core always wins", logged there via
``print()``. That definition's row still exists in the legacy table at the
time step 2 above runs (it is dropped in step 4, later in this same
migration), so a naive ``definition_id -> name`` backfill succeeds and
silently hands these values the colliding CORE attribute's own name — not an
empty string, so step 2's "definition vanished" cleanup does not catch them.
Left alone, such a row would carry the exact same ``attribute_name`` as the
winning core attribute; the first future reader that merges
``CustomFieldValue`` rows into an artifact's resolved field map by name would
have this orphaned value silently masquerade as — or overwrite — the real
core attribute's value. That is worse than losing the value outright, so
``drop_collision_orphans`` (step 3) detects and drops these rows too, logged
the same way Task 8 logged its original skip (this migration uses this
codebase's actual logging convention, ``logging.getLogger(__name__)`` +
``logger.warning``, per the Task 8 review's style-nit — see
``auth_tenancy/migrations/0007_...``/``0010_...`` for precedent).

``drop_collision_orphans`` is deliberately split out from
``backfill_attribute_names`` into its own function/``RunPython`` step: unlike
the CustomFieldDefinition-dependent backfill (frozen, no longer exercisable
once this migration ships — same fate as 0003's own ``forwards()``), every
model it touches (``CustomFieldValue``, ``Artifact``,
``WorkspaceAttributeDefinition``) survives this migration, so it stays
directly testable against the live app registry — see
``persistence/tests/test_retire_legacy_field_config.py``.
"""
from __future__ import annotations

import logging

from django.db import migrations, models

from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)


def backfill_attribute_names(apps, schema_editor) -> None:
    """Step 2: attribute_name <- CustomFieldDefinition.name; drop unreachable
    rows whose definition vanished entirely.

    No tenant-context arming: under the real ``manage.py migrate`` executor,
    ``apps.get_model(...)`` hands out historical, plain (non-tenant-scoped)
    managers here (mirrors 0003's own finding), so a flat cross-tenant query
    is safe. Like 0003's ``forwards()``, this function is frozen history —
    ``CustomFieldDefinition`` no longer exists in the live app registry once
    this migration ships, so it can no longer be exercised directly the way
    ``drop_collision_orphans`` below still can.
    """
    CustomFieldValue = apps.get_model("persistence", "CustomFieldValue")
    CustomFieldDefinition = apps.get_model("persistence", "CustomFieldDefinition")

    names = dict(CustomFieldDefinition.objects.values_list("id", "name"))
    for value in CustomFieldValue.objects.all().iterator():
        value.attribute_name = names.get(value.definition_id, "")
        value.save(update_fields=["attribute_name"])

    # A value whose definition vanished entirely has no attribute to bind to
    # and is unreachable from any form; drop it rather than ship an empty key
    # that would violate the new unique constraint.
    CustomFieldValue.objects.filter(attribute_name="").delete()


def drop_collision_orphans(apps, schema_editor) -> None:
    """Step 3 - binding (m): drop values orphaned by a core-attribute-name
    collision Task 8's migration skipped.

    Detection: a collision, by Task 8's own construction (core attributes
    seeded into ``by_name`` first, a custom field only added when its name
    isn't already taken), always means the value's ``attribute_name`` matches
    a CORE attribute of the ``WorkspaceAttributeDefinition`` Task 8 wrote for
    that ``(tenant, workspace, item_type)`` — not a ``kind="extended"`` one.
    So "not present among that row's *extended* attribute names" (whether the
    name is absent entirely, or present but claimed by a core attribute) is
    exactly a collision-skip, given the value's (already non-empty, per
    ``backfill_attribute_names`` above) name.

    Guard: only trust that absence when a ``WorkspaceAttributeDefinition`` row
    actually exists for the artifact's ``(workspace, item_type)``.
    ``Artifact.artifact_type`` is a free ``CharField`` (not constrained to
    ``attribute_definitions``' bootstrapped item types, and historically
    written with inconsistent casing by some callers) — an item_type outside
    that coverage has no row for an unrelated, pre-existing reason and must
    not be treated as a collision.

    Tenant-context arming: required when this function is exercised directly
    against the LIVE app registry (this module's own test does, since — unlike
    ``backfill_attribute_names`` — none of ``CustomFieldValue``, ``Artifact``
    or ``WorkspaceAttributeDefinition`` are retired here); a no-op under the
    real migration executor's historical (plain-manager) models. Mirrors
    0003's own per-tenant ``TenantContext.set_tenant``/``clear_tenant`` idiom.
    """
    Tenant = apps.get_model("persistence", "Tenant")
    CustomFieldValue = apps.get_model("persistence", "CustomFieldValue")
    WorkspaceAttributeDefinition = apps.get_model(
        "attribute_definitions", "WorkspaceAttributeDefinition"
    )

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        TenantContext.set_tenant(tenant_id)
        try:
            wad_extended_names_cache: dict[tuple, "set[str] | None"] = {}
            orphaned_ids: list = []
            values = CustomFieldValue.objects.filter(
                tenant_id=tenant_id
            ).select_related("artifact")
            for value in values.iterator():
                artifact = value.artifact
                cache_key = (artifact.workspace_id, artifact.artifact_type)
                if cache_key not in wad_extended_names_cache:
                    wad = WorkspaceAttributeDefinition.objects.filter(
                        tenant_id=tenant_id,
                        workspace_id=artifact.workspace_id,
                        item_type=artifact.artifact_type,
                    ).first()
                    wad_extended_names_cache[cache_key] = (
                        {
                            a["name"]
                            for a in wad.definition_json.get("attributes", [])
                            if a.get("kind") == "extended"
                        }
                        if wad is not None
                        else None
                    )
                known_extended_names = wad_extended_names_cache[cache_key]
                if (
                    known_extended_names is not None
                    and value.attribute_name not in known_extended_names
                ):
                    orphaned_ids.append(value.id)
                    logger.warning(
                        "[0080_retire_legacy_field_config] dropping "
                        "CustomFieldValue for a collision-skipped custom "
                        "field: tenant_id=%s workspace_id=%s item_type=%s "
                        "attribute_name=%r (superseded by a core attribute "
                        "of the same name; see attribute_definitions/"
                        "migrations/0003_migrate_legacy_field_config.py)",
                        tenant_id,
                        artifact.workspace_id,
                        artifact.artifact_type,
                        value.attribute_name,
                    )
            if orphaned_ids:
                CustomFieldValue.objects.filter(id__in=orphaned_ids).delete()
        finally:
            TenantContext.clear_tenant()


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0079_drop_glossary_term_version"),
        ("attribute_definitions", "0003_migrate_legacy_field_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="customfieldvalue",
            name="attribute_name",
            field=models.CharField(max_length=128, null=True),
        ),
        # Lossy-but-crash-safe reverse (``RunPython.noop``), not
        # ``IrreversibleError``: the schema operations below (RemoveField,
        # DeleteModel, ...) already reverse cleanly via Django's own recorded
        # historical state, and OTHER migrations' own tests roll the
        # `persistence` app back to an EARLIER node for unrelated reasons
        # (e.g. persistence/tests/test_prompt_template_migration.py rolling
        # back to 0043) — which requires walking *backwards* through every
        # migration after that node, this one included, even though nothing
        # about that test cares about custom fields. An IrreversibleError
        # here would abort that unrelated rollback outright. The data these
        # RunPython steps moved/dropped is still genuinely gone on a real
        # reverse migrate — a no-op does not restore it — this only makes
        # "walk past this migration node" possible without crashing.
        migrations.RunPython(backfill_attribute_names, migrations.RunPython.noop),
        migrations.RunPython(drop_collision_orphans, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="customfieldvalue",
            name="uq_customfieldvalue_definition_artifact",
        ),
        migrations.RemoveField(model_name="customfieldvalue", name="definition"),
        migrations.AlterField(
            model_name="customfieldvalue",
            name="attribute_name",
            field=models.CharField(
                max_length=128,
                help_text="Attribute name from the resolved AttributeDefinition.",
            ),
        ),
        migrations.AddConstraint(
            model_name="customfieldvalue",
            constraint=models.UniqueConstraint(
                fields=["artifact", "attribute_name"],
                name="uq_customfieldvalue_artifact_attribute",
            ),
        ),
        migrations.DeleteModel(name="CustomFieldDefinition"),
        migrations.DeleteModel(name="AttributeVisibilityConfig"),
    ]
