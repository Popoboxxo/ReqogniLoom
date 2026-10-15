"""Unit tests for the tree-display field vocabulary (Issue #1257).

``attribute_definitions/tree_fields.py`` is deliberately Django-free, so this
module is a pure unit test with no database and no fixtures: it pins the
*catalogue* contract (keys, widths, defaults) and, most importantly, that
:func:`normalize_tree_fields` refuses anything that would later render as an
empty or duplicated tree row.
"""
from __future__ import annotations

import pytest

from attribute_definitions.tree_fields import (
    DEFAULT_TREE_DISPLAY_FIELDS,
    DEFAULT_TREE_FIELD_WIDTH,
    SYSTEM_TREE_FIELDS,
    TREE_FIELD_WIDTHS,
    TreeFieldError,
    field_catalog,
    is_system_tree_field,
    is_valid_tree_field_key,
    merge_tree_fields,
    normalize_tree_fields,
    system_field_keys,
)


class TestCatalogue:
    def test_default_combination_is_the_pre_1257_rendering(self) -> None:
        """The default must name the fields the tree rendered before #1257."""
        assert DEFAULT_TREE_DISPLAY_FIELDS == (
            "uid",
            "level",
            "status",
            "updated_at",
            "version",
        )
        for key in DEFAULT_TREE_DISPLAY_FIELDS:
            assert is_system_tree_field(key), key

    def test_system_field_keys_are_unique_and_in_catalogue_order(self) -> None:
        keys = system_field_keys()
        assert len(keys) == len(set(keys))
        assert keys == tuple(spec.key for spec in SYSTEM_TREE_FIELDS)

    def test_every_system_field_ships_a_label_key_and_a_valid_width(self) -> None:
        for spec in SYSTEM_TREE_FIELDS:
            assert spec.label_key.startswith("treeDisplay.field."), spec.key
            assert spec.label, spec.key
            assert spec.width in TREE_FIELD_WIDTHS, spec.key
            assert spec.system is True

    def test_catalog_entry_shape_matches_the_rest_contract(self) -> None:
        entry = field_catalog()[0]
        assert set(entry) == {"key", "label_key", "label", "width", "system"}

    def test_field_catalog_appends_custom_keys_as_non_system(self) -> None:
        entries = field_catalog(["my_custom_field"])
        keys = [entry["key"] for entry in entries]
        assert keys[-1] == "my_custom_field"
        assert entries[-1]["system"] is False
        assert entries[-1]["width"] == DEFAULT_TREE_FIELD_WIDTH

    def test_field_catalog_deduplicates_against_system_keys(self) -> None:
        """A custom key that shadows a built-in must not be listed twice."""
        keys = [entry["key"] for entry in field_catalog(["status", "status"])]
        assert keys.count("status") == 1


class TestKeyValidation:
    @pytest.mark.parametrize("key", ["uid", "updated_at", "my_custom_field"])
    def test_snake_case_keys_are_accepted(self, key: str) -> None:
        assert is_valid_tree_field_key(key)

    @pytest.mark.parametrize(
        "key", ["", "Status", "my-field", "my field", "1st", None, 7]
    )
    def test_prose_and_non_identifiers_are_rejected(self, key: object) -> None:
        assert not is_valid_tree_field_key(key)

    def test_explicit_extra_keys_are_accepted_even_when_unknown(self) -> None:
        """A workspace custom attribute resolves through ``extra_keys``."""
        assert is_valid_tree_field_key("Kunde-Name", extra_keys=["Kunde-Name"])
        assert not is_valid_tree_field_key("Kunde-Name")


class TestNormalize:
    def test_accepts_bare_keys_and_objects_into_canonical_entries(self) -> None:
        assert normalize_tree_fields(["uid", {"key": "status", "width": "half"}]) == [
            {"key": "uid", "width": DEFAULT_TREE_FIELD_WIDTH},
            {"key": "status", "width": "half"},
        ]

    def test_preserves_the_caller_order(self) -> None:
        """Issue #1257: the stored list order is the rendered order."""
        keys = [entry["key"] for entry in normalize_tree_fields(["status", "uid"])]
        assert keys == ["status", "uid"]

    def test_empty_list_is_valid_and_means_no_fields(self) -> None:
        assert normalize_tree_fields([]) == []

    @pytest.mark.parametrize(
        "raw",
        [
            "uid",
            {"key": "uid"},
            [7],
            [{"width": "half"}],
            [{"key": "not a key", "width": "full"}],
            [{"key": "uid", "width": "wide"}],
            ["uid", "uid"],
        ],
    )
    def test_malformed_payloads_raise_with_every_error(self, raw: object) -> None:
        with pytest.raises(TreeFieldError) as excinfo:
            normalize_tree_fields(raw)
        assert excinfo.value.errors

    def test_custom_attribute_keys_can_be_configured(self) -> None:
        """Point 2 of #1257: custom attributes must work without a code change."""
        assert normalize_tree_fields(
            ["Kunde-Name"], extra_keys=["Kunde-Name"]
        ) == [{"key": "Kunde-Name", "width": DEFAULT_TREE_FIELD_WIDTH}]


class TestMerge:
    def test_non_list_customization_falls_back_to_base(self) -> None:
        base = [{"key": "uid", "width": "half"}]
        assert merge_tree_fields(None, base=base) == base
        assert merge_tree_fields({"key": "uid"}, base=base) == base

    def test_base_width_is_used_when_the_stored_entry_omits_one(self) -> None:
        merged = merge_tree_fields(["uid"], base=[{"key": "uid", "width": "half"}])
        assert merged == [{"key": "uid", "width": "half"}]

    def test_unknown_width_falls_back_instead_of_raising(self) -> None:
        """A hand-edited row must never break a *read* path."""
        merged = merge_tree_fields([{"key": "uid", "width": "gigantic"}])
        assert merged == [{"key": "uid", "width": DEFAULT_TREE_FIELD_WIDTH}]

    def test_entries_without_a_usable_key_are_dropped(self) -> None:
        assert merge_tree_fields([{"width": "half"}, 7, ""]) == []


class TestPublicSurface:
    def test_module_exports_the_documented_names(self) -> None:
        import attribute_definitions.tree_fields as module

        for name in module.__all__:
            assert hasattr(module, name), name
