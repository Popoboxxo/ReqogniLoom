"""Rule engine for artifact field validation (spec section 5)."""
from __future__ import annotations

import pytest

from attribute_definitions.field_validation import (
    FieldValidationError,
    validate_values,
)
from attribute_definitions.schema import normalize_attribute


def _attrs(*raw: dict) -> list[dict]:
    return [normalize_attribute(r) for r in raw]


DEF = _attrs(
    {"name": "title", "kind": "core", "type": "text", "required": True,
     "validation": {"length": 200}},
    {"name": "description", "kind": "core", "type": "textarea"},
    {"name": "uid", "kind": "core", "type": "text",
     "validation": {"regex": r"^REQ-\d+$"}},
    {"name": "effort", "kind": "core", "type": "number",
     "validation": {"min": 1, "max": 13}},
    {"name": "hidden_note", "kind": "core", "type": "text", "required": True,
     "visible": False},
    {"name": "sap_id", "kind": "extended", "type": "text", "required": True},
    {"name": "cost_centre", "kind": "extended", "type": "text"},
)


def test_create_requires_every_visible_required_field() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"description": "d"}, None)
    assert set(exc.value.errors) == {"title", "sap_id"}


def test_create_passes_when_all_required_fields_are_set() -> None:
    validate_values(DEF, {"title": "T", "custom_fields": {"sap_id": "S"}}, None)


def test_create_ignores_required_on_an_invisible_attribute() -> None:
    """visible=False + required=True must not block creation (spec section 5)."""
    validate_values(DEF, {"title": "T", "custom_fields": {"sap_id": "S"}}, None)


def test_update_does_not_block_a_required_field_the_request_never_touches() -> None:
    """Grandfathering for legacy data: an untouched empty required field is fine."""
    validate_values(DEF, {"description": "d"}, {"title": "", "description": ""})


def test_update_rejects_clearing_a_required_field() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"title": "   "}, {"title": "old"})
    assert "title" in exc.value.errors


def test_update_rejects_clearing_a_required_extended_field() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"custom_fields": {"sap_id": ""}}, {"title": "old"})
    assert "sap_id" in exc.value.errors


def test_unknown_extended_field_is_rejected() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"custom_fields": {"nope": "x"}}, {"title": "old"})
    assert "nope" in exc.value.errors


def test_unknown_top_level_field_is_ignored() -> None:
    """Serializer control fields (change_reason, expected_version, ...) are not
    attributes; the ViewSet's own _validate_patch_payload guards those."""
    validate_values(DEF, {"change_reason": "why", "expected_version": 3}, {"title": "t"})


def test_regex_rule_is_enforced_on_a_present_field() -> None:
    validate_values(DEF, {"uid": "REQ-42"}, {"title": "t"})
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"uid": "nope"}, {"title": "t"})
    assert "uid" in exc.value.errors


def test_length_rule_is_enforced() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"title": "x" * 201}, {"title": "t"})
    assert "title" in exc.value.errors


def test_min_max_rules_are_enforced_on_numbers() -> None:
    validate_values(DEF, {"effort": 8}, {"title": "t"})
    with pytest.raises(FieldValidationError):
        validate_values(DEF, {"effort": 0}, {"title": "t"})
    with pytest.raises(FieldValidationError):
        validate_values(DEF, {"effort": 21}, {"title": "t"})


def test_non_numeric_value_for_a_number_attribute_is_rejected() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"effort": "big"}, {"title": "t"})
    assert "effort" in exc.value.errors


def test_none_value_skips_the_range_rules_but_still_trips_required() -> None:
    validate_values(DEF, {"effort": None}, {"title": "t"})
    with pytest.raises(FieldValidationError):
        validate_values(DEF, {"title": None}, {"title": "t"})


def test_enum_value_must_be_one_of_the_options() -> None:
    attrs = _attrs({
        "name": "category", "kind": "core", "type": "enum",
        "options": [{"value": "a", "label_de": "A", "label_en": "A"},
                    {"value": "b", "label_de": "B", "label_en": "B"}],
    })
    validate_values(attrs, {"category": "a"}, {})
    with pytest.raises(FieldValidationError) as exc:
        validate_values(attrs, {"category": "z"}, {})
    assert "category" in exc.value.errors


def test_multi_enum_value_must_be_a_list_of_known_options() -> None:
    attrs = _attrs({
        "name": "tags", "kind": "core", "type": "multi-enum",
        "options": [{"value": "a", "label_de": "A", "label_en": "A"}],
    })
    validate_values(attrs, {"tags": ["a"]}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"tags": "a"}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"tags": ["a", "z"]}, {})


def test_boolean_attribute_rejects_a_non_boolean() -> None:
    attrs = _attrs({"name": "flag", "kind": "core", "type": "boolean"})
    validate_values(attrs, {"flag": True}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"flag": "yes"}, {})


def test_widget_attribute_validates_its_bound_fields_not_its_own_name() -> None:
    attrs = _attrs(
        {"name": "risk_matrix", "kind": "core", "type": "widget",
         "widget_key": "risk_matrix_rpz",
         "fields": ["probability", "impact", "detection"]},
        {"name": "detection", "kind": "core", "type": "number",
         "validation": {"min": 1, "max": 10}},
    )
    validate_values(attrs, {"detection": 5}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"detection": 11}, {})
    # The widget's own name is not a payload field and is never demanded.
    validate_values(attrs, {"detection": 5}, None)


def test_all_errors_are_reported_together() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"title": "", "uid": "bad", "effort": 99}, {"title": "t"})
    assert set(exc.value.errors) == {"title", "uid", "effort"}
