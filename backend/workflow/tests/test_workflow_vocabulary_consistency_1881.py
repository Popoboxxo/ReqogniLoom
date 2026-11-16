"""GH-1881 — one state vocabulary per artifact workflow.

The reported defect: ``GET /api/v1/issues/{id}/transitions/`` answered
``{"current_state": "Open", "states": ["Open", "proposed", "In Progress", ...]}``
while every other artifact workflow is lowercase snake_case. Because the engine
also *injects* the lowercase proposal states (``proposed`` / ``rejected``) into
the same graph, an Issue graph mixed two vocabularies — and a client that sent
``in_progress`` (the spelling every other entity accepts) got
``400 Transition not allowed: 'Open' → 'in_progress' is not defined``.

These tests pin the rule generically rather than only for Issue:

* every preset is EITHER fully lowercase snake_case OR a documented legacy
  Title-Case/German graph — an explicit, shrinking allow-list, so a new artifact
  type (or a re-spelled existing one) that reintroduces Title Case fails here;
* every allow-list entry is still genuinely non-snake_case, so a preset cannot
  stay in the list after it was converted;
* ``issue_default``'s states and transitions agree with ``Issue.IssueStatus``.

The regression that motivated the issue (that ``open`` / ``in_progress`` work
over HTTP, and that the old labels are rejected with a clear message) is
covered end to end in
``rest_api/tests/test_issue_workflow_vocabulary_1881.py``.
"""
from __future__ import annotations

import re

import pytest

from persistence.models import Issue
from workflow.definition_store import PRESET_SCHEMAS

#: A state a client can send verbatim: lowercase ASCII, digits, single
#: underscores — the vocabulary every non-legacy preset uses (`in_review`,
#: `in_progress`, `wontfix`, …).
SNAKE_CASE_STATE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Presets that still intentionally spell their business states in Title Case
#: or German. They are the *remaining* members of the pre-GH-1881 vocabulary
#: and each one names a persistence column whose other consumers spell the same
#: way. Converting one is its own change (it needs a data migration, exactly
#: like GH-453 for TestCase and GH-1881 for Issue); this list may only shrink.
LEGACY_TITLE_CASE_PRESETS: frozenset[str] = frozenset(
    {
        "adr_default",
        "risk_default",
        "goal_default",
        "main_goal_default",
        "document_default",
    }
)

_MODERN_PRESETS = sorted(set(PRESET_SCHEMAS) - LEGACY_TITLE_CASE_PRESETS)


def _non_snake_states(preset: str) -> list[str]:
    return [
        state
        for state in PRESET_SCHEMAS[preset]["states"]
        if not SNAKE_CASE_STATE.match(state)
    ]


@pytest.mark.parametrize("preset", _MODERN_PRESETS)
def test_modern_preset_states_are_all_lowercase_snake(preset: str) -> None:
    """Every state a non-legacy artifact type accepts is lowercase snake_case."""
    offenders = _non_snake_states(preset)
    assert offenders == [], (
        f"preset {preset!r} mixes vocabularies: {offenders} are not "
        "lowercase snake_case. Per GH-1881 (and GH-453 before it) a workflow "
        "graph carries exactly one vocabulary, because clients send the state "
        "value verbatim on POST .../transitions/."
    )


@pytest.mark.parametrize("preset", sorted(LEGACY_TITLE_CASE_PRESETS))
def test_legacy_presets_are_still_genuinely_non_snake(preset: str) -> None:
    """The allow-list above is honest: each entry must still be non-snake.

    Otherwise a converted preset would linger in the list as a silent loophole
    for the next Title-Case regression.
    """
    assert _non_snake_states(preset), (
        f"preset {preset!r} is listed as a legacy Title-Case vocabulary but "
        "every state is lowercase snake_case — remove it from "
        "LEGACY_TITLE_CASE_PRESETS."
    )


def test_legacy_presets_all_exist() -> None:
    """A typo in the allow-list must not silently exempt nothing (or anything)."""
    unknown = LEGACY_TITLE_CASE_PRESETS - set(PRESET_SCHEMAS)
    assert unknown == set(), f"unknown presets in LEGACY_TITLE_CASE_PRESETS: {unknown}"


def test_issue_default_states_match_the_issue_status_enum() -> None:
    """The engine vocabulary and the declared enum must not drift apart.

    ``inject_proposed_state`` adds ``proposed``/``rejected`` on top of the
    declared business states, so the enum is a subset — every enum value must
    be a real graph state, or a transition request naming it can never succeed.
    """
    declared = set(PRESET_SCHEMAS["issue_default"]["states"])
    assert set(Issue.IssueStatus.values) <= declared
    assert {
        "proposed",
        "rejected",
    } <= declared


def test_issue_transitions_only_reference_declared_states() -> None:
    """No transition may point at a state the graph does not declare."""
    schema = PRESET_SCHEMAS["issue_default"]
    declared = set(schema["states"])
    referenced = {
        state
        for transition in schema["transitions"]
        for state in (transition["from_state"], transition["to_state"])
    }
    assert referenced <= declared


def test_issue_initial_state_is_open() -> None:
    """``states[0]`` is the initial state the engine seeds new Issues into."""
    assert PRESET_SCHEMAS["issue_default"]["states"][0] == "open"


def test_issue_state_meta_uses_the_lowercase_state_names() -> None:
    """``get_state_meta`` looks states up by name — a stale key silently
    disables the flag (same failure mode GH-453 had for TestCase)."""
    state_meta = PRESET_SCHEMAS["issue_default"]["state_meta"]
    declared = set(PRESET_SCHEMAS["issue_default"]["states"])
    assert set(state_meta) <= declared
    assert state_meta["wontfix"] == {"is_outdated_equivalent": True}
    assert state_meta["resolved"] == {"auto_approve_target": True}
