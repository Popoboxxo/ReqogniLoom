"""
COMP-AS-016 DomainEventBus — Transactional Outbox + Subscriber Dispatch.

leaf_id : COMP-AS-016
req_id  : REQ-L2-AS-029, REQ-L2-AS-019, REQ-L2-AS-017

Publishes typed Domain-Events via the Transactional Outbox pattern:
  1. Caller invokes DomainEventBus.publish(event) inside an atomic block.
  2. publish() INSERTs the row into DomainEventOutbox *in that same
     transaction* — the mutation and its event commit or roll back together.
  3. An async worker (poll_and_dispatch) claims outbox rows, dispatches them to
     registered subscribers, and marks them published.

Two properties are load-bearing here and were both broken before SA-02/SA-04:

  * **The outbox INSERT must be in the caller's transaction, not in an
    ``on_commit`` hook** (SA-02). ``on_commit`` runs *after* COMMIT, so a
    process crash, a lost DB connection or an OOM kill in that window
    committed the mutation and silently dropped the event forever. The old
    code additionally swallowed insert failures, which turned a DB error into
    permanent, unlogged-at-the-caller event loss. That is the exact failure
    the Transactional Outbox pattern exists to prevent, so the insert now
    happens inline and is allowed to fail the caller's transaction.

  * **Subscriber dispatch must NOT run inside the claim transaction**
    (SA-04). Subscribers do external I/O — WebhookDispatcher performs up to 5
    HTTP POSTs with 10s timeouts plus 15s of back-off sleeps, i.e. ~65s per
    subscription — and holding a ``SELECT FOR UPDATE`` row lock plus an idle
    Postgres transaction for that long stalls the 5s poll cycle and every peer
    worker behind it. Dispatch therefore happens between two short
    transactions: claim, dispatch, write back.

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
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q
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

    COMP-AS-016. Producers call publish(); the outbox INSERT runs inline in
    the caller's own transaction (SA-02) so that a TX rollback prevents the
    event just as it prevents the mutation — a ``transaction.on_commit`` hook
    could not offer that guarantee (see module docstring above).

    The OutboxPoller worker polls DomainEventOutbox and dispatches to subscribers.
    This class also exposes a dispatch_to_subscribers() method for use by the
    worker.

    ADR-L3-DEB-01 (Transactional Outbox). ADR-L3-DEB-02 (post_commit hook) is
    superseded by SA-02 — see the docstring note in that architecture doc.
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
        """Persist *event* to the outbox inside the caller's transaction.

        Must be called inside an active ``transaction.atomic()`` block. The
        INSERT into ``DomainEventOutbox`` runs there and then, so the event row
        and the mutation that produced it share one fate: both commit, or
        neither does.

        SA-02 — this used to defer the INSERT to a ``transaction.on_commit``
        hook. That is *not* the transactional-outbox pattern: ``on_commit``
        callbacks fire after COMMIT has already returned, so anything that kills
        the process in that window (crash, OOM, SIGKILL during a deploy, a
        dropped DB connection) leaves a committed mutation with no event and no
        trace of one. Writing the row inline closes that window entirely; the
        rollback guarantee is unchanged, because a rolled-back transaction takes
        the outbox row with it.

        Raises:
            Exception: whatever the INSERT raises. Deliberately **not**
                swallowed. Inside an atomic block a failed statement has already
                poisoned the transaction — continuing would only surface later
                as ``TransactionManagementError`` — and, more importantly, an
                outbox row that cannot be written means the guarantee this
                method exists to provide cannot be met, so the caller's mutation
                must not commit either. (The previous implementation logged and
                swallowed, converting a DB error into silent event loss.)

        REQ-L3-DEB-002, REQ-L2-AS-029: atomic binding to the mutating
        transaction.
        """
        if not transaction.get_connection().in_atomic_block:
            # Not fatal — the INSERT below simply autocommits, which is the same
            # thing the old on_commit path did outside an atomic block (Django
            # runs the callback immediately there). It does mean this particular
            # event is not atomically bound to anything, so it is worth seeing.
            logger.warning(
                "DomainEventBus: publish() called outside a transaction "
                "(event %s type=%s) — the outbox row is not atomically bound "
                "to any mutation",
                event.event_id,
                event.event_type,
            )

        # DomainEventOutbox is imported at module level to allow test mocking.
        DomainEventOutbox.objects.create(
            event_id=event.event_id,
            event_type=event.event_type,
            workspace_id=event.workspace_id,
            entity_id=event.entity_id,
            payload=event.to_dict(),
        )

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

    def dispatch_to_subscribers(
        self, event: DomainEvent, timeout_seconds: int = 30
    ) -> List[str]:
        """Dispatch *event* to all registered subscribers.

        Called by the OutboxPoller worker after fetching an unpublished event.
        Subscriber failures are logged but do not block other subscribers
        (REQ-L3-DEB-008: graceful degradation) — every subscriber is always
        given a chance to run, even after an earlier one fails.

        Args:
            event: The domain event to dispatch.
            timeout_seconds: Maximum time per subscriber (default 30s).

        Returns:
            Error messages for subscribers that raised, one per failure.
            Empty list means every subscriber succeeded — the caller (
            poll_and_dispatch) uses this to decide whether the event may be
            marked published or must be retried/DLQ'd instead of silently
            losing it (see REQ-L3-DEB-008 vs. at-least-once REQ_072).
        """
        subscribers = self._registry.get_subscribers(event.event_type)
        errors: List[str] = []
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
            except Exception as exc:
                logger.exception(
                    "DomainEventBus: subscriber %s failed for event %s id=%s",
                    subscriber,
                    event.event_type,
                    event.event_id,
                )
                errors.append(f"{subscriber!r}: {exc}")
        return errors


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

#: How long a ``claimed_at`` stamp is honoured before a peer worker may take the
#: row over (SA-04).
#:
#: Upper bound comes from Celery, not from the dispatch cost: this poller runs as
#: ``application.dispatch_outbox_events``, so ``CELERY_TASK_TIME_LIMIT`` (180s,
#: settings.py) hard-kills the worker before any claim can legitimately live
#: longer than that. A claim older than 180s therefore belongs to a dead worker
#: by definition. 300s keeps a safety margin over that limit while still
#: returning a stranded row to the poll set within five minutes.
#:
#: Lower bound comes from the dispatch cost: WebhookDispatcher needs up to ~65s
#: per subscription (5 attempts x 10s HTTP timeout + 15s cumulative back-off), so
#: this must stay well above that or two workers would dispatch the same event
#: concurrently. Raising the Celery hard limit means raising this too.
CLAIM_TIMEOUT_SECONDS: int = 300


def _reclaim_cutoff() -> datetime:
    """Timestamp before which a ``claimed_at`` stamp counts as abandoned."""
    return timezone.now() - timedelta(seconds=CLAIM_TIMEOUT_SECONDS)


def _claim_event(pk: Any) -> Optional[DomainEventOutbox]:
    """Claim one outbox row and commit the claim before returning.

    The transaction here covers *only* the claim, so the ``SELECT FOR UPDATE``
    row lock is released the moment this function returns (SA-04). Peer workers
    are then kept off the row by ``claimed_at``, not by a held lock — which is
    what makes it safe to do slow, network-bound subscriber dispatch afterwards.

    Returns:
        The claimed record, or None if a peer worker got there first.
    """
    with transaction.atomic():
        record = (
            DomainEventOutbox.objects
            .select_for_update(skip_locked=True)
            .filter(pk=pk, published=False)
            .filter(Q(claimed_at__isnull=True) | Q(claimed_at__lt=_reclaim_cutoff()))
            .first()
        )
        if record is None:
            # Already published, deleted, freshly claimed, or row-locked by a
            # concurrent worker — all "someone else has it", all skip.
            return None

        # F5: a non-null claimed_at here means this row survived its
        # reclaim-cutoff filter above, i.e. this is a *reclaim* of an
        # abandoned claim, not a first attempt. If the worker that held the
        # previous claim died before reaching _finalize_failure (OOM, a
        # Celery hard-limit kill), retry_count never got incremented and the
        # row would otherwise be redelivered every CLAIM_TIMEOUT_SECONDS
        # forever, never reaching MAX_RETRIES/the DLQ. Count the reclaim
        # itself as a retry, committed now so it survives the very crash
        # that caused it.
        is_reclaim = record.claimed_at is not None
        record.claimed_at = timezone.now()
        if is_reclaim:
            record.retry_count += 1
            record.save(update_fields=["claimed_at", "retry_count"])
        else:
            record.save(update_fields=["claimed_at"])
        return record


def _finalize_success(pk: Any) -> bool:
    """Mark a dispatched event published and release its claim.

    A single conditional UPDATE rather than a re-SELECT: ``published=False`` in
    the filter makes it a no-op if a peer worker already finished this row.

    Returns:
        True if this call is the one that marked the row published.
    """
    return (
        DomainEventOutbox.objects
        .filter(pk=pk, published=False)
        .update(published=True, published_at=timezone.now(), claimed_at=None)
    ) == 1


def _move_to_dlq(record: DomainEventOutbox, error_message: str) -> None:
    """Move an exhausted event to the dead-letter queue (REQ-021).

    SA-05 — the move used to happen inside the claim transaction, so a failure
    here (DLQ insert error, constraint violation, connection blip) rolled back
    the ``retry_count`` increment along with it. The row then went back into the
    poll set with an unchanged retry_count and re-entered the exact same path on
    every cycle: a permanently stuck ``published=False`` row that never reached
    the DLQ and never stopped being retried.

    The increment is now already committed by the caller, and the move runs in
    its own transaction whose failure is logged and contained. Worst case the
    row stays in the outbox with retry_count above the limit and the move is
    re-attempted next cycle — progress, not a livelock.
    """
    try:
        with transaction.atomic():
            # get_or_create keyed on the unique event_id: if a previous attempt
            # inserted the DLQ row but failed before deleting the outbox row,
            # the retry must not trip the unique constraint.
            DomainEventDLQ.objects.get_or_create(
                event_id=record.event_id,
                defaults={
                    "event_type": record.event_type,
                    "workspace_id": record.workspace_id,
                    "entity_id": record.entity_id,
                    "payload": record.payload,
                    "error_message": error_message,
                    "retry_count": record.retry_count,
                },
            )
            DomainEventOutbox.objects.filter(pk=record.pk).delete()
    except Exception:
        logger.exception(
            "DomainEventBus: DLQ move failed for event %s — the outbox row is "
            "left in place with retry_count=%d and will be retried next cycle",
            record.event_id,
            record.retry_count,
        )
        return

    logger.error(
        "DomainEventBus: event %s moved to DLQ after %d retries",
        record.event_id,
        record.retry_count,
    )


def _finalize_failure(pk: Any, error_message: str) -> None:
    """Record a failed dispatch: bump retry_count, release the claim, maybe DLQ."""
    with transaction.atomic():
        record = (
            DomainEventOutbox.objects
            .select_for_update()
            .filter(pk=pk)
            .first()
        )
        if record is None:
            return  # DLQ'd or deleted by a peer worker in the meantime.
        record.retry_count += 1
        record.claimed_at = None
        record.save(update_fields=["retry_count", "claimed_at"])

    if record.retry_count < MAX_RETRIES:
        logger.warning(
            "DomainEventBus: event %s retry %d/%d — %s",
            record.event_id,
            record.retry_count,
            MAX_RETRIES,
            error_message,
        )
        return

    # Deliberately outside the transaction above: see _move_to_dlq (SA-05).
    _move_to_dlq(record, error_message)


def poll_and_dispatch(batch_size: int = POLL_BATCH_SIZE) -> int:
    """Fetch unpublished events from the outbox and dispatch them.

    Runs each event through three phases so that no lock is held across external
    I/O (SA-04):

      1. **Claim** — one short transaction takes the row under
         ``SELECT FOR UPDATE (skip_locked=True)``, stamps ``claimed_at`` and
         commits. Concurrent Celery workers cannot dispatch the same event twice
         (REQ-020, S-01, ADR-L3-DEB-03): they either skip the locked row or see
         a fresh ``claimed_at``.
      2. **Dispatch** — subscribers run with no transaction open and no row lock
         held. Subscribers own their own transaction and error semantics; the
         bus deliberately does not wrap them, because wrapping would put an idle
         Postgres transaction back around WebhookDispatcher's HTTP calls.
      3. **Write back** — a second short transaction records the outcome
         (published, or retry/DLQ).

    A worker that dies between phases leaves ``claimed_at`` set; the row becomes
    reclaimable after ``CLAIM_TIMEOUT_SECONDS`` and is redelivered. Delivery is
    therefore still at-least-once and subscribers must still be idempotent
    (REQ-072).

    Returns:
        Number of events processed in this poll cycle.
    """
    bus = get_event_bus()
    processed = 0

    # Fetch candidate PKs without a row-lock; individual workers race to claim
    # below. Rows under an active claim are excluded here as well, so a slow
    # dispatch does not keep re-appearing at the head of every batch.
    candidate_pks: List[Any] = list(
        DomainEventOutbox.objects
        .filter(published=False)
        .filter(Q(claimed_at__isnull=True) | Q(claimed_at__lt=_reclaim_cutoff()))
        .order_by("created_at")
        .values_list("pk", flat=True)[:batch_size]
    )

    for pk in candidate_pks:
        record = _claim_event(pk)
        if record is None:
            continue

        if record.retry_count >= MAX_RETRIES:
            # F5: a reclaim (see _claim_event) already pushed this row's
            # retry_count over the limit — a prior worker died mid-dispatch
            # without ever reaching _finalize_failure. Route straight to the
            # DLQ instead of dispatching it into the same worker-killing path
            # again.
            _move_to_dlq(
                record,
                "max retries exceeded after repeated stale-claim reclaim",
            )
            continue

        domain_event = DomainEvent(
            event_id=record.event_id,
            event_type=record.event_type,
            entity_id=record.entity_id,
            workspace_id=record.workspace_id,
            payload=record.payload,
        )

        # --- phase 2: dispatch, outside any transaction ---------------------
        try:
            # dispatch_to_subscribers is contractually non-raising (graceful
            # degradation per subscriber) — it reports failures via its return
            # value instead, so a failing subscriber still triggers retry/DLQ
            # rather than being marked published regardless. This try/except is
            # a backstop for the paths that sit *outside* that per-subscriber
            # guard, i.e. the registry snapshot and the join below: without it
            # one broken subscriber list would abort the whole poll cycle and
            # strand every remaining row with claimed_at set.
            errors = bus.dispatch_to_subscribers(domain_event)
            error_message = "; ".join(errors)
        except Exception as exc:
            logger.exception(
                "DomainEventBus: dispatch raised for event %s type=%s",
                record.event_id,
                record.event_type,
            )
            error_message = str(exc) or exc.__class__.__name__

        # --- phase 3: write the outcome back --------------------------------
        if error_message:
            _finalize_failure(pk, error_message)
        elif _finalize_success(pk):
            processed += 1

    # Outbox monitoring (REQ-069): surface dispatch throughput and backlog so a
    # growing outbox or DLQ is observable without querying the DB manually.
    backlog = DomainEventOutbox.objects.filter(published=False).count()
    dlq_count = DomainEventDLQ.objects.count()
    logger.info("DomainEventBus: dispatched %d event(s) this cycle", processed)
    logger.info("DomainEventBus: outbox backlog is %d pending event(s)", backlog)
    logger.info("DomainEventBus: dead-letter queue holds %d event(s)", dlq_count)

    return processed


__all__ = [
    "DomainEvent",
    "DomainEventBus",
    "SubscriberRegistry",
    "get_event_bus",
    "poll_and_dispatch",
]
