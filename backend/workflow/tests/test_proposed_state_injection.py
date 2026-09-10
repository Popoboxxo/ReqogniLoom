"""The "proposed" state injection helper (spec §4.1)."""
from __future__ import annotations

import copy

import pytest

from workflow.definition_store import (
    PRESET_SCHEMAS,
    PROPOSED_STATE,
    SCHEMAS_WITHOUT_PROPOSED,
    WorkflowDefinitionDTO,
    inject_proposed_state,
)


def _schema(states, transitions=None, state_meta=None):
    out = {"states": list(states), "transitions": list(transitions or [])}
    if state_meta is not None:
        out["state_meta"] = state_meta
    return out


def test_proposed_is_never_the_initial_state():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    assert result["states"][0] == "draft"
    assert result["states"][1] == PROPOSED_STATE


def test_confirm_transition_targets_the_initial_state():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    confirm = next(
        t
        for t in result["transitions"]
        if t["from_state"] == PROPOSED_STATE and t["to_state"] == "draft"
    )
    assert confirm["requires_change_reason"] is False
    assert confirm["signature_gate"] is False
    assert confirm["allowed_roles"] == ["editor", "approver", "admin"]


def test_discard_transition_requires_a_change_reason():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    discard = next(
        t
        for t in result["transitions"]
        if t["from_state"] == PROPOSED_STATE and t["to_state"] == "rejected"
    )
    assert discard["requires_change_reason"] is True


def test_new_reject_state_is_flagged_outdated_equivalent():
    result = inject_proposed_state(_schema(["draft", "approved"]))
    assert "rejected" in result["states"]
    assert result["state_meta"]["rejected"]["is_outdated_equivalent"] is True


def test_existing_reject_state_is_reused_not_duplicated():
    result = inject_proposed_state(
        _schema(["Draft", "Approved", "Rejected"]), reject_state="Rejected"
    )
    assert result["states"].count("Rejected") == 1
    assert "rejected" not in result["states"]
    discard = next(
        t for t in result["transitions"] if t["to_state"] == "Rejected"
    )
    assert discard["from_state"] == PROPOSED_STATE


def test_injection_is_idempotent():
    once = inject_proposed_state(_schema(["draft", "approved"]))
    twice = inject_proposed_state(copy.deepcopy(once))
    assert twice == once


def test_input_schema_is_not_mutated():
    original = _schema(["draft", "approved"])
    snapshot = copy.deepcopy(original)
    inject_proposed_state(original)
    assert original == snapshot


def test_minimal_preset_has_no_proposed_state():
    assert "minimal" in SCHEMAS_WITHOUT_PROPOSED
    assert PROPOSED_STATE not in PRESET_SCHEMAS["minimal"]["states"]


@pytest.mark.parametrize(
    "preset", ["standard", "extended", "need_default", "adr_default", "goal_default"]
)
def test_shipped_schemas_carry_proposed(preset):
    schema = PRESET_SCHEMAS[preset]
    assert schema["states"][1] == PROPOSED_STATE
    dto = WorkflowDefinitionDTO(
        states=tuple(schema["states"]),
        transitions=(),
        workspace_id=None,  # type: ignore[arg-type]
        item_type="X",
        preset=preset,
    )
    # Decision 1: initial_state must be unchanged by the injection.
    assert dto.initial_state == schema["states"][0]


def test_adr_reuses_its_title_case_rejected_state():
    states = PRESET_SCHEMAS["adr_default"]["states"]
    assert "Rejected" in states
    assert "rejected" not in states


def test_goal_reuses_archiviert_as_reject_target():
    transitions = PRESET_SCHEMAS["goal_default"]["transitions"]
    discard = next(
        t for t in transitions if t["from_state"] == PROPOSED_STATE
        and t["to_state"] == "Archiviert"
    )
    assert discard["requires_change_reason"] is True
