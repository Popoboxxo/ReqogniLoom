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
beyond a lightweight settings lookup -- the actual consolidation work (LLM
call + memory upsert, Task 5's heavier logic) is enqueued onto the
``memory.consolidate_interaction`` Celery task, which runs in a worker
process and manages its own tenant-context activation (see
``memory/tasks.py`` and ``memory/backends.py``'s ``_tenant_context``).

Contract correction (final whole-branch review, Finding 2): earlier versions
of this projector read ``payload.get("tenant_id")``, ``payload.get("user_id")``
and ``payload.get("message")`` -- keys NO real producer
(``application.interview_service``'s ``INTERVIEW_CHAT_TURN``/
``INTERVIEW_FORMALIZED`` emissions) ever sets, so every real event silently
took the "missing tenant/user" skip branch and no memory was ever
consolidated from a real interaction. Fixed to mirror
``ContextGraphProjector``'s exact pattern:

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

Tenant resolution correction (final whole-branch review ROUND 2, Finding A):
the version fixing Finding 2 above resolved ``tenant_id`` from
``event.workspace_id`` via ``Workspace.unscoped.filter(...)``, mirroring
``ContextGraphProjector._resolve_tenant_id`` -- but that mirror carries over
a bug that happens to be invisible in ``ContextGraphProjector``'s own tests
too: ``unscoped`` is a Django-ORM-manager-level escape hatch ONLY. It does
**not** bypass PostgreSQL Row-Level Security, and ``pl_workspace`` has
``ENABLE + FORCE ROW LEVEL SECURITY`` (persistence/migrations/
0003_rls_policies.py). The real Celery worker connects as the least-privilege,
NOSUPERUSER ``reqogniloom_app`` role (persistence/db_roles.py, REQ-L2-PL-010)
-- RLS applies to it regardless of ``unscoped`` -- and ``poll_and_dispatch``
(application/event_bus.py) never arms ``app.current_tenant`` before dispatch
(chicken-and-egg: arming it is exactly what resolving the tenant was for).
So the ``Workspace`` SELECT was silently hidden by RLS (0 rows) for every
real event, ``_resolve_tenant_id`` always returned ``None``, and
``handle_event`` always took the "workspace gone" skip branch -- the SAME
end symptom as Finding 2 (no memory ever consolidated from a real
interaction), just via a subtler, still-RLS-shaped cause. Every test in this
module's and ``memory/tests/test_consolidation_e2e.py``'s suites ran inside
``persistence.tests.factories.active_tenant()``, which arms
``app.current_tenant`` BEFORE the test body runs, so this never showed up
there; the least-privilege ``reqogniloom_app`` role also never applied to
the (superuser) test DB connection to begin with -- see
``memory/tests/test_projector_rls_tenant_resolution.py`` for the
regression test that reproduces both conditions together.

Fix: mirror ``llm_adapter.tasks.run_capability``'s established solution to
the exact same chicken-and-egg problem (a Celery task that needs a tenant_id
before any tenant context exists to query anything with) -- resolve
``tenant_id`` at EVENT-EMISSION time, when real request-scoped tenant
context (``ctx.tenant_id``) genuinely is available, and stamp it onto the
payload directly, exactly like ``user_id`` above. Both ``INTERVIEW_CHAT_TURN``
emission sites in ``interview_service.py`` now set
``"tenant_id": str(ctx.tenant_id)``. This sidesteps the RLS problem
entirely: no ``Workspace`` lookup is needed in the projector at all.
``INTERVIEW_FORMALIZED`` events never reach this point (empty interaction
text always short-circuits first), so they never need a ``tenant_id``.

Finding 4 (workspace memory on/off toggle): also mirrors
``ContextGraphProjector``'s settings check, but -- also part of round-2
Finding A -- the ``WorkspaceMemorySettings`` lookup is now wrapped in
``memory.backends._tenant_context(tenant_id)`` using the payload-resolved
``tenant_id`` from above, instead of an ``unscoped`` query with no context
armed. Without this, a disabled-workspace row would be RLS-hidden in the
real deployment and silently misread as "no settings row -> enabled=True"
-- the right-looking default for the wrong (RLS-blocked), DSGVO-relevant
reason. The toggle is enforced BEFORE Celery dispatch, so a disabled
workspace's interactions never reach the LLM extraction call or write any
``WorkspaceMemory``/``UserTenantMemory`` row. ``UserTenantMemory`` is
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
from memory.backends import _tenant_context
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

        # tenant_id is stamped onto the payload at emission time (see module
        # docstring, round-2 Finding A) -- NOT resolved here via a
        # Workspace DB query, which would be RLS-blocked with no tenant
        # context armed yet in the real Celery worker.
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            # Producer forgot to stamp tenant_id onto the event payload --
            # nothing safe to resolve/consolidate without it (the settings
            # lookup below and the Celery task both need it). Logged, not
            # raised: one malformed event must not block dispatch of others.
            logger.warning(
                "MemoryProjector: skipping event %s (type=%s) -- missing "
                "tenant_id in payload",
                event.event_id,
                event.event_type,
            )
            return

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

        # Arm both isolation layers with the payload-resolved tenant_id
        # (nesting-safe -- see _tenant_context's docstring) around the
        # settings lookup, so it is subject to RLS the same way it would be
        # in the real deployment, instead of running unscoped/context-free.
        with _tenant_context(UUID(str(tenant_id))):
            if not self._is_workspace_memory_enabled(event.workspace_id):
                return  # not an error -- event for a disabled workspace is "handled"

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
    # Settings lookup (Finding 4 -- mirrors ContextGraphProjector's
    # WorkspaceContextSettings check, but memory's "missing row" convention
    # is enabled=True, not enabled=False -- see WorkspaceMemorySettings'
    # docstring and memory_rest.WorkspaceMemorySettingsView.get).
    #
    # Round-2 Finding A: this MUST be called with `tenant_id` already armed
    # via `memory.backends._tenant_context` (see handle_event above) -- the
    # tenant-scoped `.objects` manager below raises TenantContextNotSetError
    # otherwise, and even a plain `.unscoped` query would be silently
    # RLS-hidden (0 rows -> misread as "no settings row -> enabled=True",
    # the right-looking default for the wrong, RLS-blocked reason) against
    # the real, least-privilege, FORCE-RLS `reqogniloom_app` connection.
    # ------------------------------------------------------------------

    @staticmethod
    def _is_workspace_memory_enabled(workspace_id: UUID) -> bool:
        from memory.models import WorkspaceMemorySettings

        row = (
            WorkspaceMemorySettings.objects.filter(workspace_id=workspace_id)
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
