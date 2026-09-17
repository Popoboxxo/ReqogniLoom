"""GH-453 — ``_map_status`` rescues legacy Title-Case status values on import.

CSV / ReqIF files exported before TestCase states were lowercased carry
"Draft"/"Ready"/"Approved"/"Deprecated". Against a post-GH-453 workspace those
values no longer match the definition's ``states`` exactly, and the previous
fallback (``valid_states[0]``) would have re-imported every approved test case
as a draft — silent data loss on the exact files the rename invalidated.

``_map_status`` therefore retries case-insensitively before falling back. The
retry may never change an outcome that already had an exact match.
"""
from __future__ import annotations

import pytest

from application.reqif_import_service import _map_status

TESTCASE_STATES = ["draft", "ready", "approved", "deprecated"]


@pytest.mark.parametrize(
    "legacy_value,expected",
    [
        ("Draft", "draft"),
        ("Ready", "ready"),
        ("Approved", "approved"),
        ("Deprecated", "deprecated"),
    ],
)
def test_legacy_titlecase_testcase_status_maps_onto_its_lowercase_state(
    legacy_value: str, expected: str
) -> None:
    assert _map_status(legacy_value, TESTCASE_STATES) == expected


def test_surrounding_whitespace_does_not_defeat_the_rescue() -> None:
    assert _map_status("  Approved  ", TESTCASE_STATES) == "approved"


def test_exact_match_still_wins_verbatim() -> None:
    """The rescue only runs after an exact miss, so an exactly-matching value
    must be returned untouched — including for entities that legitimately keep
    Title Case (Adr)."""
    adr_states = ["Draft", "In Review", "Approved", "Rejected", "Superseded"]
    assert _map_status("Approved", adr_states) == "Approved"
    assert _map_status("draft", TESTCASE_STATES) == "draft"


def test_genuinely_unknown_status_still_falls_back_to_the_initial_state() -> None:
    assert _map_status("frobnicated-status", TESTCASE_STATES) == "draft"


def test_no_definition_path_is_unchanged() -> None:
    """``valid_states=None`` keeps the global known-states behaviour; the
    case-insensitive retry deliberately does not apply there."""
    assert _map_status("approved", None) == "approved"
    assert _map_status("Approved", None) == "draft"


def test_empty_state_list_still_falls_back_to_draft() -> None:
    assert _map_status("Approved", []) == "draft"
