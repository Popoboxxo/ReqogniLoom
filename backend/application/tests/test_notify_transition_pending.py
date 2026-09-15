"""transition_pending: role broadcast, not person-scoped routing (spec §5.1)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.notification_service import notify_transition_pending


def _transition(from_state, to_state, roles):
    t = MagicMock()
    t.from_state = from_state
    t.to_state = to_state
    t.allowed_roles = tuple(roles)
    return t


def _definition(transitions):
    definition = MagicMock()
    definition.transitions = tuple(transitions)
    return definition


@pytest.mark.django_db
def test_collects_roles_of_all_outgoing_transitions():
    approver, admin = uuid.uuid4(), uuid.uuid4()

    with patch(
        "application.notification_service._get_definition",
        return_value=_definition([
            _transition("review", "approved", ["approver", "admin"]),
            _transition("review", "draft", ["editor"]),
            _transition("draft", "review", ["editor"]),  # not outgoing from `review`
        ]),
    ), patch(
        "application.notification_service._user_ids_with_roles",
        return_value=[approver, admin],
    ) as lookup, patch(
        "application.notification_service.create_notifications", return_value=2
    ) as notify, patch(
        "application.notification_service.resolve_artifact_id_or_none", return_value=None
    ):
        written = notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="review",
            tenant_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )

    assert written == 2
    assert set(lookup.call_args.kwargs["roles"]) == {"approver", "admin", "editor"}
    assert notify.call_args.kwargs["kind"] == "transition_pending"


@pytest.mark.django_db
def test_terminal_state_notifies_nobody():
    with patch(
        "application.notification_service._get_definition",
        return_value=_definition([_transition("draft", "review", ["editor"])]),
    ), patch("application.notification_service.create_notifications") as notify:
        written = notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="approved",  # no outgoing transitions
            tenant_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )

    assert written == 0
    notify.assert_not_called()


@pytest.mark.django_db
def test_the_actor_is_not_notified_about_their_own_transition():
    actor = uuid.uuid4()

    with patch(
        "application.notification_service._get_definition",
        return_value=_definition([_transition("review", "approved", ["approver"])]),
    ), patch(
        "application.notification_service._user_ids_with_roles", return_value=[actor]
    ), patch(
        "application.notification_service.create_notifications", return_value=0
    ) as notify, patch(
        "application.notification_service.resolve_artifact_id_or_none", return_value=None
    ):
        notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="review",
            tenant_id=uuid.uuid4(),
            actor_user_id=actor,
        )

    assert notify.call_args.kwargs["exclude_user_id"] == actor


@pytest.mark.django_db
def test_a_missing_workflow_definition_is_not_fatal():
    """A notification must never break the transition it reacts to."""
    from workflow.definition_store import WorkflowDefinitionError

    with patch(
        "application.notification_service._get_definition",
        side_effect=WorkflowDefinitionError("none"),
    ):
        assert notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="review",
            tenant_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        ) == 0


def test_workflow_transition_calls_the_producer():
    import inspect

    from workflow.services import transition

    assert "notify_transition_pending(" in inspect.getsource(transition)
