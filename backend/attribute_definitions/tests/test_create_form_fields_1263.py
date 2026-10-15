"""Create-form field vocabulary (Issue #1263).

Pure unit tests: ``attribute_definitions.create_form_fields`` is deliberately
Django-free, so this module needs no database and no app registry.
"""
from __future__ import annotations

import pytest

from attribute_definitions.create_form_fields import (
    CreateFormError,
    catalog_field_entries,
    merge_create_form_entries,
    normalize_create_form_entries,
    required_field_keys,
)


def _attribute(name: str, **overrides: object) -> dict:
    base = {
        "name": name,
        "kind": "extended",
        "type": "text",
        "required": False,
        "visible": True,
        "editable": True,
        "section": "general",
        "order": 0,
        "default": None,
    }
    base.update(overrides)
    return base


ATTRIBUTES = [
    _attribute("title", required=True, order=0),
    _attribute("description", order=1),
    _attribute("priority", type="enum", default="medium", order=2),
]


class TestCatalogFieldEntries:
    def test_includes_every_editable_attribute_in_order(self) -> None:
        entries = catalog_field_entries(ATTRIBUTES)
        assert [e["field_key"] for e in entries] == ["title", "description", "priority"]

    def test_carries_definition_required_and_default(self) -> None:
        entries = {e["field_key"]: e for e in catalog_field_entries(ATTRIBUTES)}
        assert entries["title"]["required"] is True
        assert entries["priority"]["default"] == "medium"

    def test_includes_a_hidden_attribute_with_visible_false(self) -> None:
        # A hidden attribute is still configurable — the editor must be able to
        # flip it on; the dialog simply does not render a visible=false entry.
        entries = catalog_field_entries([_attribute("secret", visible=False)])
        assert entries[0]["visible"] is False

    @pytest.mark.parametrize("editable", ["workflow", "system", False])
    def test_excludes_non_editable_fields(self, editable: object) -> None:
        assert catalog_field_entries([_attribute("status", editable=editable)]) == []

    def test_attribute_in_a_hidden_section_reads_as_invisible(self) -> None:
        # Spec section 4.4's AND-condition: a hidden section hides its fields, so
        # the entry is invisible (and therefore never server-demanded).
        entries = catalog_field_entries(
            [_attribute("secret", section="internal")],
            sections=[{"name": "internal", "visible": False}],
        )
        assert entries[0]["visible"] is False


class TestMergeCreateFormEntries:
    def test_missing_configuration_returns_the_base(self) -> None:
        base = catalog_field_entries(ATTRIBUTES)
        assert merge_create_form_entries(None, base=base) == base

    def test_stored_entry_overrides_visible_required_order_default(self) -> None:
        base = catalog_field_entries(ATTRIBUTES)
        merged = merge_create_form_entries(
            [{"field_key": "priority", "visible": False, "order": 0}], base=base
        )
        by_key = {e["field_key"]: e for e in merged}
        assert by_key["priority"]["visible"] is False
        # Order 0 puts priority first; base entries keep their own order.
        assert merged[0]["field_key"] == "priority"

    def test_unmentioned_fields_keep_the_base_entry(self) -> None:
        base = catalog_field_entries(ATTRIBUTES)
        merged = merge_create_form_entries(
            [{"field_key": "title", "required": False}], base=base
        )
        assert {e["field_key"] for e in merged} == {"title", "description", "priority"}

    def test_entry_for_a_deleted_attribute_is_dropped(self) -> None:
        base = catalog_field_entries([_attribute("title")])
        merged = merge_create_form_entries(
            [{"field_key": "gone", "visible": True}], base=base
        )
        assert [e["field_key"] for e in merged] == ["title"]

    def test_hand_edited_non_list_reads_as_no_configuration(self) -> None:
        base = catalog_field_entries(ATTRIBUTES)
        assert merge_create_form_entries("garbage", base=base) == base


class TestNormalizeCreateFormEntries:
    def test_defaults_visible_true_required_false_order_index(self) -> None:
        normalized = normalize_create_form_entries(
            [{"field_key": "title"}, {"field_key": "priority"}],
            valid_keys=["title", "priority"],
        )
        assert normalized[0] == {
            "field_key": "title",
            "visible": True,
            "required": False,
            "order": 0,
            "default": None,
        }

    def test_sorts_by_order(self) -> None:
        normalized = normalize_create_form_entries(
            [{"field_key": "a", "order": 5}, {"field_key": "b", "order": 1}],
            valid_keys=["a", "b"],
        )
        assert [e["field_key"] for e in normalized] == ["b", "a"]

    def test_hidden_field_is_never_required(self) -> None:
        normalized = normalize_create_form_entries(
            [{"field_key": "a", "visible": False, "required": True}],
            valid_keys=["a"],
        )
        assert normalized[0]["required"] is False

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(CreateFormError):
            normalize_create_form_entries(
                [{"field_key": "nope"}], valid_keys=["title"]
            )

    def test_rejects_duplicate_field(self) -> None:
        with pytest.raises(CreateFormError):
            normalize_create_form_entries(
                [{"field_key": "a"}, {"field_key": "a"}], valid_keys=["a"]
            )

    def test_rejects_unknown_key(self) -> None:
        with pytest.raises(CreateFormError):
            normalize_create_form_entries(
                [{"field_key": "a", "visable": True}], valid_keys=["a"]
            )

    def test_rejects_non_boolean_visible(self) -> None:
        with pytest.raises(CreateFormError):
            normalize_create_form_entries(
                [{"field_key": "a", "visible": "yes"}], valid_keys=["a"]
            )

    def test_rejects_non_list(self) -> None:
        with pytest.raises(CreateFormError):
            normalize_create_form_entries({"field_key": "a"}, valid_keys=["a"])

    def test_empty_valid_keys_accepts_any_key(self) -> None:
        # A workspace whose definition cannot be resolved still round-trips its
        # stored row (the read path must never fail on a missing base).
        normalized = normalize_create_form_entries(
            [{"field_key": "custom_x"}], valid_keys=[]
        )
        assert normalized[0]["field_key"] == "custom_x"


def test_required_field_keys_skips_hidden() -> None:
    assert required_field_keys(
        [
            {"field_key": "a", "visible": True, "required": True},
            {"field_key": "b", "visible": False, "required": True},
            {"field_key": "c", "visible": True, "required": False},
        ]
    ) == ["a"]
