from application.models import DomainEventOutbox


class TestMemoryEventTypes:
    def test_interview_chat_turn_is_a_valid_event_type(self):
        values = {choice[0] for choice in DomainEventOutbox.EventType.choices}
        assert "InterviewChatTurn" in values
        assert "InterviewFormalized" in values

    def test_interaction_completed_is_a_valid_event_type(self):
        """Issue #1300: the generic confirmed-step event the memory loop reads."""
        values = {choice[0] for choice in DomainEventOutbox.EventType.choices}
        assert "InteractionCompleted" in values
