"""MemoryProjector — subscribes to interview events, enqueues consolidation.

Registered on ``application.event_bus``'s ``DomainEventBus`` (Transactional
Outbox) at process startup via ``MemoryConfig.ready()``, mirroring
``context_graph.projector.register_projector_on_event_bus`` (the first
projector wired on this bus). Unlike ``ContextGraphProjector`` (which
registers for every declared ``EventType`` and no-ops on irrelevant ones)
this projector only subscribes to the two event types it actually cares
about (Task 4: ``InterviewChatTurn``/``InterviewFormalized``) -- both
approaches are correct given ``SubscriberRegistry.register`` is keyed by
event type; this one is simply narrower since there is nothing to do for
any other event.

The handler itself does no DB work and holds no tenant context open -- it
only reads the in-memory ``DomainEvent`` payload and enqueues the actual
consolidation work (LLM call + memory upsert, Task 5's heavier logic) onto
the ``memory.consolidate_interaction`` Celery task, which runs in a worker
process and manages its own tenant-context activation (see
``memory/tasks.py`` and ``memory/backends.py``'s ``_tenant_context``).
"""
from __future__ import annotations

import logging

from application.event_bus import DomainEvent, get_event_bus
from application.models import DomainEventOutbox
from memory.tasks import consolidate_interaction_task

logger = logging.getLogger(__name__)

_RELEVANT_EVENT_TYPES = {
    DomainEventOutbox.EventType.INTERVIEW_CHAT_TURN,
    DomainEventOutbox.EventType.INTERVIEW_FORMALIZED,
}


class MemoryProjector:
    """Filters domain events down to interview activity worth consolidating."""

    def handle_event(self, event: DomainEvent) -> None:
        if event.event_type not in _RELEVANT_EVENT_TYPES:
            return

        payload = event.payload or {}
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        if not tenant_id or not user_id:
            # Producer forgot to stamp tenant_id/user_id onto the event
            # payload -- nothing safe to consolidate without both (the
            # backend is tenant/scope-keyed). Logged, not raised: one
            # malformed event must not block dispatch of others.
            logger.warning(
                "MemoryProjector: skipping event %s (type=%s) -- missing "
                "tenant_id/user_id in payload",
                event.event_id,
                event.event_type,
            )
            return

        consolidate_interaction_task.delay(
            tenant_id=tenant_id,
            workspace_id=str(event.workspace_id),
            user_id=user_id,
            interaction_text=payload.get("message", ""),
        )


def register_projector_on_event_bus() -> None:
    """Register :class:`MemoryProjector` for the interview event types."""
    bus = get_event_bus()
    projector = MemoryProjector()
    for event_type in _RELEVANT_EVENT_TYPES:
        bus.register_subscriber(event_type, projector.handle_event)
    logger.info(
        "MemoryProjector registered on DomainEventBus for %d event type(s).",
        len(_RELEVANT_EVENT_TYPES),
    )


__all__ = ["MemoryProjector", "register_projector_on_event_bus"]
