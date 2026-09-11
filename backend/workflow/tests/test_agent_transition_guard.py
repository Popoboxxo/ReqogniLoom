"""Spec §4.3 — an agent never confirms its own proposal."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from workflow.definition_store import (
    TransitionDefinitionDTO,
    WorkflowDefinitionDTO,
)
from workflow.transition_validator import (
    EC_AGENT_SELF_CONFIRM,
    TransitionValidator,
    ValidationRequest,
)

WS = UUID("11111111-1111-1111-1111-111111111111")


def _definition() -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        states=("draft", "proposed", "approved", "rejected"),
        transitions=(
            TransitionDefinitionDTO(
                from_state="proposed",
                to_state="draft",
                # Deliberately mis-configured to include an agent-ish role:
                # the guard must hold regardless of allowed_roles (spec §4.3).
                allowed_roles=("editor", "approver", "admin"),
            ),
            TransitionDefinitionDTO(
                from_state="draft",
                to_state="approved",
                allowed_roles=("approver", "admin"),
            ),
        ),
        workspace_id=WS,
        item_type="Requirement",
        preset="standard",
    )


def _request(actor_type: str, current: str, target: str) -> ValidationRequest:
    return ValidationRequest(
        item_id=uuid4(),
        workspace_id=WS,
        item_type="Requirement",
        current_state=current,
        target_state=target,
        user_id=uuid4(),
        user_roles=("admin",),
        tenant_id=uuid4(),
        actor_type=actor_type,
    )


def _validate(request: ValidationRequest):
    validator = TransitionValidator(definition_store=MagicMock())
    with patch.object(
        TransitionValidator, "_load_definition", return_value=_definition()
    ):
        return validator.validate(request)


def test_agent_cannot_leave_proposed():
    result = _validate(_request("agent", "proposed", "draft"))
    assert result.valid is False
    assert result.error_code == EC_AGENT_SELF_CONFIRM


def test_agent_cannot_discard_its_own_proposal():
    result = _validate(_request("agent", "proposed", "rejected"))
    assert result.valid is False
    assert result.error_code == EC_AGENT_SELF_CONFIRM


def test_human_can_leave_proposed():
    assert _validate(_request("user", "proposed", "draft")).valid is True


def test_agent_may_still_transition_elsewhere():
    assert _validate(_request("agent", "draft", "approved")).valid is True


def _outdate_ctx(actor_type: str):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
    )


def test_outdate_blocks_an_agent_on_a_proposed_item():
    # NOTE: deviates from the plan's snippet, which asserted
    # ``lifecycle.force_transition.assert_not_called()`` — that method exists
    # on StateLifecycleManager but current outdate() (post Datenmodell-
    # Konsolidierung Phase 4 / Decision D-3) never calls it; it writes the
    # orthogonal soft-delete flag via the module-level ``_set_lifecycle_status``
    # helper instead. Assert on that real side effect.
    from workflow.services import WorkflowTransitionError, outdate

    lifecycle = MagicMock()
    lifecycle.get_item_state.return_value = MagicMock(current_state="proposed")
    with patch("workflow.services._get_lifecycle", return_value=lifecycle), patch(
        "workflow.services._set_lifecycle_status"
    ) as set_status:
        with pytest.raises(WorkflowTransitionError) as exc:
            outdate(uuid4(), "Requirement", WS, _outdate_ctx("agent"))
    assert exc.value.error_code == EC_AGENT_SELF_CONFIRM
    set_status.assert_not_called()


def test_outdate_allows_a_human_on_a_proposed_item():
    from workflow.services import outdate

    lifecycle = MagicMock()
    lifecycle.get_item_state.return_value = MagicMock(current_state="proposed")
    with patch("workflow.services._get_lifecycle", return_value=lifecycle), patch(
        "workflow.services._set_lifecycle_status"
    ) as set_status:
        result = outdate(uuid4(), "Requirement", WS, _outdate_ctx("user"))
    assert result.new_state == "outdated"
    assert result.previous_state == "proposed"
    set_status.assert_called_once()


# --- Security review M1 -----------------------------------------------------
# The hard-delete paths bypass the TransitionValidator exactly like outdate()
# does, so Rule 0 has to be re-asserted there too.


def _proposed_artifact_patches(current_state: str | None):
    lifecycle = MagicMock()
    lifecycle.get_item_state.return_value = (
        None if current_state is None else MagicMock(current_state=current_state)
    )
    return (
        patch("workflow.services._get_lifecycle", return_value=lifecycle),
        patch("workflow.services._item_id_for_artifact", return_value=uuid4()),
    )


def test_delete_artifact_guard_blocks_an_agent_on_a_proposal():
    from workflow.services import (
        WorkflowTransitionError,
        assert_agent_may_not_delete_proposed_artifact,
    )

    lifecycle_patch, item_patch = _proposed_artifact_patches("proposed")
    with lifecycle_patch, item_patch:
        with pytest.raises(WorkflowTransitionError) as exc:
            assert_agent_may_not_delete_proposed_artifact(
                _outdate_ctx("agent"), uuid4(), "Requirement", WS
            )
    assert exc.value.error_code == EC_AGENT_SELF_CONFIRM


def test_delete_artifact_guard_allows_a_human_on_a_proposal():
    from workflow.services import assert_agent_may_not_delete_proposed_artifact

    lifecycle_patch, item_patch = _proposed_artifact_patches("proposed")
    with lifecycle_patch, item_patch:
        assert (
            assert_agent_may_not_delete_proposed_artifact(
                _outdate_ctx("user"), uuid4(), "Requirement", WS
            )
            is None
        )


def test_delete_artifact_guard_allows_an_agent_on_a_normal_item():
    from workflow.services import assert_agent_may_not_delete_proposed_artifact

    lifecycle_patch, item_patch = _proposed_artifact_patches("draft")
    with lifecycle_patch, item_patch:
        assert (
            assert_agent_may_not_delete_proposed_artifact(
                _outdate_ctx("agent"), uuid4(), "Requirement", WS
            )
            is None
        )


def test_delete_artifact_guard_is_inert_without_a_workflow_state():
    """An unbacked / never-registered item is not a proposal — never deny."""
    from workflow.services import assert_agent_may_not_delete_proposed_artifact

    lifecycle_patch, item_patch = _proposed_artifact_patches(None)
    with lifecycle_patch, item_patch:
        assert (
            assert_agent_may_not_delete_proposed_artifact(
                _outdate_ctx("agent"), uuid4(), "Requirement", WS
            )
            is None
        )
