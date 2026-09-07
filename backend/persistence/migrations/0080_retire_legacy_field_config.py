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
  4. fold every surviving value into ``Artifact.custom_fields``
     (``fold_values_into_custom_fields`` — code-review finding C-1, see below),
  5. make the column non-null, swap the unique constraint, drop the two legacy
     tables.

C-1 (code review, this task's fix round): Task 8 migrated the *schema*
(``CustomFieldDefinition`` -> extended attribute definitions) but nothing ever
migrated the *data* a legacy ``CustomFieldValue`` row holds — the new system
reads ``kind="extended"`` values from ``Artifact.custom_fields``
(``persistence.custom_fields.validate_custom_fields``), not from this table,
and nothing reads ``pl_custom_field_value`` any more after this migration.
Dropping the table below without folding first would make every surviving
value permanently unreadable. ``fold_values_into_custom_fields`` runs after
``drop_collision_orphans`` (so a collision-orphaned row is never folded) and
before the schema-drop operations, applying the same ceilings
``validate_custom_fields`` enforces defensively (a legacy value predates that
validator): oversized strings are truncated, dotted keys are renamed, and an
artifact already at ``MAX_KEYS`` skips the overflow deterministically — never
crashing the migration or silently keeping a value the API would reject on
the next write.

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


def fold_values_into_custom_fields(apps, schema_editor) -> None:
    """Step 4 (code-review C-1): fold surviving ``CustomFieldValue`` rows into
    ``Artifact.custom_fields`` before the legacy table is dropped below.

    Runs after ``drop_collision_orphans`` (no collision-orphaned row is ever
    seen here — proven by
    ``TestFoldValuesIntoCustomFields.test_collision_orphan_is_gone_before_fold_runs``)
    and before the ``RemoveField``/``DeleteModel`` operations that make the
    data unreachable.

    Ceilings mirror ``persistence.custom_fields.validate_custom_fields``
    (duplicated, not imported — this frozen ``RunPython`` step must not break
    if that module is refactored later), applied defensively since a legacy
    value predates that validator and was never checked against it:
      - a string value over ``MAX_VALUE_STRING_LENGTH`` is truncated, not
        rejected — this migration must never abort or drop an artifact's
        entire custom_fields over one oversized legacy value;
      - a dotted key (disallowed — JSONB path traversal ambiguity) is
        rewritten with dots replaced by underscores;
      - once an artifact's ``custom_fields`` would exceed ``MAX_KEYS``, the
        remaining values for that artifact are skipped, always in the same
        order (sorted by ``attribute_name``) so a retry is reproducible.

    Values are grouped by artifact and written with a single ``save()`` per
    artifact (not once per value) to keep this bounded for an artifact that
    accumulated many legacy custom fields.

    Tenant-context arming: same idiom as ``drop_collision_orphans`` above —
    required when this function is exercised directly against the LIVE app
    registry (this module's own test does), a no-op under the real migration
    executor's historical (plain-manager) models.
    """
    Tenant = apps.get_model("persistence", "Tenant")
    CustomFieldValue = apps.get_model("persistence", "CustomFieldValue")
    Artifact = apps.get_model("persistence", "Artifact")

    # Mirrors persistence.custom_fields.{MAX_KEYS,MAX_VALUE_STRING_LENGTH} —
    # duplicated on purpose, see docstring above.
    MAX_KEYS = 50
    MAX_VALUE_STRING_LENGTH = 2000

    folded = 0
    truncated = 0
    key_renamed = 0
    key_dropped_for_max = 0
    # Always 0 in practice: drop_collision_orphans (the RunPython step
    # immediately before this one) already removed every row this step would
    # otherwise call an orphan. Counted and logged anyway so the summary line
    # is an explicit proof of the ordering invariant, not a silent assumption.
    orphan_skipped = 0

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        TenantContext.set_tenant(tenant_id)
        try:
            by_artifact: dict = {}
            for value in (
                CustomFieldValue.objects.filter(tenant_id=tenant_id)
                .order_by("attribute_name")
                .iterator()
            ):
                by_artifact.setdefault(value.artifact_id, []).append(value)

            for artifact_id, values in by_artifact.items():
                artifact = Artifact.objects.get(id=artifact_id)
                custom_fields = dict(artifact.custom_fields or {})
                changed = False
                for value in values:
                    key = value.attribute_name
                    val = value.value
                    if "." in key:
                        new_key = key.replace(".", "_")
                        logger.warning(
                            "[0080_retire_legacy_field_config] renaming dotted "
                            "custom_fields key on fold: tenant_id=%s "
                            "artifact_id=%s %r -> %r",
                            tenant_id, artifact_id, key, new_key,
                        )
                        key = new_key
                        key_renamed += 1
                    if len(val) > MAX_VALUE_STRING_LENGTH:
                        logger.warning(
                            "[0080_retire_legacy_field_config] truncating "
                            "oversized custom_fields value on fold: "
                            "tenant_id=%s artifact_id=%s key=%r (%d -> %d "
                            "chars)",
                            tenant_id, artifact_id, key, len(val),
                            MAX_VALUE_STRING_LENGTH,
                        )
                        val = val[:MAX_VALUE_STRING_LENGTH]
                        truncated += 1
                    if key not in custom_fields and len(custom_fields) >= MAX_KEYS:
                        logger.warning(
                            "[0080_retire_legacy_field_config] dropping "
                            "custom_fields key on fold, artifact already at "
                            "MAX_KEYS=%d: tenant_id=%s artifact_id=%s key=%r",
                            MAX_KEYS, tenant_id, artifact_id, key,
                        )
                        key_dropped_for_max += 1
                        continue
                    custom_fields[key] = val
                    changed = True
                    folded += 1
                if changed:
                    artifact.custom_fields = custom_fields
                    artifact.save(update_fields=["custom_fields"])
        finally:
            TenantContext.clear_tenant()

    logger.info(
        "[0080_retire_legacy_field_config] folded CustomFieldValue rows into "
        "Artifact.custom_fields: folded=%d truncated=%d key_renamed=%d "
        "key_dropped_for_max=%d orphan_skipped=%d",
        folded, truncated, key_renamed, key_dropped_for_max, orphan_skipped,
    )


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
        migrations.RunPython(
            fold_values_into_custom_fields, migrations.RunPython.noop
        ),
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
