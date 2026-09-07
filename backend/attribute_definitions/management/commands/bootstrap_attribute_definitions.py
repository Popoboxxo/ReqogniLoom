"""Seed the initial GlobalAttributeDefinition rows from model introspection.

Spec section 3.2 ("the cheap core list", Audit N4 step 1). Runs once per tenant
as part of the rollout, not live on every read: later new Django model fields
need an explicit ``--sync-new-fields`` run, which is deliberate — model fields
change rarely and an automatic sync would silently reintroduce columns an admin
had removed from the form.

Two design points that make this command order-independent with respect to the
Datenmodell-Konsolidierung spec:

1. ``status`` is NOT introspected from a column. It is injected synthetically
   (``locked``, ``editable="workflow"``) because the single status axis after
   that migration is ``WorkflowItemState.current_state``, not a per-model
   column. ``options`` stays empty: the concrete states come from the workflow
   definition, which is already their single source of truth.
2. Every column that migration drops is in ``EXCLUDED_MODEL_FIELDS``, so the
   output is byte-identical before and after it.

Models are resolved through ``apps.get_model`` with an ordered candidate list
because Adr / Risk / Issue / Goal historically lived in ``application.models``
and moved to ``persistence.models`` in that same migration.

Tenancy: ``Command.handle`` arms both isolation layers per tenant via
``persistence.middleware.set_request_tenant``/``clear_request_tenant`` (paired
in a ``finally``). A management command has no request/middleware around it,
so without this the least-privilege runtime role (``reqogniloom_app``) hits
Postgres RLS: ``GlobalAttributeDefinitionStore.get`` silently returns nothing
and ``.initialize`` raises ``ProgrammingError`` ("new row violates row-level
security policy") — verified live against the dev stack, not just inferred
from the store's docstring. Same pattern as
``application.management.commands.backfill_embeddings``.
"""
from __future__ import annotations

import copy
from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from application.cache_invalidation import invalidate_workspace_caches
from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from attribute_definitions.models import GlobalAttributeDefinition
from attribute_definitions.schema import normalize_attribute
from persistence.models import Tenant
from presets.registry import PresetRegistry

BOOTSTRAP_ITEM_TYPES: tuple[str, ...] = (
    "Requirement",
    "StakeholderNeed",
    "ArchitectureElement",
    "TestCase",
    "Adr",
    "Risk",
    "Issue",
    "Goal",
    "Icd",
    "GlossaryTerm",
)

PRESETS: tuple[str, ...] = ("minimal", "standard", "extended")

#: Ordered ``(app_label, model_name)`` candidates per item type. The first that
#: resolves wins, so a model that moves between apps does not break the command.
MODEL_LOCATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "Requirement": (("persistence", "Requirement"),),
    "StakeholderNeed": (("persistence", "StakeholderNeed"),),
    "ArchitectureElement": (("persistence", "ArchitectureElement"),),
    "TestCase": (("persistence", "TestCase"),),
    "GlossaryTerm": (("persistence", "GlossaryTerm"),),
    "Icd": (("icd", "Icd"),),
    "Adr": (("persistence", "Adr"), ("application", "Adr")),
    "Risk": (("persistence", "Risk"), ("application", "Risk")),
    "Issue": (("persistence", "Issue"), ("application", "Issue")),
    "Goal": (("persistence", "Goal"), ("application", "Goal")),
}

#: Columns that are never user-facing attributes. ``status`` and
#: ``lifecycle_status`` are here because they are the two status axes the
#: Datenmodell-Konsolidierung removes; ``status`` comes back synthetically.
EXCLUDED_MODEL_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "tenant",
        "tenant_id",
        "workspace",
        "workspace_id",
        "artifact",
        "artifact_id",
        "created_at",
        "modified_at",
        "updated_at",
        "created_by",
        "modified_by",
        "version",
        "lock_version",
        "status",
        "lifecycle_status",
        "risk_score",
        "severity",
        "term_fk",
    }
)

CLASSIFICATION_FIELDS: frozenset[str] = frozenset(
    {
        "category", "type", "level", "test_type", "element_type", "severity_level",
        "moscow_priority", "complexity_fibonacci", "verification_method",
        "probability", "impact", "detection",
    }
)

CHANGE_CONTROL_FIELDS: frozenset[str] = frozenset({"uid", "suspect", "baseline_id"})

#: Curated widget attributes (spec section 6.3). ``fields[]`` names the core
#: attributes the widget renders; the form renderer skips those individually so
#: they are not drawn twice.
WIDGET_ATTRIBUTES: dict[str, tuple[dict[str, Any], ...]] = {
    "Risk": (
        {
            "name": "risk_matrix",
            "kind": "core",
            "type": "widget",
            "widget_key": "risk_matrix_rpz",
            "fields": ["probability", "impact", "detection"],
            "section": "classification",
            "order": 10,
            "label": {"de": "Risikomatrix", "en": "Risk matrix"},
        },
    ),
    "Adr": (
        {
            "name": "decision_record",
            "kind": "core",
            "type": "widget",
            "widget_key": "markdown_tab_group",
            "fields": ["description", "context", "consequences"],
            "section": "general",
            "order": 10,
            "label": {"de": "Entscheidung", "en": "Decision"},
        },
    ),
    "TestCase": (
        {
            "name": "steps",
            "kind": "core",
            "type": "widget",
            "widget_key": "steps_editor",
            "fields": ["steps_data"],
            "section": "general",
            "order": 20,
            "label": {"de": "Testschritte", "en": "Test steps"},
        },
    ),
}

#: Model fields a widget consumes under a different attribute name, so the raw
#: column does not collide with the widget entry (TestCase.steps <-> the
#: ``steps`` widget). Maps ``item_type -> {model_field: attribute_name}``.
WIDGET_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "TestCase": {"steps": "steps_data"},
}


def synthetic_status_attribute() -> dict[str, Any]:
    """The one systemobligatory attribute every type carries (spec section 3.1).

    ``options`` is empty on purpose: the reachable states come from the
    workflow definition for ``(workspace, item_type)``, which is their single
    source of truth. The renderer fills the select from there.
    """
    return normalize_attribute(
        {
            "name": "status",
            "kind": "core",
            "type": "enum",
            "options": [
                {"value": "__workflow__", "label_de": "Workflow", "label_en": "Workflow"}
            ],
            "required": True,
            "visible": True,
            "locked": True,
            "editable": "workflow",
            "section": "general",
            "order": -100,
            "label": {"de": "Status", "en": "Status"},
            "export": True,
        }
    )


def _resolve_model(item_type: str) -> type[models.Model]:
    for app_label, model_name in MODEL_LOCATIONS[item_type]:
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            continue
    raise CommandError(
        f"Could not resolve a model for item type {item_type!r}; "
        f"tried {MODEL_LOCATIONS[item_type]}"
    )


def _attribute_type(field: models.Field) -> str | None:
    """Map a Django field onto an attribute ``type``, or None to skip it."""
    if getattr(field, "choices", None):
        return "enum"
    if isinstance(field, models.BooleanField):
        return "boolean"
    if isinstance(field, (models.DateField, models.DateTimeField)):
        return "date"
    if isinstance(
        field, (models.IntegerField, models.FloatField, models.DecimalField)
    ):
        return "number"
    if isinstance(field, models.TextField):
        return "textarea"
    if isinstance(field, (models.CharField, models.SlugField, models.EmailField)):
        return "text"
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        related = field.related_model
        if related is not None and related.__name__ == "User":
            return "user"
        return "reference"
    if isinstance(field, models.UUIDField):
        return "reference"
    # JSONField and everything else has no basic renderer; a special case must
    # be registered as a widget in WIDGET_ATTRIBUTES instead.
    return None


def _options_from_choices(field: models.Field) -> list[dict[str, str]]:
    return [
        {"value": str(value), "label_de": str(label), "label_en": str(label)}
        for value, label in (field.choices or [])
    ]


def _section_for(name: str) -> str:
    if name in CLASSIFICATION_FIELDS:
        return "classification"
    if name in CHANGE_CONTROL_FIELDS:
        return "change_control"
    return "general"


def introspect_core_attributes(item_type: str, preset: str) -> list[dict[str, Any]]:
    """Return the normalized core attribute list for ``(item_type, preset)``.

    ``required`` comes from ``blank=False`` on the model, plus the preset's
    ``mandatory_fields`` for names that actually exist as columns. Names in
    ``mandatory_fields`` with no matching column (``priority``,
    ``classification``, ``traceability_target``, ``change_reason``) are ignored
    here and reported by the command as a configuration finding.
    """
    model = _resolve_model(item_type)
    aliases = WIDGET_FIELD_ALIASES.get(item_type, {})
    widget_field_names = {
        name
        for entry in WIDGET_ATTRIBUTES.get(item_type, ())
        for name in entry["fields"]
    }

    attributes: list[dict[str, Any]] = [synthetic_status_attribute()]
    order = 0
    for field in model._meta.get_fields():
        if not isinstance(field, models.Field) or field.auto_created:
            continue
        if field.name in EXCLUDED_MODEL_FIELDS:
            continue
        attribute_type = _attribute_type(field)
        name = aliases.get(field.name, field.name)
        if attribute_type is None:
            # Only keep an unrenderable column when a widget claims it.
            if name not in widget_field_names:
                continue
            attribute_type = "textarea"
        order += 1
        attributes.append(
            normalize_attribute(
                {
                    "name": name,
                    "kind": "core",
                    "type": attribute_type,
                    "options": _options_from_choices(field) if attribute_type == "enum" else [],
                    "required": not field.blank,
                    "visible": True,
                    "editable": True,
                    "section": _section_for(name),
                    "order": order,
                    "label": {"de": name, "en": name},
                    "ai_elicit": name in ("title", "description"),
                    "export": True,
                }
            )
        )

    for entry in WIDGET_ATTRIBUTES.get(item_type, ()):
        attributes.append(normalize_attribute(dict(entry, export=False)))

    mandatory = set(PresetRegistry().get_preset_config(preset).mandatory_fields)
    for attribute in attributes:
        if attribute["name"] in mandatory:
            attribute["required"] = True

    attributes.sort(key=lambda a: (a["section"], a["order"], a["name"]))
    return attributes


def unmatched_mandatory_fields(item_type: str, preset: str) -> list[str]:
    """Preset ``mandatory_fields`` entries that have no matching attribute."""
    names = {a["name"] for a in introspect_core_attributes(item_type, preset)}
    return sorted(set(PresetRegistry().get_preset_config(preset).mandatory_fields) - names)


class Command(BaseCommand):
    help = (
        "Seed GlobalAttributeDefinition rows from Django model introspection. "
        "Idempotent: existing rows are left alone unless --sync-new-fields."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            dest="tenant",
            default=None,
            help="Tenant UUID. Omit to bootstrap every tenant.",
        )
        parser.add_argument(
            "--sync-new-fields",
            action="store_true",
            dest="sync_new_fields",
            help=(
                "Append core attributes that exist on the model but not yet in "
                "the stored definition. Never modifies an existing entry."
            ),
        )

    def handle(self, *args, **options) -> None:
        # A management command has no request/middleware around it, so
        # without explicitly arming both isolation layers the least-privilege
        # runtime role (reqogniloom_app) hits Postgres RLS: reads return
        # nothing and writes raise ProgrammingError ("new row violates
        # row-level security policy"). Same pattern as
        # application.management.commands.backfill_embeddings.
        from persistence.middleware import clear_request_tenant, set_request_tenant

        store = GlobalAttributeDefinitionStore()
        tenant_ids = (
            [options["tenant"]]
            if options["tenant"]
            else list(Tenant.objects.values_list("id", flat=True))
        )
        created = updated = 0
        with transaction.atomic():
            for tenant_id in tenant_ids:
                set_request_tenant(tenant_id)
                try:
                    for item_type in BOOTSTRAP_ITEM_TYPES:
                        for preset in PRESETS:
                            attributes = introspect_core_attributes(item_type, preset)
                            existing = store.get(tenant_id, item_type, preset)
                            if existing is None:
                                store.initialize(tenant_id, item_type, preset, attributes)
                                created += 1
                            elif options["sync_new_fields"]:
                                if self._append_missing(store, existing, attributes):
                                    updated += 1
                finally:
                    clear_request_tenant()

        for item_type in BOOTSTRAP_ITEM_TYPES:
            for preset in PRESETS:
                unmatched = unmatched_mandatory_fields(item_type, preset)
                if unmatched:
                    self.stdout.write(
                        self.style.WARNING(
                            f"{item_type}/{preset}: preset mandatory_fields name "
                            f"{unmatched} with no matching attribute — ignored"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"bootstrap_attribute_definitions: {created} created, {updated} synced"
            )
        )

    @staticmethod
    def _append_missing(
        store: GlobalAttributeDefinitionStore,
        row: GlobalAttributeDefinition,
        introspected: list[dict[str, Any]],
    ) -> bool:
        """Append attributes the stored definition lacks. Returns True on change.

        Writes via a bare ``row.save()`` rather than ``store.update()``:
        ``update()`` runs ``validate_meta_only_change``, which correctly
        rejects adding a new *core* attribute "through the API" — that
        restriction targets admin edits, not this command's own
        introspection-driven sync. But ``update()`` is also the only place
        that calls ``_propagate()``, so bypassing it used to leave every
        non-customized workspace row permanently out of sync with the global
        default it mirrors (ledger binding (k), Task 6 review I-1). Calling
        ``store._propagate(row)`` directly after the save keeps the schema
        bypass (still needed) while closing the propagation gap.

        ``_propagate()`` itself bulk-``update()``s workspace rows, which
        bypasses ``save()``/signals and therefore the shared cache too —
        without the explicit ``invalidate_workspace_caches`` loop below, a
        warm worker keeps serving the pre-sync definition for every affected
        workspace until it restarts (Task 7 review I-2).
        """
        stored = list((row.definition_json or {}).get("attributes", []))
        known = {a["name"] for a in stored}
        additions = [copy.deepcopy(a) for a in introspected if a["name"] not in known]
        if not additions:
            return False
        stored.extend(additions)
        stored.sort(key=lambda a: (a["section"], a["order"], a["name"]))
        row.definition_json = {"attributes": stored}
        # ponytail: deferred read-modify-write on the optimistic-lock counter,
        # deliberately consistent with the other 3 sites in this codebase
        # (global_definition_store.py, workspace_definition_store.py x2) —
        # see ledger binding item (j): converted to F("version") + 1 in one
        # cross-cutting sweep at Task 10, when expected_version becomes
        # load-bearing. Not fixed here on purpose.
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "version", "modified_at"])
        store._propagate(row)
        for workspace_id in store.list_derived_workspace_ids(row):
            invalidate_workspace_caches(workspace_id)
        return True
