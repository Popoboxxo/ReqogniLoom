"""Gappy ordering model for attribute definitions (feature #1260).

Pure unit tests (no DB, no Django settings module): ``ordering.py`` is
deliberately Django-free, and the properties pinned here are the ones the
service/REST/MCP layers rely on:

* a move into an existing gap rewrites exactly ONE entry,
* a section without room is re-spaced instead of silently collapsing two
  entries onto the same key,
* a cross-section move carries ``section`` and ``order`` together,
* an explicit ``attribute_flow`` follows its attribute.
"""
from __future__ import annotations

import pytest

from attribute_definitions.ordering import (
    ORDER_STEP,
    ReorderError,
    UnknownAnchorError,
    UnknownAttributeError,
    reorder,
    reorder_definition,
)

SPAN = {"kind": "attribute", "name": "alpha", "span": "half"}


def attr(name: str, *, section: str = "general", order: int = 0, **extra):
    return {
        "name": name,
        "kind": "extended",
        "type": "text",
        "section": section,
        "order": order,
        **extra,
    }


def orders(attributes) -> dict[str, int]:
    return {a["name"]: a["order"] for a in attributes}


def names(attributes) -> list[str]:
    return [a["name"] for a in attributes]


class TestSparseInsertion:
    def test_move_into_a_gap_rewrites_only_the_moved_entry(self) -> None:
        attributes = [attr("alpha", order=0), attr("beta", order=ORDER_STEP),
                      attr("gamma", order=2 * ORDER_STEP)]

        result = reorder(attributes, name="alpha", section="general", after="beta")

        assert orders(result) == {
            "alpha": ORDER_STEP + ORDER_STEP // 2,
            "beta": ORDER_STEP,
            "gamma": 2 * ORDER_STEP,
        }
        # "Only the affected neighbours": the untouched entries are the very
        # same objects, not merely equal copies.
        by_name = {a["name"]: a for a in result}
        assert by_name["beta"] is attributes[1]
        assert by_name["gamma"] is attributes[2]

    def test_move_to_front_uses_the_free_slot_below_the_first_entry(self) -> None:
        attributes = [attr("alpha", order=ORDER_STEP), attr("beta", order=2 * ORDER_STEP)]

        result = reorder(attributes, name="beta", section="general", after=None)

        assert orders(result)["beta"] == 0
        assert orders(result)["alpha"] == ORDER_STEP

    def test_append_uses_one_step_beyond_the_last_entry(self) -> None:
        attributes = [
            attr("alpha", order=ORDER_STEP),
            attr("beta", order=2 * ORDER_STEP),
            attr("gamma", section="other", order=ORDER_STEP),
        ]

        result = reorder(attributes, name="gamma", section="general", after="beta")

        assert orders(result)["gamma"] == 3 * ORDER_STEP
        assert result[2]["section"] == "general"

    def test_empty_section_gets_the_first_gap(self) -> None:
        attributes = [attr("alpha", order=7)]

        result = reorder(attributes, name="alpha", section="general", after=None)

        assert orders(result)["alpha"] == ORDER_STEP


class TestRespace:
    def test_adjacent_neighbours_trigger_a_respace_of_that_section(self) -> None:
        attributes = [attr("alpha", order=0), attr("beta", order=1), attr("gamma", order=2)]

        result = reorder(attributes, name="gamma", section="general", after="alpha")

        assert orders(result) == {
            "alpha": ORDER_STEP,
            "gamma": 2 * ORDER_STEP,
            "beta": 3 * ORDER_STEP,
        }

    def test_respace_does_not_touch_other_sections(self) -> None:
        attributes = [
            attr("alpha", order=0),
            attr("beta", order=1),
            attr("other", section="other", order=1),
        ]

        result = reorder(attributes, name="beta", section="general", after=None)

        assert orders(result)["other"] == 1
        assert orders(result)["beta"] == ORDER_STEP

    def test_head_insert_without_room_re_spaces(self) -> None:
        attributes = [attr("alpha", order=0), attr("beta", order=ORDER_STEP)]

        result = reorder(attributes, name="beta", section="general", after=None)

        assert orders(result) == {"beta": ORDER_STEP, "alpha": 2 * ORDER_STEP}


class TestAtomicSectionMove:
    def test_cross_section_move_sets_section_and_order_together(self) -> None:
        attributes = [
            attr("alpha", section="general", order=ORDER_STEP),
            attr("beta", section="other", order=ORDER_STEP),
        ]

        result = reorder(attributes, name="beta", section="general", after="alpha")

        moved = next(a for a in result if a["name"] == "beta")
        assert moved["section"] == "general"
        assert moved["order"] == 2 * ORDER_STEP

    def test_input_list_and_entries_are_not_mutated(self) -> None:
        attributes = [attr("alpha", order=0), attr("beta", order=ORDER_STEP)]

        reorder(attributes, name="alpha", section="general", after="beta")

        assert orders(attributes) == {"alpha": 0, "beta": ORDER_STEP}


class TestRejections:
    def test_unknown_attribute_raises(self) -> None:
        with pytest.raises(UnknownAttributeError):
            reorder([attr("alpha")], name="nope", section="general")

    def test_unknown_anchor_raises(self) -> None:
        with pytest.raises(UnknownAnchorError):
            reorder([attr("alpha")], name="alpha", section="general", after="nope")

    def test_anchor_of_another_section_raises(self) -> None:
        attributes = [attr("alpha"), attr("beta", section="other")]

        with pytest.raises(UnknownAnchorError):
            reorder(attributes, name="alpha", section="general", after="beta")

    @pytest.mark.parametrize("section", ["", "   ", None, 7])
    def test_empty_or_non_string_section_raises(self, section) -> None:
        with pytest.raises(ReorderError):
            reorder([attr("alpha")], name="alpha", section=section)  # type: ignore[arg-type]


class TestFlowFollowsTheAttribute:
    def test_flow_token_moves_and_keeps_its_span(self) -> None:
        attributes = [attr("alpha", order=ORDER_STEP), attr("beta", order=2 * ORDER_STEP)]
        sections = [
            {"name": "general", "order": 0, "visible": True, "layout": "full",
             "attribute_flow": [SPAN, {"kind": "attribute", "name": "beta", "span": "full"}]},
        ]

        _, new_sections = reorder_definition(
            attributes, sections, name="alpha", section="general", after="beta"
        )

        assert new_sections[0]["attribute_flow"] == [
            {"kind": "attribute", "name": "beta", "span": "full"},
            {"kind": "attribute", "name": "alpha", "span": "half"},
        ]

    def test_section_without_a_flow_is_returned_value_equal(self) -> None:
        attributes = [attr("alpha", order=0), attr("beta", order=ORDER_STEP)]
        sections = [{"name": "general", "order": 0, "visible": True, "layout": "full"}]

        _, new_sections = reorder_definition(
            attributes, sections, name="alpha", section="general", after="beta"
        )

        assert new_sections == sections

    def test_token_missing_from_the_target_flow_is_appended(self) -> None:
        attributes = [
            attr("alpha", order=ORDER_STEP),
            attr("beta", section="other", order=ORDER_STEP),
        ]
        sections = [
            {"name": "general", "order": 0, "visible": True, "layout": "full",
             "attribute_flow": [{"kind": "attribute", "name": "alpha", "span": "full"}]},
            {"name": "other", "order": 1, "visible": True, "layout": "full"},
        ]

        _, new_sections = reorder_definition(
            attributes, sections, name="beta", section="general", after="alpha"
        )

        assert new_sections[0]["attribute_flow"] == [
            {"kind": "attribute", "name": "alpha", "span": "full"},
            {"kind": "attribute", "name": "beta", "span": "full"},
        ]

    def test_moved_attribute_is_dropped_from_the_source_sections_flow(self) -> None:
        attributes = [
            attr("alpha", section="general", order=ORDER_STEP),
            attr("beta", section="other", order=ORDER_STEP),
        ]
        sections = [
            {"name": "general", "order": 0, "visible": True, "layout": "full"},
            {"name": "other", "order": 1, "visible": True, "layout": "full",
             "attribute_flow": [{"kind": "attribute", "name": "beta", "span": "full"}]},
        ]

        _, new_sections = reorder_definition(
            attributes, sections, name="beta", section="general", after="alpha"
        )

        assert new_sections[1]["attribute_flow"] == []


def test_result_is_a_new_list_of_the_same_entries() -> None:
    attributes = [attr("alpha", order=0)]

    result = reorder(attributes, name="alpha", section="general")

    assert result is not attributes
    assert names(result) == names(attributes)
