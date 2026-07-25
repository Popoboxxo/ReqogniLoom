"""Tests for the shared ``workflow.services.is_approval_gate`` helper (Phase 5).

Moved out of ``AiDerivationService._is_approval_gate`` (Phase 3) so both the
derivation service and the new ``review.*`` MCP tool group depend on the
workflow layer, not on each other.
"""
from __future__ import annotations

from workflow.definition_store import TransitionDefinitionDTO
from workflow.services import is_approval_gate


def test_editor_allowed_transition_is_not_a_gate():
    t = TransitionDefinitionDTO(
        from_state="draft", to_state="in_review", allowed_roles=("editor", "admin")
    )
    assert is_approval_gate(t) is False


def test_approver_only_transition_is_a_gate():
    t = TransitionDefinitionDTO(
        from_state="in_review", to_state="approved", allowed_roles=("approver", "admin")
    )
    assert is_approval_gate(t) is True
