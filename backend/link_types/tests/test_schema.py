"""definition_json shape/range validation for tenant-authored link types."""
from __future__ import annotations

import pytest

from link_types.builtin import builtin_definition
from link_types.schema import validate_definition_json
from persistence.errors import ValidationError


def _minimal() -> dict:
    return {
        "label": {
            "de": {"downstream": "a", "upstream": "b", "neutral": "c"},
            "en": {"downstream": "a", "upstream": "b", "neutral": "c"},
        },
        "allowed_pairs": [{"source_type": "Requirement", "target_type": "Risk"}],
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": False,
    }


def test_every_builtin_definition_validates():
    for key in (
        "derives-from",
        "decomposes",
        "allocated-to",
        "verifies",
        "decides",
        "mitigates",
        "references",
        "diagram-ref",
    ):
        assert validate_definition_json(builtin_definition(key), key=key)


def test_unknown_suspect_rule_is_rejected_and_lists_the_valid_values():
    payload = _minimal()
    payload["suspect_rule"] = "flag_everything"
    with pytest.raises(ValidationError) as exc:
        validate_definition_json(payload, key="conflicts-with")
    message = str(exc.value)
    assert "suspect_rule" in message
    assert "parent_change_flags_children" in message


def test_negative_impact_weight_is_rejected():
    payload = _minimal()
    payload["impact_weight"] = -0.1
    with pytest.raises(ValidationError, match="impact_weight"):
        validate_definition_json(payload, key="conflicts-with")


def test_allowed_pairs_must_be_objects_with_both_sides():
    payload = _minimal()
    payload["allowed_pairs"] = [{"source_type": "Requirement"}]
    with pytest.raises(ValidationError, match="target_type"):
        validate_definition_json(payload, key="conflicts-with")


def test_allowed_pairs_may_be_empty_meaning_the_type_links_nothing_yet():
    payload = _minimal()
    payload["allowed_pairs"] = []
    assert validate_definition_json(payload, key="conflicts-with")["allowed_pairs"] == []


def test_missing_label_language_is_rejected():
    payload = _minimal()
    del payload["label"]["en"]
    with pytest.raises(ValidationError, match="label"):
        validate_definition_json(payload, key="conflicts-with")


def test_missing_label_perspective_is_rejected():
    payload = _minimal()
    del payload["label"]["de"]["neutral"]
    with pytest.raises(ValidationError, match="neutral"):
        validate_definition_json(payload, key="conflicts-with")


def test_optional_flags_default_when_absent():
    payload = _minimal()
    for optional in ("coverage_relevant", "manual_creatable", "system_owned", "active", "built_in"):
        del payload[optional]
    result = validate_definition_json(payload, key="conflicts-with")
    assert result["coverage_relevant"] is False
    assert result["manual_creatable"] is True
    assert result["system_owned"] is False
    assert result["active"] is True
    assert result["built_in"] is False


def test_unknown_top_level_field_is_rejected():
    payload = _minimal()
    payload["propagation_script"] = "flag(x)"
    with pytest.raises(ValidationError, match="propagation_script"):
        validate_definition_json(payload, key="conflicts-with")
