"""Typed Given/When/Then test steps (Issue #1564).

``TestCase.steps`` used to be an untyped list of free dicts, in practice
``{"step": ..., "expected_result": ...}`` as produced by the AI derivation.
This module is the single normaliser and validator for the typed shape::

    {"id": "<stable uuid>", "step_type": "given|when|then|and|but", "text": "…"}

Every reader (REST, MCP, export, diff, baseline, indexer) normalises on read,
so legacy rows keep working without a migration having run. The data migration
uses the very same function, which is why normalisation is idempotent.

Deliberately not here: a Gherkin parser (text -> steps) and per-step results in
the test run. Both are the separate proposal V8 from the backlog roadmap.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Sequence, TypedDict

from application.base import ValidationError

#: Upper bounds from the issue's acceptance criteria. They keep a single test
#: case from turning into an unbounded payload on every transport.
MAX_STEPS = 200
MAX_STEP_TEXT_LENGTH = 2000

_STEP_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://reqogniloom.dev/test-step")

_GHERKIN_KEYWORD = {
    "given": "Given",
    "when": "When",
    "then": "Then",
    "and": "And",
    "but": "But",
}


class StepType(str, Enum):
    """The five Gherkin step kinds the step model distinguishes."""

    GIVEN = "given"
    WHEN = "when"
    THEN = "then"
    AND = "and"
    BUT = "but"


class TestStep(TypedDict):
    """One typed step as stored and transported."""

    id: str
    step_type: str
    text: str


_LEADING_FORBIDDEN = frozenset({StepType.AND.value, StepType.BUT.value})


def _step_id(testcase_id: Any, index: int, step_type: str, text: str) -> str:
    """Deterministic id: the same input yields the same id on every call.

    ``uuid5`` keeps a read-normalised payload stable, so a client can diff two
    responses without seeing phantom changes. The test case id (when known) is
    part of the namespace so two test cases with identical titles never share
    ids.
    """
    seed = f"{testcase_id or ''}:{index}:{step_type}:{text}"
    return str(uuid.uuid5(_STEP_NAMESPACE, seed))


def _coerce_step_type(value: Any, path: str) -> StepType:
    try:
        return StepType(str(value).lower())
    except ValueError as exc:
        allowed = sorted(step.value for step in StepType)
        raise ValidationError(
            f"{path} must be one of {allowed}, got {value!r}."
        ) from exc


def normalize_steps(
    raw: object, *, testcase_id: Any = None
) -> list[TestStep]:
    """Return *raw* in the typed shape, accepting every historical form.

    Accepted inputs:

    * the typed shape (``step_type`` + ``text``), passed through unchanged;
    * the legacy LLM shape ``{"step": A, "expected_result": B}``, expanded to a
      ``when`` step (A) followed by a ``then`` step (B) when B is not empty;
    * an empty/``None`` value, meaning "no steps".

    Anything else raises :class:`ValidationError` naming the offending path —
    silently dropping a shape is how the pre-#1564 data would lose steps.

    Args:
        raw: The stored or incoming ``steps`` value.
        testcase_id: Optional owning test case, part of the id namespace.

    Returns:
        A list of typed steps in input order.
    """
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValidationError("steps must be a list of step objects.")
    if isinstance(raw, dict):  # pragma: no cover - guarded by Sequence check
        raise ValidationError("steps must be a list of step objects.")

    normalized: list[TestStep] = []
    for index, item in enumerate(raw):
        path = f"steps[{index}]"
        if isinstance(item, str):
            # Pre-#1564 hand-authored data: a bare string is an action.
            text = item.strip()
            if not text:
                continue
            normalized.append(
                {
                    "id": _step_id(
                        testcase_id, len(normalized), StepType.WHEN.value, text
                    ),
                    "step_type": StepType.WHEN.value,
                    "text": text,
                }
            )
            continue
        if not isinstance(item, dict):
            raise ValidationError(f"{path} must be an object, got {type(item).__name__}.")

        if "step_type" in item:
            step_type = _coerce_step_type(item.get("step_type"), f"{path}.step_type")
            text = str(item.get("text") or "").strip()
            if not text:
                # An empty typed step cannot be rendered. Keeping it would
                # validate as "not empty" later in a confusing place.
                continue
            normalized.append(
                {
                    "id": str(item.get("id") or "")
                    or _step_id(testcase_id, len(normalized), step_type.value, text),
                    "step_type": step_type.value,
                    "text": text,
                }
            )
            continue

        if "step" in item:
            action = str(item.get("step") or "").strip()
            expected = str(item.get("expected_result") or "").strip()
            if not action and not expected:
                continue
            if action:
                normalized.append(
                    {
                        "id": _step_id(
                            testcase_id, len(normalized), StepType.WHEN.value, action
                        ),
                        "step_type": StepType.WHEN.value,
                        "text": action,
                    }
                )
            if expected:
                normalized.append(
                    {
                        "id": _step_id(
                            testcase_id, len(normalized), StepType.THEN.value, expected
                        ),
                        "step_type": StepType.THEN.value,
                        "text": expected,
                    }
                )
            continue

        raise ValidationError(
            f"{path} has no recognised step shape; expected "
            "{'step_type', 'text'} or the legacy {'step', 'expected_result'}."
        )

    return normalized


def validate_steps(steps: Sequence[TestStep]) -> None:
    """Reject an unusable step list before it is persisted.

    Raises:
        ValidationError: on a non-list, too many steps, an unknown type, an
            empty/oversized text, a duplicate id or a list that opens with
            ``and``/``but``.
    """
    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise ValidationError("steps must be a list of step objects.")
    if len(steps) > MAX_STEPS:
        raise ValidationError(f"steps must contain at most {MAX_STEPS} entries.")
    if not steps:
        return

    seen_ids: set[str] = set()
    for index, step in enumerate(steps):
        path = f"steps[{index}]"
        if not isinstance(step, dict):
            raise ValidationError(f"{path} must be an object.")
        step_type = _coerce_step_type(step.get("step_type"), f"{path}.step_type")
        text = str(step.get("text") or "").strip()
        if not text:
            raise ValidationError(f"{path}.text must not be empty.")
        if len(text) > MAX_STEP_TEXT_LENGTH:
            raise ValidationError(
                f"{path}.text must be at most {MAX_STEP_TEXT_LENGTH} characters."
            )
        step_id = str(step.get("id") or "")
        if not step_id:
            raise ValidationError(f"{path}.id must not be empty.")
        if step_id in seen_ids:
            raise ValidationError(f"{path}.id duplicates an earlier step.")
        seen_ids.add(step_id)
        if index == 0 and step_type.value in _LEADING_FORBIDDEN:
            raise ValidationError(
                f"{path}.step_type must not be 'and' or 'but' as the first step."
            )


def steps_to_gherkin(steps: Sequence[TestStep], *, title: str = "") -> str:
    """Render steps as a Gherkin scenario (English keywords, 4-space indent).

    A parser in the other direction is explicitly out of scope (proposal V8).
    """
    lines = [f"Scenario: {title}".rstrip()]
    for step in steps:
        keyword = _GHERKIN_KEYWORD.get(str(step.get("step_type")), "And")
        lines.append(f"    {keyword} {step.get('text', '')}".rstrip())
    return "\n".join(lines) + "\n"
