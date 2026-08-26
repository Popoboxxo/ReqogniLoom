"""Tests for MemoryProjector (Task 5 + final whole-branch review Finding 2/4,
round-2 Finding A): filters events, resolves tenant/user, respects the
workspace toggle, and delegates to the async task.

Producer-contract regression guard (Finding 2 / round-2 Finding A): payloads
below are copied verbatim from the real emission sites in
``application/interview_service.py`` (``generate_chat_turn``/
``_generate_multi_chat_turn`` for ``INTERVIEW_CHAT_TURN``,
``_formalize_single``/``_formalize_multi`` for ``INTERVIEW_FORMALIZED``) --
NOT hand-invented shapes. This is deliberate: a prior version of this file
constructed a payload with ``tenant_id``/``message`` keys no real producer
ever sets, which passed while the real pipeline silently never ran (see
memory/projector.py's module docstring). ``tenant_id`` is now ALSO part of
that verbatim shape (round-2 Finding A: stamped at emission time, same as
``user_id``, instead of resolved via an RLS-blocked ``Workspace`` DB query).
"""
from unittest.mock import patch

import pytest

from application.event_bus import DomainEvent
from memory.projector import MemoryProjector
from persistence.middleware import clear_request_tenant
from persistence.tenancy import TenantContext
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
                    "tenant_id": str(tenant.id),
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
                    "tenant_id": str(tenant.id),
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
        """A chat-turn payload with real conversational text and a tenant_id
        but no user_id (producer regression) is skipped with a warning, not
        enqueued."""
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
                    "tenant_id": str(tenant.id),
                },
            )
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        mock_task.delay.assert_not_called()

    def test_skips_chat_turn_missing_tenant_id(self):
        """Round-2 Finding A: a chat-turn payload with real conversational
        text but no tenant_id (producer regression -- the emission site
        forgot to stamp it) is skipped with a warning, not enqueued, and
        must NOT fall back to a Workspace DB lookup (there is none left in
        the projector at all -- see memory/projector.py's module
        docstring)."""
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
            MemoryProjector().handle_event(event)  # must not raise, no DB needed
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
                    "tenant_id": str(tenant.id),
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
                    "tenant_id": str(tenant.id),
                },
            )
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        mock_task.delay.assert_called_once()

    def test_enqueues_task_with_no_ambient_tenant_context(self):
        """Round-2 Finding A, structural regression guard: the real Celery
        worker's ``poll_and_dispatch`` (application/event_bus.py) hands
        ``handle_event`` a ``DomainEvent`` with NO ``TenantContext`` armed
        and no ``app.current_tenant`` session variable set -- unlike every
        other test above, which calls ``handle_event`` from INSIDE
        ``with active_tenant():`` and therefore leaves both isolation
        layers armed for the whole call. Test data is created via
        ``active_tenant()`` for SETUP only; the context is explicitly
        cleared before ``handle_event`` runs, to genuinely simulate the
        real worker's starting condition -- this is exactly the gap the
        prior fix round's tests could not exercise (see
        memory/projector.py's module docstring).

        This is a structural proof (no DB role switch -- see
        ``memory/tests/test_projector_rls_tenant_resolution.py`` for the
        genuine RLS-enforced version of this same scenario, which the test
        DB's superuser connection here cannot reproduce on its own): it
        proves ``handle_event`` no longer NEEDS an ambient context at all
        for tenant resolution, because ``tenant_id`` comes straight off the
        payload (stamped at emission time) instead of a
        context-dependent ``Workspace`` DB query.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            tenant_id, ws_id, user_id = tenant.id, ws.id, user.id

        # active_tenant()'s __exit__ already clears both layers (see
        # persistence/tests/factories.py); assert it explicitly and clear
        # again defensively so this test does not silently pass by accident
        # of ordering/fixture reuse.
        clear_request_tenant()
        assert not TenantContext.is_set()

        event = DomainEvent(
            event_type="InterviewChatTurn",
            entity_id=ws_id,
            workspace_id=ws_id,
            payload={
                "session_kind": "single",
                "user_message": "We are a B2B SaaS company.",
                "reply": "Got it, noted your company is B2B SaaS.",
                "extracted_fields": ["title"],
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
            },
        )
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            MemoryProjector().handle_event(event)

        assert not TenantContext.is_set(), (
            "handle_event must leave no tenant context armed behind it -- "
            "_tenant_context's nesting guard should have torn down exactly "
            "what it armed"
        )
        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["tenant_id"] == str(tenant_id)
        assert kwargs["workspace_id"] == str(ws_id)
        assert kwargs["user_id"] == str(user_id)
