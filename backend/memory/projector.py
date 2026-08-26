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

The handler itself does no heavy DB work and holds no tenant context open
beyond a lightweight, ``unscoped`` settings/tenant lookup -- the actual
consolidation work (LLM call + memory upsert, Task 5's heavier logic) is
enqueued onto the ``memory.consolidate_interaction`` Celery task, which runs
in a worker process and manages its own tenant-context activation (see
``memory/tasks.py`` and ``memory/backends.py``'s ``_tenant_context``).

Contract correction (final whole-branch review, Finding 2): earlier versions
of this projector read ``payload.get("tenant_id")``, ``payload.get("user_id")``
and ``payload.get("message")`` -- keys NO real producer
(``application.interview_service``'s ``INTERVIEW_CHAT_TURN``/
``INTERVIEW_FORMALIZED`` emissions) ever sets, so every real event silently
took the "missing tenant/user" skip branch and no memory was ever
consolidated from a real interaction. Fixed to mirror
``ContextGraphProjector``'s exact pattern:

* ``tenant_id`` is resolved from ``event.workspace_id`` via the ``unscoped``
  escape hatch (this handler runs outside any request/tenant-context), not
  read from the payload.
* ``user_id`` is read from the payload -- ``DomainEvent``/``ServiceBase.
  _make_event`` carry no actor identity today (verified: neither
  ``application/base.py::_make_event`` nor ``application/event_bus.py::
  DomainEvent`` has a user/actor field), so both ``INTERVIEW_CHAT_TURN``
  emission sites in ``interview_service.py`` now stamp
  ``"user_id": str(ctx.user_id)`` onto the payload explicitly.
* the interaction text is built from the ``user_message``/``reply`` keys the
  producer actually emits (chat-turn payload shape), not a ``"message"`` key
  nothing ever sets. ``INTERVIEW_FORMALIZED`` payloads carry neither key, so
  the resulting empty interaction text hits ``consolidate_interaction``'s own
  no-op guard -- no facts are (or should be) extracted from a formalize
  event, which carries no conversational text.

Finding 4 (workspace memory on/off toggle): also mirrors
``ContextGraphProjector``'s settings check -- looked up via ``unscoped``
BEFORE tenant context / Celery dispatch, so a disabled workspace's
interactions never reach the LLM extraction call or write any
``WorkspaceMemory``/``UserTenantMemory`` row (the toggle is documented as
DSGVO-relevant; the cheapest and most complete place to enforce it is here,
before the Celery task is even enqueued). ``UserTenantMemory`` is
tenant-wide, not workspace-scoped, but this toggle is intentionally
interpreted as "was this interaction, which happened in this workspace,
allowed to be consolidated" -- so a disabled workspace suppresses BOTH
scopes for events sourced from it, not just the workspace-scoped one.
"""
from __future__ import annotations

import logging
from uuid import UUID

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

        # Cheapest check first, pure payload parsing, no DB: an
        # INTERVIEW_FORMALIZED event (or any other malformed chat-turn
        # payload) carrying no conversational text is a silent, expected
        # no-op here -- not a producer bug worth a warning, and not worth a
        # workspace-settings/tenant DB round-trip.
        interaction_text = self._build_interaction_text(payload)
        if not interaction_text:
            return

        if not self._is_workspace_memory_enabled(event.workspace_id):
            return  # not an error -- event for a disabled workspace is "handled"

        tenant_id = self._resolve_tenant_id(event.workspace_id)
        if tenant_id is None:
            return  # workspace gone (race with a concurrent delete) -- nothing left to project

        user_id = payload.get("user_id")
        if not user_id:
            # Producer forgot to stamp user_id onto the event payload --
            # nothing safe to consolidate without it (both memory scopes are
            # keyed by user or workspace). Logged, not raised: one malformed
            # event must not block dispatch of others. Only reached once we
            # already know there IS text to consolidate, so this only fires
            # for a genuine chat-turn producer regression, never for the
            # expected-empty-text INTERVIEW_FORMALIZED case above.
            logger.warning(
                "MemoryProjector: skipping event %s (type=%s) -- missing "
                "user_id in payload",
                event.event_id,
                event.event_type,
            )
            return

        consolidate_interaction_task.delay(
            tenant_id=str(tenant_id),
            workspace_id=str(event.workspace_id),
            user_id=str(user_id),
            interaction_text=interaction_text,
        )

    # ------------------------------------------------------------------
    # Interaction-text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_interaction_text(payload: dict) -> str:
        """Build the text fed to ``memory.extract`` from a chat-turn payload.

        ``INTERVIEW_CHAT_TURN`` payloads (see both emission sites in
        ``interview_service.py``) carry ``user_message``/``reply`` -- never a
        ``"message"`` key. Both are combined so the extraction prompt sees
        the full exchange (a fact stated by the user AND confirmed/restated
        by the assistant is stronger evidence than the user's utterance
        alone). ``INTERVIEW_FORMALIZED`` payloads carry neither key, so this
        correctly degrades to "".
        """
        user_message = str(payload.get("user_message") or "").strip()
        reply = str(payload.get("reply") or "").strip()
        if user_message and reply:
            return f"User: {user_message}\nAssistant: {reply}"
        return user_message or reply

    # ------------------------------------------------------------------
    # Tenant resolution (mirrors ContextGraphProjector._resolve_tenant_id)
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_tenant_id(workspace_id: UUID):
        from persistence.models import Workspace

        return (
            Workspace.unscoped.filter(id=workspace_id)
            .values_list("tenant_id", flat=True)
            .first()
        )

    # ------------------------------------------------------------------
    # Settings lookup (Finding 4 -- mirrors ContextGraphProjector's
    # WorkspaceContextSettings check, but memory's "missing row" convention
    # is enabled=True, not enabled=False -- see WorkspaceMemorySettings'
    # docstring and memory_rest.WorkspaceMemorySettingsView.get).
    # ------------------------------------------------------------------

    @staticmethod
    def _is_workspace_memory_enabled(workspace_id: UUID) -> bool:
        from memory.models import WorkspaceMemorySettings

        # unscoped: this runs before tenant context is established for this
        # event (resolving settings is how we decide whether to bother
        # doing anything at all) -- mirrors _resolve_tenant_id above and
        # ContextGraphProjector._load_settings.
        row = (
            WorkspaceMemorySettings.unscoped.filter(workspace_id=workspace_id)
            .values_list("enabled", flat=True)
            .first()
        )
        return True if row is None else row


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
