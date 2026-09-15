"""Which preset ``mandatory_fields`` names are actually enforced (GH-912).

``bootstrap_attribute_definitions`` used to resolve the preset's
``mandatory_fields`` list against attribute names alone and report every
mismatch as "ignored". For the built-in presets that produced 22 permanent
false warnings per migrate run: the names are *policy* names, and three of them
have consumers that are not attributes at all — ``classification`` aliases the
``type`` column, ``change_reason`` is satisfied by the transition request and
``traceability_target`` is the Extended-tier lever for rule 7.

``policy_fields_without_consumer`` is where that knowledge is applied, in the
module that owns it (``workflow.precondition_rules``). These tests pin both
directions: consumed names are never reported (so a clean migrate stays silent),
and a name nothing consumes still is (so the hygiene check has not been
hollowed out).
"""
from __future__ import annotations

import pytest

from workflow.precondition_rules import policy_fields_without_consumer


class TestConsumedPolicyFields:
    """Each consumer kind must be recognised."""

    def test_attribute_name_is_consumed(self) -> None:
        assert (
            policy_fields_without_consumer(
                ["title"],
                item_type="Requirement",
                attribute_names={"title"},
                model_field_names={"title"},
            )
            == []
        )

    def test_column_alias_is_consumed(self) -> None:
        """``classification`` is the policy name for ``Requirement.type``."""
        assert (
            policy_fields_without_consumer(
                ["classification"],
                item_type="Requirement",
                attribute_names=set(),
                model_field_names={"type"},
            )
            == []
        )

    @pytest.mark.parametrize("policy_field", ["change_reason", "traceability_target"])
    def test_request_and_graph_level_fields_are_consumed(self, policy_field: str) -> None:
        """Rule 5 reads the transition's change_reason; rule 7 the trace graph.

        Neither is an attribute or a column, and both are enforced — the
        pre-#912 check called them "ignored".
        """
        assert (
            policy_fields_without_consumer(
                [policy_field],
                item_type="Requirement",
                attribute_names=set(),
                model_field_names=set(),
            )
            == []
        )

    def test_real_requirement_policy_is_fully_consumed(self) -> None:
        """The built-in presets must produce no hygiene warning at all."""
        from presets.registry import PresetRegistry

        from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
            introspect_core_attributes,
        )
        from persistence.models import Requirement

        columns = {
            field.name
            for field in Requirement._meta.get_fields()
            if hasattr(field, "attname")
        }
        for preset in ("minimal", "standard", "extended"):
            policy = PresetRegistry().get_preset_config(preset).mandatory_fields
            attributes = {
                attribute["name"]
                for attribute in introspect_core_attributes("Requirement", preset)
            }
            assert (
                policy_fields_without_consumer(
                    policy,
                    item_type="Requirement",
                    attribute_names=attributes,
                    model_field_names=columns,
                )
                == []
            ), preset


class TestUnconsumedPolicyFields:
    """The check must still catch genuinely dead configuration."""

    def test_unknown_name_is_reported(self) -> None:
        assert policy_fields_without_consumer(
            ["title", "renamed_away_field"],
            item_type="Requirement",
            attribute_names={"title"},
            model_field_names={"title"},
        ) == ["renamed_away_field"]

    def test_result_is_sorted_and_deduplicated(self) -> None:
        assert policy_fields_without_consumer(
            ["zzz", "aaa", "zzz"],
            item_type="Requirement",
            attribute_names=set(),
            model_field_names=set(),
        ) == ["aaa", "zzz"]

    def test_policy_is_not_applied_to_entity_types_rule_5_skips(self) -> None:
        """A type outside rule 5's registry consumes none of the names."""
        assert policy_fields_without_consumer(
            ["title"],
            item_type="Nonexistent",
            attribute_names={"title"},
            model_field_names={"title"},
        ) == ["title"]
