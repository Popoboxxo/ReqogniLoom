"""Typed test steps: normalisation, validation and Gherkin export (#1564)."""

from __future__ import annotations

import pytest

from application.base import ValidationError
from application.test_steps import (
    MAX_STEPS,
    MAX_STEP_TEXT_LENGTH,
    StepType,
    normalize_steps,
    steps_to_gherkin,
    validate_steps,
)

TESTCASE_ID = "11111111-1111-1111-1111-111111111111"


def test_legacy_pair_becomes_when_then() -> None:
    out = normalize_steps(
        [{"step": "Open page", "expected_result": "Page visible"}],
        testcase_id=TESTCASE_ID,
    )

    assert [step["step_type"] for step in out] == ["when", "then"]
    assert [step["text"] for step in out] == ["Open page", "Page visible"]


def test_legacy_without_expected_result_yields_only_when() -> None:
    out = normalize_steps([{"step": "Open page", "expected_result": ""}])

    assert [step["step_type"] for step in out] == ["when"]


def test_a_legacy_row_with_both_parts_empty_produces_nothing() -> None:
    assert normalize_steps([{"step": "", "expected_result": ""}]) == []


def test_typed_steps_pass_through_unchanged() -> None:
    typed = [
        {"id": "a", "step_type": "given", "text": "a user"},
        {"id": "b", "step_type": "when", "text": "they log in"},
    ]

    assert normalize_steps(typed) == typed


def test_ids_are_stable_across_calls() -> None:
    raw = [{"step": "Open page", "expected_result": "Page visible"}]

    first = normalize_steps(raw, testcase_id=TESTCASE_ID)
    second = normalize_steps(raw, testcase_id=TESTCASE_ID)

    assert first == second
    assert len({step["id"] for step in first}) == 2


def test_ids_differ_between_test_cases() -> None:
    raw = [{"step": "Open page", "expected_result": ""}]

    one = normalize_steps(raw, testcase_id="testcase-one")
    two = normalize_steps(raw, testcase_id="testcase-two")

    assert one[0]["id"] != two[0]["id"]


def test_normalize_is_idempotent() -> None:
    raw = [
        {"step": "Open page", "expected_result": "Page visible"},
        {"id": "typed", "step_type": "then", "text": "done"},
    ]

    once = normalize_steps(raw, testcase_id=TESTCASE_ID)

    assert normalize_steps(once, testcase_id=TESTCASE_ID) == once


def test_a_bare_string_becomes_a_when_step() -> None:
    """The oldest hand-authored shape (``string[]``) stays readable."""
    out = normalize_steps(["open", "click"], testcase_id=TESTCASE_ID)

    assert [step["step_type"] for step in out] == ["when", "when"]
    assert [step["text"] for step in out] == ["open", "click"]


def test_unknown_shape_raises_with_path() -> None:
    with pytest.raises(ValidationError, match=r"steps\[1\]"):
        normalize_steps([{"step": "ok", "expected_result": ""}, {"x": 1}])


def test_an_unknown_step_type_raises_with_path() -> None:
    with pytest.raises(ValidationError, match=r"steps\[0\]\.step_type"):
        normalize_steps([{"step_type": "scenario", "text": "nope"}])


def test_a_non_list_raises() -> None:
    with pytest.raises(ValidationError, match="steps must be a list"):
        normalize_steps({"step": "A"})


def test_none_means_no_steps() -> None:
    assert normalize_steps(None) == []


def _step(step_type: str, text: str = "x", step_id: str = "id") -> dict:
    return {"id": step_id, "step_type": step_type, "text": text}


def test_validate_accepts_a_typed_sequence() -> None:
    validate_steps([_step("given", "a user"), _step("when", "login", "id2")])


def test_validate_rejects_leading_and() -> None:
    with pytest.raises(ValidationError, match=r"steps\[0\]\.step_type"):
        validate_steps([_step("and"), _step("then", "done", "id2")])


def test_validate_rejects_empty_text() -> None:
    with pytest.raises(ValidationError, match=r"steps\[0\]\.text"):
        validate_steps([_step("given", "   ")])


def test_validate_rejects_oversized_text() -> None:
    with pytest.raises(ValidationError, match="at most"):
        validate_steps([_step("given", "x" * (MAX_STEP_TEXT_LENGTH + 1))])


def test_validate_rejects_too_many_steps() -> None:
    steps = [_step("given", f"s{i}", f"id{i}") for i in range(MAX_STEPS + 1)]

    with pytest.raises(ValidationError, match="at most"):
        validate_steps(steps)


def test_validate_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        validate_steps([_step("given", "a", "same"), _step("then", "b", "same")])


def test_validate_rejects_a_missing_id() -> None:
    with pytest.raises(ValidationError, match=r"steps\[0\]\.id"):
        validate_steps([{"id": "", "step_type": "given", "text": "a"}])


def test_gherkin_export_keeps_order_and_keywords() -> None:
    steps = [
        _step("given", "a user", "1"),
        _step("when", "they log in", "2"),
        _step("then", "the dashboard opens", "3"),
        _step("and", "a toast appears", "4"),
    ]

    rendered = steps_to_gherkin(steps, title="Login")

    assert rendered.splitlines() == [
        "Scenario: Login",
        "    Given a user",
        "    When they log in",
        "    Then the dashboard opens",
        "    And a toast appears",
    ]


def test_step_type_enum_values_are_the_transport_strings() -> None:
    assert StepType.GIVEN == "given"
    assert {step.value for step in StepType} == {"given", "when", "then", "and", "but"}
