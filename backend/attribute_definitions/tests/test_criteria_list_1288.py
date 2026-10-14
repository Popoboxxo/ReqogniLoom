"""#1288 — the ``criteria-list`` attribute type and its validator."""
from __future__ import annotations

import pytest

from attribute_definitions.field_validation import (
    FieldValidationError,
    normalize_criteria_list,
    validate_values,
)
from attribute_definitions.schema import (
    ATTRIBUTE_TYPES,
    AttributeSchemaError,
    normalize_attribute,
)


def _attrs(*raw: dict) -> list[dict]:
    return [normalize_attribute(r) for r in raw]


DEF = _attrs(
    {"name": "title", "kind": "core", "type": "text", "required": True},
    {"name": "acceptance_criteria", "kind": "core", "type": "criteria-list"},
)


def test_criteria_list_is_a_registered_attribute_type() -> None:
    assert "criteria-list" in ATTRIBUTE_TYPES
    # A definition that uses it normalizes like any other type.
    normalize_attribute({"name": "criteria", "kind": "extended", "type": "criteria-list"})


class TestNormalizeCriteriaList:
    def test_accepts_and_normalizes_a_valid_list(self) -> None:
        assert normalize_criteria_list(
            [
                {"text": "  measurable  ", "fulfilled": False},
                {"text": "b", "fulfilled": True, "evidence_ref": "abc"},
            ]
        ) == [
            {"text": "measurable", "fulfilled": False, "evidence_ref": None},
            {"text": "b", "fulfilled": True, "evidence_ref": "abc"},
        ]

    def test_rejects_a_non_list(self) -> None:
        with pytest.raises(FieldValidationError):
            normalize_criteria_list("not a list")

    def test_rejects_a_missing_text(self) -> None:
        with pytest.raises(FieldValidationError) as exc:
            normalize_criteria_list([{"fulfilled": True}])
        assert "criteria-list" in exc.value.errors

    def test_rejects_a_non_boolean_fulfilled(self) -> None:
        with pytest.raises(FieldValidationError):
            normalize_criteria_list([{"text": "x", "fulfilled": "yes"}])

    def test_rejects_an_unknown_key(self) -> None:
        with pytest.raises(FieldValidationError):
            normalize_criteria_list([{"text": "x", "fulfilled": True, "extra": 1}])


class TestValidateValuesIntegration:
    def test_a_valid_criteria_list_passes(self) -> None:
        validate_values(
            DEF,
            {
                "title": "T",
                "acceptance_criteria": [{"text": "x", "fulfilled": False}],
            },
            None,
        )

    def test_a_malformed_criteria_list_is_rejected(self) -> None:
        with pytest.raises(FieldValidationError) as exc:
            validate_values(
                DEF,
                {"title": "T", "acceptance_criteria": [{"text": ""}]},
                None,
            )
        assert "acceptance_criteria" in exc.value.errors
