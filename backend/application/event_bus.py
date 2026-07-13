"""
COMP-AS-016 DomainEventBus — Transactional Outbox + Subscriber Dispatch.

leaf_id : COMP-AS-016
req_id  : REQ-L2-AS-029, REQ-L2-AS-019, REQ-L2-AS-017

Publishes typed Domain-Events via the Transactional Outbox pattern:
  1. Caller invokes DomainEventBus.publish(event) inside an atomic block.
  2. publish() enqueues a lambda via transaction.on_commit(); if the TX is rolled
     back, the lambda never fires — no event for a rolled-back mutation.
  3. The on_commit callback inserts the event into DomainEventOutbox.
  4. An async worker (OutboxPoller) polls the outbox table, dispatches to
     registered subscribers, and marks events as published.

Interface contracts implemented:
  IF-AS-INT-009..017  — incoming event publications from domain services
  IF-AS-INT-013,014   — outgoing async subscriber dispatch

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-016_DomainEventBus/
      L3_COMP-AS-016_DomainEventBus_Architecture.md
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from application.models import DomainEventDLQ, DomainEventOutbox

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain-Event dataclass (typed carrier)
# ---------------------------------------------------------------------------


@dataclass
class DomainEvent:
    """Typed domain event carrier (REQ-L3-DEB-003).

    All fields required for outbox persistence and subscriber routing.
    """

    event_type: str                     # One of DomainEventOutbox.EventType values
    entity_id: UUID                     # Primary entity affected
    workspace_id: UUID                  # Tenant/workspace isolation
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for outbox payload field."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "entity_id": str(self.entity_id),
            "workspace_id": str(self.workspace_id),
            **self.payload,
        }


# ---------------------------------------------------------------------------
# Subscriber registry
# ---------------------------------------------------------------------------


class SubscriberRegistry:
    """Thread-safe registry mapping event_type → [callable].

    REQ-L3-DEB-005: dynamic registration, event-type-based filtering,
    multiple subscribers per type.
    """

    def __init__(self) -> None:
        self._registry: Dict[str, List[Callable[[DomainEvent], None]]] = {}
        self._lock = threading.Lock()

    def register(self, event_type: str, subscriber: Callable[[DomainEvent], None]) -> None:
        """Register *subscriber* for *event_type*."""
        with self._lock:
            self._registry.setdefault(event_type, [])
            if subscriber not in self._registry[event_type]:
                self._registry[event_type].append(subscriber)

    def unregister(self, event_type: str, subscriber: Callable[[DomainEvent], None]) -> None:
        """Remove *subscriber* from *event_type* list (no-op if not registered)."""
        with self._lock:
            if event_type in self._registry:
                try:
                    self._registry[event_type].remove(subscriber)
                except ValueError:
                    pass

    def get_subscribers(self, event_type: str) -> List[Callable[[DomainEvent], None]]:
        """Return a snapshot list of subscribers for *event_type*."""
        with self._lock:
            return list(self._registry.get(event_type, []))

    def all_subscribers(self) -> Dict[str, List[Callable[[DomainEvent], None]]]:
        """Return a copy of the full registry (for monitoring)."""
        with self._lock:
            return {k: list(v) for k, v in self._registry.items()}


# ---------------------------------------------------------------------------
# DomainEventBus Singleton
# ---------------------------------------------------------------------------


class DomainEventBus:
    """Central event-bus engine (Singleton pattern, thread-safe).

    COMP-AS-016. Producers call publish(); the actual DB write happens in the
    on_commit hook so that a TX rollback prevents the event.

    The OutboxPoller worker polls DomainEventOutbox and dispatches to subscribers.
    This class also exposes a dispatch_to_subscribers() method for use by the
    worker.

    ADR-L3-DEB-01 (Transactional Outbox), ADR-L3-DEB-02 (post_commit hook).
    """

    _instance: Optional["DomainEventBus"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DomainEventBus":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._registry = SubscriberRegistry()  # type: ignore[attr-defined]
                cls._instance = inst
        return cls._instance  # type: ignore[return-value]

    def publish(self, event: DomainEvent) -> None:
        """Enqueue *event* for persistence after the current transaction commits.

        Must be called inside an active Django transaction.atomic() block.
        The actual INSERT into DomainEventOutbox fires in the on_commit hook —
        guaranteeing that a rolled-back TX never produces an event.

        REQ-L3-DEB-002: Event is published in post_commit hook.
        REQ-L2-AS-029: Atomic binding to the mutating transaction.
        """
        # DomainEventOutbox is imported at module level to allow test mocking.
        def _insert() -> None:
            try:
                DomainEventOutbox.objects.create(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    workspace_id=event.workspace_id,
                    entity_id=event.entity_id,
                    payload=event.to_dict(),
                )
            except Exception:
                logger.exception(
                    "DomainEventBus: failed to persist event %s type=%s",
                    event.event_id,
                    event.event_type,
                )

        transaction.on_commit(_insert)

    def register_subscriber(
        self, event_type: str, subscriber: Callable[[DomainEvent], None]
    ) -> None:
        """Register a subscriber for a given event type (REQ-L3-DEB-005)."""
        self._registry.register(event_type, subscriber)

    def unregister_subscriber(
        self, event_type: str, subscriber: Callable[[DomainEvent], None]
    ) -> None:
        """Deregister a subscriber (REQ-L3-DEB-005)."""
        self._registry.unregister(event_type, subscriber)

    def get_subscriber_registry(self) -> Dict[str, List[Callable[[DomainEvent], None]]]:
        """Expose registry snapshot for monitoring (REQ-L3-DEB-010)."""
        return self._registry.all_subscribers()

    def dispatch_to_subscribers(self, event: DomainEvent, timeout_seconds: int = 30) -> None:
        """Dispatch *event* to all registered subscribers.

        Called by the OutboxPoller worker after fetching an unpublished event.
        Subscriber failures are logged but do not block other subscribers
        (REQ-L3-DEB-008: graceful degradation).

        Args:
            event: The domain event to dispatch.
            timeout_seconds: Maximum time per subscriber (default 30s).
        """
        subscribers = self._registry.get_subscribers(event.event_type)
        for subscriber in subscribers:
            try:
                start = time.monotonic()
                subscriber(event)
                elapsed = time.monotonic() - start
                if elapsed > timeout_seconds:
                    logger.warning(
                        "DomainEventBus: subscriber %s exceeded timeout %.1fs for event %s",
                        subscriber,
                        elapsed,
                        event.event_type,
                    )
            except Exception:
                logger.exception(
                    "DomainEventBus: subscriber %s failed for event %s id=%s",
                    subscriber,
                    event.event_type,
                    event.event_id,
                )


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------

_bus_instance: Optional[DomainEventBus] = None


def get_event_bus() -> DomainEventBus:
    """Return the process-singleton DomainEventBus instance."""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = DomainEventBus()
    return _bus_instance


# ---------------------------------------------------------------------------
# OutboxPoller (worker entry point — called by Celery or Django-Q task)
# ---------------------------------------------------------------------------

MAX_RETRIES: int = 5
POLL_BATCH_SIZE: int = 100


def poll_and_dispatch(batch_size: int = POLL_BATCH_SIZE) -> int:
    """Fetch unpublished events from the outbox and dispatch them.

    SELECT FOR UPDATE prevents concurrent workers from processing the same event
    (REQ-L3-DEB-003, ADR-L3-DEB-03).

    Returns:
        Number of events processed in this poll cycle.
    """
    # DomainEventDLQ and DomainEventOutbox are imported at module level.
    bus = get_event_bus()
    processed = 0

    with transaction.atomic():
        # SELECT FOR UPDATE skips already-locked rows (SKIP LOCKED)
        outbox_qs = (
            DomainEventOutbox.objects.select_for_update(skip_locked=True)
            .filter(published=False)
            .order_by("created_at")[:batch_size]
        )
        events_to_process = list(outbox_qs)

    for record in events_to_process:
        domain_event = DomainEvent(
            event_id=record.event_id,
            event_type=record.event_type,
            entity_id=record.entity_id,
            workspace_id=record.workspace_id,
            payload=record.payload,
        )
        try:
            bus.dispatch_to_subscribers(domain_event)
            record.published = True
            record.published_at = timezone.now()
            record.save(update_fields=["published", "published_at"])
            processed += 1
        except Exception as exc:
            record.retry_count += 1
            record.save(update_fields=["retry_count"])
            if record.retry_count >= MAX_RETRIES:
                # Move to DLQ atomically (REQ-021)
                with transaction.atomic():
                    DomainEventDLQ.objects.create(
                        event_id=record.event_id,
                        event_type=record.event_type,
                        workspace_id=record.workspace_id,
                        entity_id=record.entity_id,
                        payload=record.payload,
                        error_message=str(exc),
                        retry_count=record.retry_count,
                    )
                    record.delete()
                logger.error(
                    "DomainEventBus: event %s moved to DLQ after %d retries",
                    record.event_id,
                    record.retry_count,
                )
            else:
                logger.warning(
                    "DomainEventBus: event %s retry %d/%d — %s",
                    record.event_id,
                    record.retry_count,
                    MAX_RETRIES,
                    exc,
                )

    return processed


__all__ = [
    "DomainEvent",
    "DomainEventBus",
    "SubscriberRegistry",
    "get_event_bus",
    "poll_and_dispatch",
]
