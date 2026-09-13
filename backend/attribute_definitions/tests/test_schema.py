"""Pure schema-vocabulary tests — no DB, no Django settings needed."""
from __future__ import annotations

import pytest

from attribute_definitions.schema import (
    ITEM_TYPES,
    PRESETS,
    AttributeSchemaError,
    effective_attribute_flow,
    effective_section_flow,
    materialize_attribute_flow,
    materialize_section_flow,
    materialize_sections,
    normalize_attribute,
    normalize_flow_token,
    normalize_section,
    resolve_attribute_span,
    stored_attributes,
    stored_section_flow,
    stored_sections,
    validate_attribute_flow_json,
    validate_definition_json,
    validate_definition_key,
    validate_meta_only_change,
    validate_section_flow_json,
    validate_sections_json,
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
        "audience": "basic", "multiple": False, "allow_external": False,
        "copyable": False, "reveal": "always", "mask": "none",
        "display_format": "text",
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


def test_editable_accepts_the_system_and_automation_literals() -> None:
    """Spec section 6: ``system`` (server-owned) and ``automation`` (AWMS)."""
    for value in ("system", "automation"):
        assert normalize_attribute(_core("s", editable=value))["editable"] == value


def test_locked_system_attribute_may_be_hidden() -> None:
    """Spec sections 3/5: the synthetic Artifact ``id`` is locked AND hidden."""
    out = normalize_attribute(
        {
            "name": "id",
            "kind": "core",
            "type": "text",
            "editable": "system",
            "locked": True,
            "visible": False,
        }
    )
    assert out["visible"] is False
    assert out["locked"] is True


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
                                     export=True, copyable=True, reveal="click",
                                     mask="short", display_format="mono"))]
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


# --- Ledger gap #5: CORE_EDITABLE_META_PROPERTIES was never enforced ---------


def test_meta_only_change_rejects_widget_key_and_fields_on_a_core_attribute() -> None:
    """Live-proven gap: an admin could freely swap `widget_key`/`fields` on a
    core widget attribute because `validate_meta_only_change` never checked
    them against `CORE_EDITABLE_META_PROPERTIES`."""
    old = [normalize_attribute(_core(
        "risk_matrix", type="widget", widget_key="risk_matrix_rpz",
        fields=["probability", "severity"],
    ))]
    swapped_widget = [normalize_attribute(_core(
        "risk_matrix", type="widget", widget_key="tag_input",
        fields=["probability", "severity"],
    ))]
    with pytest.raises(AttributeSchemaError) as exc:
        validate_meta_only_change(old, swapped_widget)
    assert "widget_key" in " ".join(exc.value.errors)

    narrowed_fields = [normalize_attribute(_core(
        "risk_matrix", type="widget", widget_key="risk_matrix_rpz",
        fields=["probability"],
    ))]
    with pytest.raises(AttributeSchemaError) as exc:
        validate_meta_only_change(old, narrowed_fields)
    assert "fields" in " ".join(exc.value.errors)


def test_meta_only_change_rejects_validation_rule_change_on_a_core_attribute() -> None:
    old = [normalize_attribute(_core("code", validation={"regex": r"^\d+$"}))]
    new = [normalize_attribute(_core("code", validation={"regex": r"^[a-z]+$"}))]
    with pytest.raises(AttributeSchemaError) as exc:
        validate_meta_only_change(old, new)
    assert "validation" in " ".join(exc.value.errors)


# --- Task 7: sections[] --------------------------------------------------


def test_normalize_section_applies_defaults() -> None:
    out = normalize_section({"name": "general"})
    assert out == {"name": "general", "order": 0, "visible": True, "layout": "full"}


def test_normalize_section_rejects_an_unknown_layout() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_section({"name": "general", "layout": "third"})
    assert "layout" in " ".join(exc.value.errors)


def test_normalize_section_rejects_a_missing_name() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_section({})
    assert "name" in " ".join(exc.value.errors)


def test_normalize_section_rejects_an_unknown_key() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_section({"name": "general", "extra": True})
    assert "extra" in " ".join(exc.value.errors)


def test_validate_sections_json_rejects_a_duplicate_name() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        validate_sections_json([{"name": "a"}, {"name": "a"}])
    assert "duplicate" in " ".join(exc.value.errors)


def test_validate_sections_json_sorts_by_order_then_name() -> None:
    out = validate_sections_json([{"name": "b", "order": 0}, {"name": "a", "order": 0}])
    assert [s["name"] for s in out] == ["a", "b"]


def test_materialize_sections_derives_first_appearance_order() -> None:
    attributes = [
        normalize_attribute(_core("title", section="general")),
        normalize_attribute({"name": "note", "kind": "extended", "type": "text", "section": "extra"}),
        normalize_attribute({"name": "note2", "kind": "extended", "type": "text", "section": "general"}),
    ]
    out = materialize_sections(attributes)
    assert out == [
        {"name": "general", "order": 0, "visible": True, "layout": "full"},
        {"name": "extra", "order": 1, "visible": True, "layout": "full"},
    ]


def test_validate_definition_json_normalizes_sections_when_present() -> None:
    payload = {
        "attributes": [_core("title")],
        "sections": [{"name": "general"}],
    }
    out = validate_definition_json(payload)
    assert out["sections"] == [
        {"name": "general", "order": 0, "visible": True, "layout": "full"}
    ]


def test_validate_definition_json_omits_sections_key_when_absent() -> None:
    out = validate_definition_json({"attributes": [_core("title")]})
    assert "sections" not in out


def test_stored_sections_returns_empty_for_a_row_with_no_sections_key() -> None:
    assert stored_sections({"attributes": []}) == []


def test_stored_sections_normalizes_a_stored_list() -> None:
    out = stored_sections({"attributes": [], "sections": [{"name": "general"}]})
    assert out == [{"name": "general", "order": 0, "visible": True, "layout": "full"}]


# ---------------------------------------------------------------------------
# actor attribute type (Attribut v3 WS2, spec section 4)
# ---------------------------------------------------------------------------


def test_actor_is_a_known_attribute_type() -> None:
    out = normalize_attribute({"name": "deciders", "kind": "extended", "type": "actor"})
    assert out["type"] == "actor"
    assert out["multiple"] is False
    assert out["allow_external"] is False


def test_actor_properties_round_trip_and_require_booleans() -> None:
    out = normalize_attribute(
        {
            "name": "deciders",
            "kind": "extended",
            "type": "actor",
            "multiple": True,
            "allow_external": True,
        }
    )
    assert out["multiple"] is True
    assert out["allow_external"] is True

    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute(
            {"name": "deciders", "kind": "extended", "type": "actor", "multiple": "yes"}
        )
    assert "multiple" in " ".join(exc.value.errors)


def test_legacy_user_type_still_normalizes() -> None:
    """Spec section 4: the previous ``user`` type stays readable."""
    out = normalize_attribute({"name": "owner_user", "kind": "core", "type": "user"})
    assert out["type"] == "user"


# ---------------------------------------------------------------------------
# Generic display/interaction properties (Attribut v3 WS3, spec section 5)
# ---------------------------------------------------------------------------


def test_display_properties_default_to_the_spec_values() -> None:
    out = normalize_attribute(_core("title"))
    assert out["copyable"] is False
    assert out["reveal"] == "always"
    assert out["mask"] == "none"
    assert out["display_format"] == "text"


def test_display_properties_round_trip() -> None:
    out = normalize_attribute(
        _core(
            "id",
            copyable=True,
            reveal="shortcut",
            mask="short",
            display_format="mono",
        )
    )
    assert out["copyable"] is True
    assert out["reveal"] == "shortcut"
    assert out["mask"] == "short"
    assert out["display_format"] == "mono"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("reveal", "hover"),
        ("mask", "full"),
        ("display_format", "rich"),
        ("copyable", "yes"),
    ],
)
def test_invalid_display_property_values_are_rejected(key, value) -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute(_core("title", **{key: value}))
    assert key in " ".join(exc.value.errors)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("reveal", ["click"]),
        ("reveal", {"mode": "click"}),
        ("mask", ["short"]),
        ("display_format", {"format": "mono"}),
        ("audience", ["expert"]),
        ("editable", {"editable": "system"}),
    ],
)
def test_unhashable_enum_values_are_rejected_as_schema_errors(key, value) -> None:
    """A list/dict is unhashable, so ``value not in frozenset`` would raise
    ``TypeError`` (a 500) before the guard. It must become a 400 instead."""
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute(_core("title", **{key: value}))
    assert key in " ".join(exc.value.errors)


def test_stored_attributes_backfills_the_display_properties() -> None:
    """A row written before WS3 normalizes to the documented defaults."""
    out = stored_attributes(
        {"attributes": [{"name": "t", "kind": "core", "type": "text"}]}
    )
    assert out[0]["copyable"] is False
    assert out[0]["reveal"] == "always"
    assert out[0]["mask"] == "none"
    assert out[0]["display_format"] == "text"


# ---------------------------------------------------------------------------
# Attribut v3 WS4 #938 — 12-column layout flow (spec section 7)
# ---------------------------------------------------------------------------


def _flow_section(name: str, **over) -> dict:
    base = {"name": name}
    base.update(over)
    return base


def test_normalize_section_omits_attribute_flow_when_absent() -> None:
    """Additive: a section without a flow keeps the exact pre-WS4 shape, so
    every stored definition normalizes unchanged."""
    out = normalize_section({"name": "general"})
    assert "attribute_flow" not in out


def test_normalize_section_carries_a_valid_attribute_flow() -> None:
    out = normalize_section(
        {
            "name": "general",
            "attribute_flow": [
                {"kind": "attribute", "name": "title", "span": "half"},
                {"kind": "spacer", "size": "sm"},
                {"kind": "attribute", "name": "description"},
            ],
        }
    )
    assert out["attribute_flow"] == [
        {"kind": "attribute", "name": "title", "span": "half"},
        {"kind": "spacer", "size": "sm"},
        {"kind": "attribute", "name": "description", "span": "full"},
    ]


def test_normalize_flow_token_rejects_an_unknown_kind() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_flow_token({"kind": "column"}, allowed_kinds=frozenset({"section"}))
    assert "kind" in " ".join(exc.value.errors)


def test_normalize_flow_token_enforces_the_level_gate() -> None:
    """``section_flow`` never accepts an attribute token and vice versa."""
    with pytest.raises(AttributeSchemaError):
        normalize_flow_token(
            {"kind": "attribute", "name": "title"},
            allowed_kinds=frozenset({"section", "spacer"}),
        )
    with pytest.raises(AttributeSchemaError):
        normalize_flow_token(
            {"kind": "section", "name": "general"},
            allowed_kinds=frozenset({"attribute", "spacer"}),
        )


@pytest.mark.parametrize("span", ["third", "12", "wide"])
def test_normalize_flow_token_rejects_an_invalid_span(span) -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_flow_token(
            {"kind": "attribute", "name": "title", "span": span},
            allowed_kinds=frozenset({"attribute"}),
        )
    assert "span" in " ".join(exc.value.errors)


@pytest.mark.parametrize("size", ["xl", "1", "medium"])
def test_normalize_flow_token_rejects_an_invalid_spacer_size(size) -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_flow_token(
            {"kind": "spacer", "size": size},
            allowed_kinds=frozenset({"spacer"}),
        )
    assert "size" in " ".join(exc.value.errors)


def test_normalize_flow_token_rejects_an_unknown_key() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_flow_token(
            {"kind": "spacer", "size": "sm", "span": "full"},
            allowed_kinds=frozenset({"spacer"}),
        )
    assert "span" in " ".join(exc.value.errors)


@pytest.mark.parametrize(
    "token",
    [
        {"kind": ["section"], "name": "general"},
        {"kind": "attribute", "name": "title", "span": ["half"]},
        {"kind": "spacer", "size": {"value": "sm"}},
    ],
)
def test_normalize_flow_token_rejects_unhashable_values_as_schema_errors(token) -> None:
    """A list/dict is unhashable, so a bare frozenset membership test would
    raise ``TypeError`` (a 500); it must be the documented 400 (WS3-F3)."""
    with pytest.raises(AttributeSchemaError):
        normalize_flow_token(token, allowed_kinds=frozenset({"attribute", "section", "spacer"}))


def test_validate_section_flow_json_preserves_order() -> None:
    flow = [
        {"kind": "section", "name": "content"},
        {"kind": "spacer", "size": "md"},
        {"kind": "section", "name": "general"},
    ]
    assert validate_section_flow_json(flow) == flow


def test_validate_attribute_flow_json_rejects_a_non_list() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        validate_attribute_flow_json({"kind": "attribute", "name": "title"})
    assert "attribute_flow" in " ".join(exc.value.errors)


def test_materialize_section_flow_derives_the_section_order() -> None:
    sections = [
        {"name": "general", "order": 0, "visible": True, "layout": "full"},
        {"name": "extra", "order": 1, "visible": True, "layout": "half"},
    ]
    assert materialize_section_flow(sections) == [
        {"kind": "section", "name": "general"},
        {"kind": "section", "name": "extra"},
    ]


def test_materialize_attribute_flow_derives_full_width_per_attribute() -> None:
    attributes = [
        normalize_attribute(_core("title", order=0)),
        normalize_attribute({"name": "note", "kind": "extended", "type": "text", "order": 1}),
    ]
    assert materialize_attribute_flow(attributes) == [
        {"kind": "attribute", "name": "title", "span": "full"},
        {"kind": "attribute", "name": "note", "span": "full"},
    ]


def test_validate_definition_json_carries_section_and_attribute_flows() -> None:
    payload = {
        "attributes": [_core("title", section="general"), _core("note", section="extra")],
        "sections": [
            _flow_section("general"),
            _flow_section(
                "extra",
                attribute_flow=[{"kind": "attribute", "name": "note", "span": "quarter"}],
            ),
        ],
        "section_flow": [
            {"kind": "section", "name": "general"},
            {"kind": "spacer", "size": "lg"},
            {"kind": "section", "name": "extra"},
        ],
    }
    out = validate_definition_json(payload)
    assert out["section_flow"] == payload["section_flow"]
    by_name = {s["name"]: s for s in out["sections"]}
    assert by_name["extra"]["attribute_flow"] == [
        {"kind": "attribute", "name": "note", "span": "quarter"}
    ]
    assert "attribute_flow" not in by_name["general"]


def test_validate_definition_json_omits_the_flow_key_when_absent() -> None:
    out = validate_definition_json({"attributes": [_core("title")]})
    assert "section_flow" not in out


def test_validate_definition_json_rejects_an_invalid_section_flow() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        validate_definition_json(
            {
                "attributes": [_core("title")],
                "section_flow": [{"kind": "attribute", "name": "title"}],
            }
        )
    assert "kind" in " ".join(exc.value.errors)


def test_stored_section_flow_returns_empty_without_the_key() -> None:
    assert stored_section_flow({"attributes": []}) == []


def test_stored_section_flow_normalizes_a_stored_flow() -> None:
    out = stored_section_flow(
        {"attributes": [], "section_flow": [{"kind": "spacer", "size": "lg"}]}
    )
    assert out == [{"kind": "spacer", "size": "lg"}]


def test_effective_section_flow_derives_from_sections_when_absent() -> None:
    definition = {
        "attributes": [],
        "sections": [
            {"name": "general", "order": 0, "visible": True, "layout": "full"},
        ],
    }
    assert effective_section_flow(definition) == [
        {"kind": "section", "name": "general"}
    ]


def test_effective_section_flow_prefers_a_stored_flow() -> None:
    definition = {
        "attributes": [],
        "sections": [{"name": "general", "order": 0, "visible": True, "layout": "full"}],
        "section_flow": [{"kind": "spacer", "size": "sm"}],
    }
    assert effective_section_flow(definition) == [{"kind": "spacer", "size": "sm"}]


def test_effective_attribute_flow_derives_from_attributes_when_absent() -> None:
    section = {"name": "general"}
    attributes = [normalize_attribute(_core("title")), normalize_attribute(_core("note"))]
    assert effective_attribute_flow(section, attributes) == [
        {"kind": "attribute", "name": "title", "span": "full"},
        {"kind": "attribute", "name": "note", "span": "full"},
    ]


def test_effective_attribute_flow_prefers_a_stored_flow() -> None:
    section = {
        "name": "general",
        "attribute_flow": [{"kind": "attribute", "name": "title", "span": "half"}],
    }
    assert effective_attribute_flow(section, [normalize_attribute(_core("title"))]) == [
        {"kind": "attribute", "name": "title", "span": "half"}
    ]


def test_resolve_attribute_span_defaults_to_full_without_a_flow() -> None:
    assert resolve_attribute_span("title", {"name": "general"}) == "full"
    assert resolve_attribute_span("title", None) == "full"
    section = {
        "name": "general",
        "attribute_flow": [{"kind": "attribute", "name": "title", "span": "quarter"}],
    }
    assert resolve_attribute_span("title", section) == "quarter"
    assert resolve_attribute_span("other", section) == "full"

