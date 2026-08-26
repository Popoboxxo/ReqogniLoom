from application.models import DomainEventOutbox


class TestMemoryEventTypes:
    def test_interview_chat_turn_is_a_valid_event_type(self):
        values = {choice[0] for choice in DomainEventOutbox.EventType.choices}
        assert "InterviewChatTurn" in values
        assert "InterviewFormalized" in values
