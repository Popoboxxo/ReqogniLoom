"""Legacy field-config migration (spec section 4).

Only the pure helper functions (``apply_visibility_config``,
``custom_field_to_attribute``, ``FIELD_TYPE_MAP``) are covered here.

The ``@pytest.mark.django_db`` tests that used to exercise ``forwards()``/
``backwards()`` directly against the live app registry (calling
``migration.forwards(django.apps.apps, None)`` after creating real
``AttributeVisibilityConfig``/``CustomFieldDefinition`` rows) were removed in
Task 9 (spec section 4, "removed, not deprecated"): ``forwards()`` does
``apps.get_model("persistence", "AttributeVisibilityConfig")`` internally, and
that model — along with ``CustomFieldDefinition`` — no longer exists once
Task 9's own migration (``persistence/migrations/0080_...``) drops them. This
migration (0003) is frozen, correct history: it still applies fine via the
real ``manage.py migrate`` executor (which hands ``forwards()`` *historical*
model classes resolved from the migration graph, not live ones), but it can
no longer be driven through the live app registry the way this test file did.
Re-exercising it would require a full ``MigrationExecutor``-based test
(applying migrations up to 0002, writing legacy rows via the historical
models, migrating to 0003, then asserting) — out of scope for Task 9, which
only needs the schema-migration-does-not-crash property, covered instead by
``persistence/tests/test_retire_legacy_field_config.py``.
"""
from __future__ import annotations

import importlib

from attribute_definitions.schema import normalize_attribute

migration = importlib.import_module(
    "attribute_definitions.migrations.0003_migrate_legacy_field_config"
)


def test_field_type_map_is_exactly_the_spec_mapping() -> None:
    assert migration.FIELD_TYPE_MAP == {
        "text": "text", "number": "number", "dropdown": "enum"
    }


def test_apply_visibility_config_sets_visible_and_required() -> None:
    attributes = [normalize_attribute({"name": "uid", "kind": "core", "type": "text"})]
    out = migration.apply_visibility_config(
        attributes,
        [{"attribute_name": "uid", "is_visible": False, "is_required": True}],
    )
    assert out[0]["visible"] is False
    assert out[0]["required"] is True


def test_apply_visibility_config_never_touches_a_locked_attribute() -> None:
    locked = normalize_attribute({
        "name": "status", "kind": "core", "type": "enum", "locked": True,
        "editable": "workflow",
        "options": [{"value": "d", "label_de": "D", "label_en": "D"}],
    })
    out = migration.apply_visibility_config(
        [locked], [{"attribute_name": "status", "is_visible": False, "is_required": False}]
    )
    assert out[0]["visible"] is True


def test_apply_visibility_config_ignores_an_unknown_attribute_name() -> None:
    attributes = [normalize_attribute({"name": "uid", "kind": "core", "type": "text"})]
    out = migration.apply_visibility_config(
        attributes, [{"attribute_name": "gone", "is_visible": False, "is_required": True}]
    )
    assert [a["name"] for a in out] == ["uid"]
    assert out[0]["visible"] is True


def test_custom_field_to_attribute_maps_dropdown_to_enum_with_options() -> None:
    out = migration.custom_field_to_attribute(
        {"name": "Kostenstelle", "field_type": "dropdown", "is_required": True,
         "options": ["A", "B"], "order": 3},
        order=3,
    )
    assert out["kind"] == "extended"
    assert out["type"] == "enum"
    assert out["required"] is True
    assert out["options"] == [
        {"value": "A", "label_de": "A", "label_en": "A"},
        {"value": "B", "label_de": "B", "label_en": "B"},
    ]
    assert out["section"] == "custom"


def test_custom_field_to_attribute_maps_text_and_number() -> None:
    assert migration.custom_field_to_attribute(
        {"name": "n", "field_type": "number", "is_required": False,
         "options": [], "order": 0}, order=0
    )["type"] == "number"
    assert migration.custom_field_to_attribute(
        {"name": "t", "field_type": "text", "is_required": False,
         "options": [], "order": 0}, order=0
    )["type"] == "text"


def test_custom_field_to_attribute_falls_back_to_text_for_dropdown_with_no_options() -> None:
    """C-1: an `enum` with empty options crashes normalize_attribute - fall back to text."""
    out = migration.custom_field_to_attribute(
        {"name": "empty_dropdown", "field_type": "dropdown", "is_required": False,
         "options": [], "order": 0},
        order=0,
    )
    assert out["type"] == "text"
    assert out["options"] == []

    # Missing "options" key entirely (row.get("options") or []) is the same case.
    out_missing = migration.custom_field_to_attribute(
        {"name": "no_options_key", "field_type": "dropdown", "is_required": False,
         "order": 0},
        order=0,
    )
    assert out_missing["type"] == "text"
