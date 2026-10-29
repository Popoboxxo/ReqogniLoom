"""OpenAPI shapes for the attribute-configuration REST surface (#1388).

The views in :mod:`rest_api.attribute_catalog_views` and
:mod:`rest_api.attribute_definition_views` are thin adapters over
``AttributeCatalogService`` / ``AttributeDefinitionService``: they return the
service's dicts unchanged and validate their writes in place. These serializers
therefore exist **for the published contract only** — nothing is rendered
through them at runtime.

They were transcribed from the two services' payload builders plus the
``attribute_definitions.schema`` validators that define the document itself:

* ``AttributeCatalogService._entry_payload`` / ``_entry_document`` (catalog),
* ``AttributeDefinitionService._global_payload`` / ``_workspace_payload``
  (definitions),
* ``attribute_definitions.schema.normalize_attribute`` (the attribute block —
  every key below is one member of that module's ``ALLOWED_KEYS``) and
  ``validate_sections_json`` / ``validate_section_flow_json`` (the layout
  documents).

Keeping them here — instead of inside the adapters — mirrors
:mod:`memory.schema_serializers` and :mod:`admin_ops.schema_serializers`: the
adapters stay free of DRF-serializer imports and one module describes both the
catalog and the definition resources, which share the attribute block.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "AttributeBlockSerializer",
    "AttributeCatalogAddToDefinitionRequestSerializer",
    "AttributeCatalogAddToDefinitionResponseSerializer",
    "AttributeCatalogCreateRequestSerializer",
    "AttributeCatalogDeprecateRequestSerializer",
    "AttributeCatalogDocumentSerializer",
    "AttributeCatalogEntrySerializer",
    "AttributeCatalogEntryDocumentSerializer",
    "AttributeCatalogImportRequestSerializer",
    "AttributeCatalogImportSummarySerializer",
    "AttributeCatalogListSerializer",
    "AttributeCatalogUpdateRequestSerializer",
    "AttributeDefinitionDocumentSerializer",
    "AttributeDefinitionListSerializer",
    "AttributeDefinitionUpdateRequestSerializer",
    "AttributeDefinitionVersionSerializer",
    "AttributeFlowTokenSerializer",
    "AttributeReorderRequestSerializer",
    "AttributeUsageResponseSerializer",
    "GlobalAttributeDefinitionSerializer",
    "I18nTextSerializer",
    "SectionFlowTokenSerializer",
    "SectionSerializer",
    "ValidationRulesSerializer",
    "WorkspaceAttributeDefinitionSerializer",
]

#: ``attribute_definitions.schema.ATTRIBUTE_TYPES`` — the closed type range.
_ATTRIBUTE_TYPES = [
    "text",
    "textarea",
    "number",
    "boolean",
    "enum",
    "multi-enum",
    "date",
    "reference",
    "user",
    "actor",
    "widget",
    "criteria-list",
]
_ATTRIBUTE_KINDS = ["core", "extended"]
_AUDIENCES = ["basic", "expert"]
#: ``EDITABLE_VALUES`` mixes booleans and strings, so ``editable`` is declared
#: as free JSON (see :class:`AttributeBlockSerializer`).
_REVEALS = ["always", "click", "shortcut"]
_MASKS = ["none", "short"]
_DISPLAY_FORMATS = ["text", "mono", "chips"]
_ON_COLLISION = ["skip", "overwrite", "rename"]
_SECTION_LAYOUTS = ["full", "half"]
_ATTRIBUTE_SPANS = ["full", "half", "quarter"]
_SPACER_SIZES = ["sm", "md", "lg"]
_ORIGINS = ["global", "global_customized", "workspace_only"]


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


class I18nTextSerializer(serializers.Serializer):
    """The canonical ``{de, en}`` display-text pair."""

    de = serializers.CharField(allow_blank=True)
    en = serializers.CharField(allow_blank=True)


class AttributeOptionSerializer(serializers.Serializer):
    """One ``enum``/``multi-enum`` option (``_normalize_options``)."""

    value = serializers.CharField()
    label_de = serializers.CharField()
    label_en = serializers.CharField()


class ValidationRulesSerializer(serializers.Serializer):
    """The ``validation`` rule block of an attribute (``_VALIDATION_KEYS``).

    Only these four rule names exist; an unknown name is a 400 on the write
    that introduced it.
    """

    regex = serializers.CharField(required=False)
    min = serializers.FloatField(required=False)
    max = serializers.FloatField(required=False)
    length = serializers.IntegerField(required=False)


class AttributeFlowTokenSerializer(serializers.Serializer):
    """One token of a section's ``attribute_flow`` (spec section 7)."""

    kind = serializers.ChoiceField(choices=["attribute", "spacer"])
    name = serializers.CharField(required=False)
    span = serializers.ChoiceField(choices=_ATTRIBUTE_SPANS, required=False)
    size = serializers.ChoiceField(choices=_SPACER_SIZES, required=False)


class SectionFlowTokenSerializer(serializers.Serializer):
    """One token of a definition-level ``section_flow`` (WS4 #938)."""

    kind = serializers.ChoiceField(choices=["section", "spacer"])
    name = serializers.CharField(required=False)
    size = serializers.ChoiceField(choices=_SPACER_SIZES, required=False)


class SectionSerializer(serializers.Serializer):
    """One section of a definition (``validate_sections_json``)."""

    name = serializers.CharField()
    order = serializers.IntegerField(required=False)
    visible = serializers.BooleanField(required=False)
    layout = serializers.ChoiceField(choices=_SECTION_LAYOUTS, required=False)
    attribute_flow = AttributeFlowTokenSerializer(many=True, required=False)


class AttributeBlockSerializer(serializers.Serializer):
    """One attribute entry of a definition (``normalize_attribute``).

    ``name``/``kind``/``type`` are the module's ``_REQUIRED_KEYS``; every other
    key is one of its documented defaults and therefore optional on a write
    while always present in a stored/returned block.

    ``editable`` is deliberately declared as free JSON: ``EDITABLE_VALUES``
    accepts ``true``, ``false`` **and** the strings ``"workflow"``/``"system"``/
    ``"automation"``, a union the OpenAPI 3.0 type system cannot express in a
    single field. ``default`` is free JSON for the same reason (an attribute's
    default value is typed by its own ``type``).
    """

    name = serializers.CharField()
    kind = serializers.ChoiceField(choices=_ATTRIBUTE_KINDS)
    type = serializers.ChoiceField(choices=_ATTRIBUTE_TYPES)
    widget_key = serializers.CharField(required=False, allow_null=True)
    fields = serializers.ListField(child=serializers.JSONField(), required=False)
    options = AttributeOptionSerializer(many=True, required=False)
    required = serializers.BooleanField(required=False)
    visible = serializers.BooleanField(required=False)
    locked = serializers.BooleanField(required=False)
    editable = serializers.JSONField(
        required=False,
        help_text='true, false, "workflow", "system" or "automation".',
    )
    stage_mandatory = serializers.BooleanField(required=False)
    section = serializers.CharField(required=False)
    order = serializers.IntegerField(required=False)
    label = I18nTextSerializer(required=False)
    help_text = I18nTextSerializer(required=False)
    default = serializers.JSONField(required=False, allow_null=True)
    validation = ValidationRulesSerializer(required=False)
    ai_elicit = serializers.BooleanField(required=False)
    export = serializers.BooleanField(required=False)
    audience = serializers.ChoiceField(choices=_AUDIENCES, required=False)
    multiple = serializers.BooleanField(required=False)
    allow_external = serializers.BooleanField(required=False)
    copyable = serializers.BooleanField(required=False)
    reveal = serializers.ChoiceField(choices=_REVEALS, required=False)
    mask = serializers.ChoiceField(choices=_MASKS, required=False)
    display_format = serializers.ChoiceField(
        choices=_DISPLAY_FORMATS, required=False
    )
    deprecated = serializers.BooleanField(required=False)
    deprecated_reason = serializers.CharField(required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# attribute-definition resources
# ---------------------------------------------------------------------------


class GlobalAttributeDefinitionSerializer(serializers.Serializer):
    """``AttributeDefinitionService._global_payload`` — one tenant-wide default.

    A missing row is not a 404: it answers with ``initialized: false`` and
    empty lists so the UI can offer an "Initialize" affordance.
    """

    item_type = serializers.CharField()
    preset = serializers.CharField()
    initialized = serializers.BooleanField()
    version = serializers.IntegerField()
    attributes = AttributeBlockSerializer(many=True)
    sections = SectionSerializer(many=True)
    section_flow = SectionFlowTokenSerializer(
        many=True,
        required=False,
        help_text="Present only when the stored definition carries a flow.",
    )
    propagated_workspace_count = serializers.IntegerField(
        required=False,
        help_text="Present on a write that propagated to on-default workspaces.",
    )


class WorkspaceAttributeDefinitionSerializer(serializers.Serializer):
    """``AttributeDefinitionService._workspace_payload`` — resolved definition.

    ``origins`` is the read-only per-attribute provenance map of Task 4
    (spec section 4.2), keyed by attribute name.
    """

    item_type = serializers.CharField()
    preset = serializers.CharField()
    is_customized = serializers.BooleanField()
    version = serializers.IntegerField()
    attributes = AttributeBlockSerializer(many=True)
    origins = serializers.DictField(
        child=serializers.ChoiceField(choices=_ORIGINS),
        help_text="attribute name -> 'global' | 'global_customized' | "
        "'workspace_only'.",
    )
    sections = SectionSerializer(many=True)
    section_flow = SectionFlowTokenSerializer(
        many=True, required=False,
        help_text="Present only when the stored definition carries a flow.",
    )


class AttributeDefinitionDocumentSerializer(serializers.Serializer):
    """A definition payload of either scope.

    ``POST .../attribute-catalog/{id}/add-to-definition/`` answers with the
    global default **or** a workspace override depending on the scope the caller
    asked for, so the response documents the union: ``is_customized``/``origins``
    appear on the workspace side, ``initialized`` on the global side.
    """

    item_type = serializers.CharField()
    preset = serializers.CharField()
    initialized = serializers.BooleanField(required=False)
    is_customized = serializers.BooleanField(required=False)
    version = serializers.IntegerField()
    attributes = AttributeBlockSerializer(many=True)
    origins = serializers.DictField(
        child=serializers.ChoiceField(choices=_ORIGINS), required=False
    )
    sections = SectionSerializer(many=True)
    section_flow = SectionFlowTokenSerializer(many=True, required=False)
    propagated_workspace_count = serializers.IntegerField(required=False)


class AttributeDefinitionListSerializer(serializers.Serializer):
    """``GET /attribute-defaults/`` envelope."""

    definitions = GlobalAttributeDefinitionSerializer(many=True)


class AttributeDefinitionUpdateRequestSerializer(serializers.Serializer):
    """Body of ``PUT /attribute-defaults/{item_type}/{preset}/`` (and the
    workspace twin).

    ``sections``/``section_flow`` are optional: an absent key means "leave the
    row's current value unchanged", which is what the views' ``_read_sections``
    / ``_read_section_flow`` helpers implement.
    """

    attributes = AttributeBlockSerializer(many=True)
    sections = SectionSerializer(many=True, required=False)
    section_flow = SectionFlowTokenSerializer(many=True, required=False)


class AttributeReorderRequestSerializer(serializers.Serializer):
    """Body of the ``.../reorder/`` routes (feature #1260).

    ``after`` omitted = move to the front of the target section; ``version``
    omitted = skip the optimistic-lock precondition.
    """

    name = serializers.CharField()
    section = serializers.CharField()
    after = serializers.CharField(required=False)
    version = serializers.IntegerField(required=False)


class AttributeDefinitionVersionSerializer(serializers.Serializer):
    """Definition document produced by ``export_definition``.

    ``schema_version`` guards the importer against a future format change;
    ``section_flow`` is absent when the stored definition carries none.
    """

    schema_version = serializers.IntegerField()
    item_type = serializers.CharField()
    attributes = AttributeBlockSerializer(many=True)
    sections = SectionSerializer(many=True)
    section_flow = SectionFlowTokenSerializer(many=True, required=False)


class AttributeUsageResponseSerializer(serializers.Serializer):
    """``GET .../attribute-definitions/{item_type}/usage/`` answer."""

    count = serializers.IntegerField(
        help_text="Artifacts referencing the attribute (or one of its options)."
    )


# ---------------------------------------------------------------------------
# attribute-catalog resources
# ---------------------------------------------------------------------------


class AttributeCatalogEntrySerializer(serializers.Serializer):
    """``AttributeCatalogService._entry_payload`` — one catalog entry."""

    id = serializers.CharField()
    name = serializers.CharField()
    definition = AttributeBlockSerializer(
        help_text="A reusable kind='extended' attribute block."
    )
    category = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    label = I18nTextSerializer()
    help_text = I18nTextSerializer()
    origin = serializers.CharField(allow_blank=True)
    deprecated = serializers.BooleanField()
    version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class AttributeCatalogEntryDocumentSerializer(serializers.Serializer):
    """``_entry_document`` — the export/import projection of one entry.

    Everything but the storage metadata (``id``/``version``/timestamps), so an
    exported document can be re-imported without carrying instance identity.
    """

    name = serializers.CharField()
    definition = AttributeBlockSerializer()
    category = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    label = I18nTextSerializer()
    help_text = I18nTextSerializer()
    origin = serializers.CharField(allow_blank=True)
    deprecated = serializers.BooleanField()


class AttributeCatalogListSerializer(serializers.Serializer):
    """``GET /attribute-catalog/`` and ``/attribute-catalog/search/`` envelope."""

    entries = AttributeCatalogEntrySerializer(many=True)


class AttributeCatalogCreateRequestSerializer(serializers.Serializer):
    """Body of ``POST /attribute-catalog/``."""

    name = serializers.CharField()
    definition = AttributeBlockSerializer()
    category = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    label = I18nTextSerializer(required=False)
    help_text = I18nTextSerializer(required=False)
    origin = serializers.CharField(required=False, allow_blank=True)


class AttributeCatalogUpdateRequestSerializer(serializers.Serializer):
    """Body of ``PUT``/``PATCH /attribute-catalog/{entry_id}/``.

    Partial semantics: only the keys actually sent are touched, so all fields
    are optional here.
    """

    name = serializers.CharField(required=False)
    definition = AttributeBlockSerializer(required=False)
    category = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    label = I18nTextSerializer(required=False)
    help_text = I18nTextSerializer(required=False)
    origin = serializers.CharField(required=False, allow_blank=True)
    deprecated = serializers.BooleanField(required=False)


class AttributeCatalogDeprecateRequestSerializer(serializers.Serializer):
    """Body of ``POST /attribute-catalog/{entry_id}/deprecate/``.

    An omitted flag means "deprecate" (``default=true`` in the view).
    """

    deprecated = serializers.BooleanField(required=False)


class AttributeCatalogDocumentSerializer(serializers.Serializer):
    """``GET /attribute-catalog/export/`` — a re-importable document."""

    schema_version = serializers.IntegerField()
    document_type = serializers.CharField(
        help_text="Always 'attribute_catalog'.",
    )
    entries = AttributeCatalogEntryDocumentSerializer(many=True)


class AttributeCatalogImportRequestSerializer(serializers.Serializer):
    """Body of ``POST /attribute-catalog/import/``.

    A previously exported document: ``schema_version`` must equal the current
    format version and ``entries`` must be present, otherwise
    ``AttributeCatalogService`` answers 400 (the transport itself accepts any
    JSON object). ``document_type`` is echoed by the exporter but not checked on
    import; ``on_collision`` may also be given as a query parameter (the query
    parameter wins).
    """

    schema_version = serializers.IntegerField()
    document_type = serializers.CharField(required=False)
    entries = AttributeCatalogEntryDocumentSerializer(many=True)
    on_collision = serializers.ChoiceField(choices=_ON_COLLISION, required=False)


class AttributeCatalogImportSummarySerializer(serializers.Serializer):
    """``import_catalog`` summary."""

    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    total = serializers.IntegerField()


class AttributeCatalogAddToDefinitionRequestSerializer(serializers.Serializer):
    """Body of ``POST /attribute-catalog/{entry_id}/add-to-definition/``.

    Exactly one of ``preset``/``workspace_id`` is required; the service
    answers 400 otherwise, so both stay declared-but-optional here.
    """

    item_type = serializers.CharField()
    preset = serializers.ChoiceField(
        choices=["minimal", "standard", "extended"], required=False
    )
    workspace_id = serializers.UUIDField(required=False)
    on_collision = serializers.ChoiceField(choices=_ON_COLLISION, required=False)


class AttributeCatalogAddToDefinitionResponseSerializer(serializers.Serializer):
    """Result of the one-shot copy-into-definition operation."""

    definition = AttributeDefinitionDocumentSerializer()
    catalog_entry_id = serializers.CharField()
    on_collision = serializers.ChoiceField(choices=_ON_COLLISION)
