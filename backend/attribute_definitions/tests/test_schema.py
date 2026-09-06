"""Pure schema-vocabulary tests — no DB, no Django settings needed."""
from __future__ import annotations

import pytest

from attribute_definitions.schema import (
    AttributeSchemaError,
    normalize_attribute,
    validate_definition_json,
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
