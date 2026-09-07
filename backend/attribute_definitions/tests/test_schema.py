"""Pure schema-vocabulary tests — no DB, no Django settings needed."""
from __future__ import annotations

import pytest

from attribute_definitions.schema import (
    ITEM_TYPES,
    PRESETS,
    AttributeSchemaError,
    normalize_attribute,
    stored_attributes,
    validate_definition_json,
    validate_definition_key,
    validate_meta_only_change,
)


def _core(name: str, **over) -> dict:
    base = {"name": name, "kind": "core", "type": "text", "section": "general", "order": 0}
    base.update(over)
    return base


def _locked_status() -> dict:
    return _core(
        "status",
        type="enum",
        options=[{"value": "draft", "label_de": "Entwurf", "label_en": "Draft"}],
        locked=True,
        editable="workflow",
    )


def test_normalize_fills_every_documented_default() -> None:
    out = normalize_attribute({"name": "title", "kind": "core", "type": "text"})
    assert out == {
        "name": "title", "kind": "core", "type": "text", "widget_key": None,
        "fields": [], "options": [], "required": False, "visible": True,
        "locked": False, "editable": True, "section": "general", "order": 0,
        "label": {"de": "", "en": ""}, "help_text": {"de": "", "en": ""},
        "default": None, "validation": {}, "ai_elicit": False, "export": False,
        "audience": "basic",
    }


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "core", "type": "text", "colour": "red"})
    assert "colour" in " ".join(exc.value.errors)


def test_unknown_type_is_rejected() -> None:
    with pytest.raises(AttributeSchemaError):
        normalize_attribute({"name": "x", "kind": "core", "type": "richtext"})


def test_enum_without_options_is_rejected() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "core", "type": "enum"})
    assert "options" in " ".join(exc.value.errors)


def test_option_entries_need_value_and_both_labels() -> None:
    with pytest.raises(AttributeSchemaError):
        normalize_attribute({"name": "x", "kind": "core", "type": "enum",
                             "options": [{"value": "a", "label_de": "A"}]})


def test_widget_key_only_allowed_for_type_widget() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "core", "type": "text",
                             "widget_key": "steps_editor"})
    assert "widget_key" in " ".join(exc.value.errors)


def test_type_widget_requires_a_registered_widget_key_and_fields() -> None:
    with pytest.raises(AttributeSchemaError):
        normalize_attribute({"name": "x", "kind": "core", "type": "widget",
                             "widget_key": "not_registered", "fields": ["a"]})
    ok = normalize_attribute({"name": "x", "kind": "core", "type": "widget",
                              "widget_key": "risk_matrix_rpz",
                              "fields": ["probability", "impact", "detection"]})
    assert ok["fields"] == ["probability", "impact", "detection"]


def test_locked_is_only_allowed_on_core() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "extended", "type": "text",
                             "locked": True})
    assert "locked" in " ".join(exc.value.errors)


def test_locked_defaults_visible_true_when_omitted() -> None:
    assert normalize_attribute(_locked_status())["visible"] is True


def test_locked_rejects_explicit_visible_false() -> None:
    raw = _locked_status()
    raw["visible"] = False
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute(raw)
    assert "visible" in " ".join(exc.value.errors)


def test_editable_accepts_workflow_literal_and_rejects_others() -> None:
    assert normalize_attribute(_core("s", editable="workflow"))["editable"] == "workflow"
    with pytest.raises(AttributeSchemaError):
        normalize_attribute(_core("s", editable="sometimes"))


def test_audience_defaults_to_basic_and_rejects_other_values() -> None:
    assert normalize_attribute(_core("a"))["audience"] == "basic"
    assert normalize_attribute(_core("a", audience="expert"))["audience"] == "expert"
    with pytest.raises(AttributeSchemaError):
        normalize_attribute(_core("a", audience="admin"))


def test_validation_rejects_unknown_rule_keys() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute(_core("a", validation={"startswith": "X"}))
    assert "startswith" in " ".join(exc.value.errors)


def test_validate_definition_json_rejects_duplicate_names() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        validate_definition_json({"attributes": [_core("title"), _core("title")]})
    assert "title" in " ".join(exc.value.errors)


def test_validate_definition_json_sorts_by_section_then_order_then_name() -> None:
    out = validate_definition_json({"attributes": [
        _core("b", section="zzz", order=1),
        _core("a", section="general", order=5),
        _core("c", section="general", order=1),
    ]})
    assert [a["name"] for a in out["attributes"]] == ["c", "a", "b"]


def test_meta_only_change_rejects_renaming_a_core_attribute() -> None:
    old = [normalize_attribute(_core("title"))]
    new = [normalize_attribute(_core("headline"))]
    with pytest.raises(AttributeSchemaError) as exc:
        validate_meta_only_change(old, new)
    assert "title" in " ".join(exc.value.errors)


def test_meta_only_change_rejects_retyping_or_dropping_a_core_attribute() -> None:
    old = [normalize_attribute(_core("title")), normalize_attribute(_core("uid"))]
    with pytest.raises(AttributeSchemaError):
        validate_meta_only_change(old, [normalize_attribute(_core("title", type="textarea")),
                                        normalize_attribute(_core("uid"))])
    with pytest.raises(AttributeSchemaError):
        validate_meta_only_change(old, [normalize_attribute(_core("title"))])


def test_meta_only_change_allows_a_new_extended_attribute() -> None:
    old = [normalize_attribute(_core("title"))]
    new = old + [normalize_attribute({"name": "sap_id", "kind": "extended", "type": "text"})]
    validate_meta_only_change(old, new)


def test_meta_only_change_rejects_a_new_core_attribute() -> None:
    old = [normalize_attribute(_core("title"))]
    new = old + [normalize_attribute(_core("smuggled"))]
    with pytest.raises(AttributeSchemaError):
        validate_meta_only_change(old, new)


def test_meta_only_change_allows_core_meta_properties() -> None:
    old = [normalize_attribute(_core("title"))]
    new = [normalize_attribute(_core("title", required=True, section="classification",
                                     order=9, audience="expert", ai_elicit=True,
                                     export=True))]
    validate_meta_only_change(old, new)


def test_meta_only_change_rejects_touching_locked_visible_required_editable() -> None:
    old = [normalize_attribute(_locked_status())]
    for prop, value in (("required", True), ("editable", True), ("visible", False)):
        changed = _locked_status()
        changed[prop] = value
        with pytest.raises(AttributeSchemaError) as exc:
            validate_meta_only_change(old, [normalize_attribute(changed)])
        assert "status" in " ".join(exc.value.errors)


def test_meta_only_change_allows_cosmetics_on_a_locked_attribute() -> None:
    old = [normalize_attribute(_locked_status())]
    moved = _locked_status()
    moved.update(section="header", order=99, label={"de": "Zustand", "en": "State"})
    validate_meta_only_change(old, [normalize_attribute(moved)])


# --- Ledger item (a): validation rule VALUES are type-checked -----------------


@pytest.mark.parametrize(
    "rules",
    [
        {"length": "abc"},
        {"length": [1]},
        {"length": -1},
        {"length": True},
        {"length": 1.5},
        {"min": "x"},
        {"max": None},
        {"min": True},
        {"regex": ["^a$"]},
        {"regex": "["},
    ],
)
def test_malformed_validation_rule_values_are_rejected(rules) -> None:
    """A bad rule used to be stored and then crash EVERY later artifact save."""
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute(_core("a", validation=rules))
    assert "validation" in " ".join(exc.value.errors)


def test_well_formed_validation_rules_survive_normalization() -> None:
    out = normalize_attribute(
        _core("a", validation={"length": 10, "min": 1, "max": 2.5, "regex": r"^\d+$"})
    )
    assert out["validation"] == {
        "min": 1, "max": 2.5, "length": 10, "regex": r"^\d+$",
    }


# --- Ledger item (e): stored rows are normalized before being indexed --------


def test_stored_attributes_normalizes_a_row_missing_optional_keys() -> None:
    out = stored_attributes({"attributes": [{"name": "t", "kind": "core", "type": "text"}]})
    assert out[0]["visible"] is True and out[0]["ai_elicit"] is False


def test_stored_attributes_raises_a_schema_error_on_a_corrupt_row() -> None:
    """The point of the helper: a schema error (→400), never a KeyError (→500)."""
    with pytest.raises(AttributeSchemaError):
        stored_attributes({"attributes": [{"name": "t", "type": "text"}]})


def test_stored_attributes_tolerates_a_null_definition_json() -> None:
    assert stored_attributes(None) == []


# --- Ledger item (h): the (item_type, preset) key vocabulary -----------------


def test_validate_definition_key_rejects_a_typo() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        validate_definition_key("Risk", "standrad")
    assert "standrad" in " ".join(exc.value.errors)


def test_validate_definition_key_rejects_an_unknown_item_type() -> None:
    with pytest.raises(AttributeSchemaError):
        validate_definition_key("Sprocket", "standard")


def test_validate_definition_key_accepts_every_bootstrapped_combination() -> None:
    for item_type in ITEM_TYPES:
        for preset in PRESETS:
            validate_definition_key(item_type, preset)


# --- Task 2 finding: privilege escalation through a meta-only PUT ------------


def test_meta_only_change_rejects_promoting_an_extended_attribute_to_core() -> None:
    """extended → core+locked in one PUT used to pass: loop 1 skipped non-core
    old entries and loop 2 only inspected names that were NEW."""
    old = [normalize_attribute(_core("sap_id", kind="extended"))]
    promoted = [normalize_attribute(_core("sap_id", kind="core", locked=True))]
    with pytest.raises(AttributeSchemaError) as exc:
        validate_meta_only_change(old, promoted)
    joined = " ".join(exc.value.errors)
    assert "kind" in joined and "locked" in joined


def test_meta_only_change_rejects_demoting_a_core_attribute_to_extended() -> None:
    old = [normalize_attribute(_core("title"))]
    demoted = [normalize_attribute(_core("title", kind="extended"))]
    with pytest.raises(AttributeSchemaError):
        validate_meta_only_change(old, demoted)


def test_meta_only_change_rejects_locking_an_unlocked_core_attribute() -> None:
    old = [normalize_attribute(_core("title"))]
    locked = [normalize_attribute(_core("title", locked=True))]
    with pytest.raises(AttributeSchemaError) as exc:
        validate_meta_only_change(old, locked)
    assert "locked" in " ".join(exc.value.errors)


def test_meta_only_change_still_allows_an_ordinary_meta_edit() -> None:
    old = [normalize_attribute(_core("title"))]
    edited = [normalize_attribute(_core("title", required=True, order=5))]
    validate_meta_only_change(old, edited)
