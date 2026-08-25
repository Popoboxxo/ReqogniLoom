"""Tests for MemoryProjector (Task 5): filters events, delegates to the async task."""
from unittest.mock import patch
from uuid import uuid4

from application.event_bus import DomainEvent
from memory.projector import MemoryProjector


class TestMemoryProjector:
    def test_ignores_irrelevant_event_types(self):
        projector = MemoryProjector()
        event = DomainEvent(event_type="RequirementCreated", entity_id=uuid4(), workspace_id=uuid4())
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            projector.handle_event(event)
        mock_task.delay.assert_not_called()

    def test_enqueues_task_for_interview_chat_turn(self):
        projector = MemoryProjector()
        event = DomainEvent(
            event_type="InterviewChatTurn",
            entity_id=uuid4(),
            workspace_id=uuid4(),
            payload={"tenant_id": str(uuid4()), "user_id": str(uuid4()), "message": "hello"},
        )
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            projector.handle_event(event)
        mock_task.delay.assert_called_once()

    def test_enqueues_task_for_interview_formalized(self):
        projector = MemoryProjector()
        event = DomainEvent(
            event_type="InterviewFormalized",
            entity_id=uuid4(),
            workspace_id=uuid4(),
            payload={"tenant_id": str(uuid4()), "user_id": str(uuid4()), "message": "done"},
        )
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            projector.handle_event(event)
        mock_task.delay.assert_called_once()

    def test_skips_event_missing_tenant_or_user_id(self):
        projector = MemoryProjector()
        event = DomainEvent(
            event_type="InterviewChatTurn",
            entity_id=uuid4(),
            workspace_id=uuid4(),
            payload={"message": "hello"},
        )
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            projector.handle_event(event)
        mock_task.delay.assert_not_called()
