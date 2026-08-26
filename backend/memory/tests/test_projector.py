"""Tests for MemoryProjector (Task 5 + final whole-branch review Finding 2/4):
filters events, resolves tenant/user, respects the workspace toggle, and
delegates to the async task.

Producer-contract regression guard (Finding 2): payloads below are copied
verbatim from the real emission sites in ``application/interview_service.py``
(``generate_chat_turn``/``_generate_multi_chat_turn`` for
``INTERVIEW_CHAT_TURN``, ``_formalize_single``/``_formalize_multi`` for
``INTERVIEW_FORMALIZED``) -- NOT hand-invented shapes. This is deliberate: a
prior version of this file constructed a payload with ``tenant_id``/
``message`` keys no real producer ever sets, which passed while the real
pipeline silently never ran (see memory/projector.py's module docstring).
"""
from unittest.mock import patch

import pytest

from application.event_bus import DomainEvent
from memory.projector import MemoryProjector
from persistence.tests.factories import active_tenant, make_user, make_workspace


class TestMemoryProjectorEventFiltering:
    def test_ignores_irrelevant_event_types(self):
        import uuid

        projector = MemoryProjector()
        event = DomainEvent(event_type="RequirementCreated", entity_id=uuid.uuid4(), workspace_id=uuid.uuid4())
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            projector.handle_event(event)
        mock_task.delay.assert_not_called()


@pytest.mark.django_db
class TestMemoryProjectorRealPayloadShapes:
    def test_enqueues_task_for_interview_chat_turn(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)

            # Verbatim shape of application/interview_service.py's
            # generate_chat_turn() INTERVIEW_CHAT_TURN payload.
            event = DomainEvent(
                event_type="InterviewChatTurn",
                entity_id=ws.id,
                workspace_id=ws.id,
                payload={
                    "session_kind": "single",
                    "user_message": "We are a B2B SaaS company.",
                    "reply": "Got it, noted your company is B2B SaaS.",
                    "extracted_fields": ["title"],
                    "user_id": str(user.id),
                },
            )
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                projector = MemoryProjector()
                projector.handle_event(event)

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["tenant_id"] == str(tenant.id)
        assert kwargs["workspace_id"] == str(ws.id)
        assert kwargs["user_id"] == str(user.id)
        assert "B2B SaaS company" in kwargs["interaction_text"]
        assert "noted your company is B2B SaaS" in kwargs["interaction_text"]

    def test_enqueues_task_for_multi_chat_turn(self):
        """Verbatim shape of _generate_multi_chat_turn()'s payload (no
        "extracted_fields" key -- carries "has_proposal" instead)."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)

            event = DomainEvent(
                event_type="InterviewChatTurn",
                entity_id=ws.id,
                workspace_id=ws.id,
                payload={
                    "session_kind": "multi",
                    "user_message": "Add a login requirement.",
                    "reply": "Proposed a new Requirement artifact.",
                    "has_proposal": True,
                    "user_id": str(user.id),
                },
            )
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)

        mock_task.delay.assert_called_once()

    def test_interview_formalized_is_a_silent_noop_no_conversational_text(self):
        """Verbatim shape of _formalize_single()'s INTERVIEW_FORMALIZED
        payload -- no user_message/reply key exists, so this must not
        enqueue anything (no interaction text to consolidate) and must not
        touch the DB at all (no tenant/settings lookup)."""
        import uuid

        event = DomainEvent(
            event_type="InterviewFormalized",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            payload={
                "artifact_type": "Requirement",
                "resulting_artifact_ids": [str(uuid.uuid4())],
            },
        )
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            MemoryProjector().handle_event(event)  # must not raise, no DB needed
        mock_task.delay.assert_not_called()

    def test_skips_chat_turn_missing_user_id(self):
        """A chat-turn payload with real conversational text but no user_id
        (producer regression) is skipped with a warning, not enqueued."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)

            event = DomainEvent(
                event_type="InterviewChatTurn",
                entity_id=ws.id,
                workspace_id=ws.id,
                payload={
                    "session_kind": "single",
                    "user_message": "hello",
                    "reply": "hi",
                    "extracted_fields": [],
                },
            )
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        mock_task.delay.assert_not_called()

    def test_skips_unknown_workspace(self):
        """workspace_id that resolves to no real Workspace row (race with a
        concurrent delete, or a stale test double) -- tenant resolution
        returns None, nothing is enqueued."""
        import uuid

        event = DomainEvent(
            event_type="InterviewChatTurn",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            payload={
                "session_kind": "single",
                "user_message": "hello",
                "reply": "hi",
                "extracted_fields": [],
                "user_id": str(uuid.uuid4()),
            },
        )
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            MemoryProjector().handle_event(event)
        mock_task.delay.assert_not_called()

    def test_disabled_workspace_suppresses_consolidation(self):
        """Finding 4: WorkspaceMemorySettings(enabled=False) must gate the
        whole downstream chain, including the LLM-consolidation Celery task,
        at the cheapest point (before enqueue)."""
        from memory.models import WorkspaceMemorySettings

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            WorkspaceMemorySettings.objects.create(tenant_id=tenant.id, workspace=ws, enabled=False)

            event = DomainEvent(
                event_type="InterviewChatTurn",
                entity_id=ws.id,
                workspace_id=ws.id,
                payload={
                    "session_kind": "single",
                    "user_message": "hello",
                    "reply": "hi",
                    "extracted_fields": [],
                    "user_id": str(user.id),
                },
            )
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        mock_task.delay.assert_not_called()

    def test_missing_settings_row_defaults_to_enabled(self):
        """Mirrors WorkspaceMemorySettingsView.get's "missing row -> enabled:
        True" convention -- no settings row must not block consolidation."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)

            event = DomainEvent(
                event_type="InterviewChatTurn",
                entity_id=ws.id,
                workspace_id=ws.id,
                payload={
                    "session_kind": "single",
                    "user_message": "hello",
                    "reply": "hi",
                    "extracted_fields": [],
                    "user_id": str(user.id),
                },
            )
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        mock_task.delay.assert_called_once()
