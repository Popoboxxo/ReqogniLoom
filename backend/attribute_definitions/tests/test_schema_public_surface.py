"""Pins the public surface of the ``attribute_definitions.schema`` facade.

The implementation is split into ``_schema_*`` modules; ``schema.py`` is a
re-export facade consumed by 50+ modules, including a data migration. This
test makes a dropped or renamed export fail here instead of in whichever
importer happens to be exercised first.
"""
from __future__ import annotations

from attribute_definitions import schema

EXPECTED_PUBLIC_NAMES = {
    "ACTOR_TYPES",
    "ALLOWED_KEYS",
    "ATTRIBUTE_FLOW_KINDS",
    "ATTRIBUTE_KINDS",
    "ATTRIBUTE_SPANS",
    "ATTRIBUTE_TYPES",
    "AUDIENCE_VALUES",
    "AttributeDefinitionConflictError",
    "AttributeDefinitionVersionConflict",
    "AttributeSchemaError",
    "CORE_EDITABLE_META_PROPERTIES",
    "DEFAULT_ATTRIBUTE_SPAN",
    "DISPLAY_FORMAT_VALUES",
    "EDITABLE_VALUES",
    "ENTITY_LEVEL_CARRIER_FIELDS",
    "GRID_COLUMNS",
    "ITEM_TYPES",
    "LOCKED_IMMUTABLE_PROPERTIES",
    "MASK_VALUES",
    "PRESETS",
    "REVEAL_VALUES",
    "SECTION_FLOW_KINDS",
    "SECTION_LAYOUTS",
    "SECTION_SPAN_COLUMNS",
    "SPACER_COLUMNS",
    "SPACER_SIZES",
    "SPAN_COLUMNS",
    "SYSTEM_FIELDS_ENABLED_ITEM_TYPES",
    "WIDGET_KEYS",
    "all_entity_carrier_fields",
    "effective_attribute_flow",
    "effective_section_flow",
    "entity_carrier_fields",
    "materialize_attribute_flow",
    "materialize_section_flow",
    "materialize_sections",
    "normalize_attribute",
    "normalize_flow_token",
    "normalize_section",
    "prune_attribute_flows",
    "prune_section_flow",
    "resolve_attribute_span",
    "stored_attributes",
    "stored_section_flow",
    "stored_sections",
    "validate_attribute_flow_json",
    "validate_definition_json",
    "validate_definition_key",
    "validate_meta_only_change",
    "validate_new_attribute_name",
    "validate_section_flow_json",
    "validate_sections_json",
}


def test_all_is_the_frozen_public_surface() -> None:
    assert set(schema.__all__) == EXPECTED_PUBLIC_NAMES


def test_every_public_name_resolves_on_the_facade() -> None:
    missing = [name for name in EXPECTED_PUBLIC_NAMES if not hasattr(schema, name)]
    assert missing == []


def test_no_duplicate_public_names() -> None:
    assert len(schema.__all__) == len(set(schema.__all__))
