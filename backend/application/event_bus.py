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

import contextlib
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from application.models import DomainEventDLQ, DomainEventOutbox
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)


class UnresolvedTenantError(RuntimeError):
    """A tenant could not be resolved for an ``as_*`` write under enforcement.

    Raised by :meth:`DomainEventBus.publish` when ``RLS_AS_ENFORCED`` is on and
    neither the armed request tenant nor the ``workspace_id -> pl_workspace``
    relation yields a tenant. Failing here (rather than inserting a NULL-tenant
    row) is deliberate: under the armed policy a NULL-tenant row is invisible to
    the poller, i.e. the event would be silently dropped (#1183 / A4).
    """


class TenantMismatchError(UnresolvedTenantError):
    """An armed request tenant disagrees with the event workspace's tenant (#1183, F2).

    Subclasses :class:`UnresolvedTenantError` so existing fail-closed handlers
    catch it too, while callers that care can distinguish a *misattribution*
    from a *lookup miss*. Raised by :meth:`DomainEventBus.publish` only while
    ``RLS_AS_ENFORCED`` is on: the workspace relation is the authoritative
    tenant source, so a session armed to a different tenant must not stamp the
    row with that (wrong) tenant.
    """


def _workspace_tenant_id(workspace_id: Any) -> Optional[UUID]:
    """Return ``workspace_id -> pl_workspace.tenant_id`` or ``None``.

    Best-effort: a failure here (the relation is RLS-hidden, there is no DB in
    a unit test, or the workspace does not exist) yields ``None`` and lets the
    caller decide. Under enforcement a hidden workspace is a *signal* — the
    armed tenant does not own it — so the caller fails closed rather than
    guessing.
    """
    try:
        from persistence.models import Workspace

        return (
            Workspace.unscoped.filter(id=workspace_id)
            .values_list("tenant_id", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 — best-effort; callers fail closed on ON.
        logger.debug(
            "DomainEventBus: tenant lookup for workspace %s failed",
            workspace_id,
            exc_info=True,
        )
        return None


def _resolve_emission_tenant_id(workspace_id: Any) -> Optional[UUID]:
    """Resolve the tenant to stamp on a new outbox row (#1183 / A4 + F2).

    The **workspace relation is authoritative**: ``pl_workspace.tenant_id`` is
    the tenant the event actually belongs to. The armed request tenant is only
    an optimisation when the two agree; it is never trusted blindly.

    Order of authority:

    1. DEFAULT OFF (``RLS_AS_ENFORCED`` unset) — unchanged pre-#1183 behaviour:
       the armed request tenant wins, without a DB round-trip; otherwise fall
       back to ``workspace_id -> pl_workspace.tenant_id``.
    2. ENFORCEMENT ON — resolve the workspace tenant. If an armed session tenant
       disagrees with it, :class:`TenantMismatchError` is raised (fail closed):
       stamping the armed tenant would attribute the event to the wrong tenant,
       and stamping the workspace tenant would fail the policy's ``WITH CHECK``
       against ``app.current_tenant``. If the workspace tenant cannot be
       resolved at all, ``None`` is returned and :meth:`DomainEventBus.publish`
       raises :class:`UnresolvedTenantError` (covers a foreign/hidden workspace
       and a genuinely missing one).

    Returns ``None`` only when no tenant can be attributed.
    """
    armed = TenantContext.get_tenant() if TenantContext.is_set() else None

    # DEFAULT OFF: byte-for-byte the pre-#1183 behaviour, no DB round-trip when
    # a request tenant is already armed.
    if armed is not None and not _enforcement_enabled():
        return armed

    workspace_tenant = _workspace_tenant_id(workspace_id)

    if workspace_tenant is None:
        # Nothing authoritative to attribute the event to. Under enforcement
        # this includes a workspace hidden by RLS because the armed tenant does
        # not own it — never stamp the armed tenant in that case.
        if _enforcement_enabled():
            return None
        return armed

    if _enforcement_enabled() and armed is not None and armed != workspace_tenant:
        raise TenantMismatchError(
            f"DomainEventBus: armed request tenant {armed} does not own event "
            f"workspace {workspace_id} (tenant {workspace_tenant}); refusing to "
            "stamp a cross-tenant attribution while RLS_AS_ENFORCED is on."
        )

    return workspace_tenant


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
        #
        # #1183 / A4: stamp the tenant anchor at emission time. The staged
        # ``as_*`` policy's WITH CHECK compares ``tenant_id`` against the armed
        # ``app.current_tenant`` once ``RLS_AS_ENFORCED=on``; a row left NULL
        # would be invisible to the poller and the event silently dropped. Only
        # fail closed while enforcement is on — with the flag off (the ship
        # default) an unresolvable tenant keeps the pre-#1183 behaviour (NULL,
        # visible under the permissive policy).
        tenant_id = _resolve_emission_tenant_id(event.workspace_id)
        if tenant_id is None and getattr(settings, "RLS_AS_ENFORCED", False):
            raise UnresolvedTenantError(
                "DomainEventBus: cannot resolve a tenant for workspace "
                f"{event.workspace_id} while RLS_AS_ENFORCED is on; refusing "
                "to insert an outbox row that would be invisible under "
                f"enforcement (event {event.event_id})."
            )
        DomainEventOutbox.objects.create(
            event_id=event.event_id,
            event_type=event.event_type,
            workspace_id=event.workspace_id,
            entity_id=event.entity_id,
            payload=event.to_dict(),
            tenant_id=tenant_id,
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
# Consumer-side idempotency (ADR-014 §4, DATA-09 / finding N3)
# ---------------------------------------------------------------------------

#: How long a subscriber's ``event_id`` dedup marker is retained.
#:
#: The outbox is at-least-once: a worker that dies between claiming a row and
#: writing its outcome leaves ``claimed_at`` set, and the row is redelivered
#: once that claim ages past ``CLAIM_TIMEOUT_SECONDS`` (300 s). The window must
#: therefore comfortably exceed the reclaim delay (and the Celery hard limit it
#: is derived from) so a redelivery always finds the marker. 24 h mirrors the
#: ``Idempotency-Key`` replay window chosen in ADR-014 §3. A genuinely *new*
#: event always carries a fresh ``event_id`` and is never suppressed.
SUBSCRIBER_DEDUP_TTL_SECONDS: int = 24 * 60 * 60

_SUBSCRIBER_DEDUP_KEY_TEMPLATE = "outbox:dedup:{subscriber}:{event_id}"


def _subscriber_dedup_key(subscriber: str, event_id: Any) -> str:
    """Return the dedup-window key for one ``(subscriber, event_id)`` pair."""
    return _SUBSCRIBER_DEDUP_KEY_TEMPLATE.format(
        subscriber=subscriber, event_id=event_id
    )


def subscriber_already_processed(subscriber: str, event_id: Any) -> bool:
    """Return True if *subscriber* already recorded an effect for *event_id*.

    ADR-014 §4 places the idempotency requirement on the consumer: the bus is
    at-least-once, so a subscriber that would write again on redelivery checks
    this marker first. Fails **open** — if the dedup store is unreachable the
    delivery proceeds. At-least-once may then duplicate one effect, but
    silently dropping an event's effect would be strictly worse.
    """
    try:
        return cache.get(_subscriber_dedup_key(subscriber, event_id)) is not None
    except Exception:  # a dedup-store outage must not abort dispatch
        logger.warning(
            "DomainEventBus: dedup lookup failed for subscriber=%s event=%s — "
            "proceeding (at-least-once)",
            subscriber,
            event_id,
            exc_info=True,
        )
        return False


def mark_subscriber_processed(subscriber: str, event_id: Any) -> bool:
    """Claim the dedup marker for ``(subscriber, event_id)``.

    Returns True when this call created the marker (first delivery), False when
    it already existed or the store was unreachable. Callers invoke this
    **after** their effect succeeds — mirroring ``WebhookDispatcher``'s
    success-log receipt — so a crash before the effect leaves no marker and the
    redelivery still runs.
    """
    try:
        return bool(
            cache.add(
                _subscriber_dedup_key(subscriber, event_id),
                timezone.now().isoformat(),
                SUBSCRIBER_DEDUP_TTL_SECONDS,
            )
        )
    except Exception:  # see subscriber_already_processed
        logger.warning(
            "DomainEventBus: dedup claim failed for subscriber=%s event=%s — "
            "effect already applied, a duplicate is possible on redelivery",
            subscriber,
            event_id,
            exc_info=True,
        )
        return False


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
                    # #1183 / A4: carry the outbox row's tenant onto the DLQ row.
                    # The caller runs inside an armed per-row tenant context, so
                    # the policy's WITH CHECK accepts only this value.
                    "tenant_id": record.tenant_id,
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


def _enforcement_enabled() -> bool:
    """Return whether the staged ``as_*`` RLS enforcement flag is on.

    Read at call time (not import time) so ``override_settings`` and the
    operational env flag both take effect without a code change.
    """
    return bool(getattr(settings, "RLS_AS_ENFORCED", False))


def _list_candidate_pks(batch_size: int) -> List[Any]:
    """Candidate PKs via the ORM — the DEFAULT-OFF path (behaviour unchanged).

    Under the permissive policy (``RLS_AS_ENFORCED`` unset) the app role sees
    every tenant's rows, so the plain ORM query the poller has always used is
    correct. Rows under an active claim are excluded here as well, so a slow
    dispatch does not keep re-appearing at the head of every batch.
    """
    return list(
        DomainEventOutbox.objects
        .filter(published=False)
        .filter(Q(claimed_at__isnull=True) | Q(claimed_at__lt=_reclaim_cutoff()))
        .order_by("created_at")
        .values_list("pk", flat=True)[:batch_size]
    )


def _list_candidates_enforced(batch_size: int) -> List[tuple]:
    """Candidate ``(pk, tenant_id)`` pairs via the ``SECURITY DEFINER`` helper.

    ENFORCEMENT-ON path (#1183 / A4). With ``app.rls_as_enforced=on`` the app
    role cannot read ``as_domain_event_outbox`` without a tenant context, and
    the poller cannot know which tenant to arm before it has read the rows. The
    owner-privileged ``public.as_outbox_candidates`` resolves exactly that
    chicken-and-egg (residual R-8: dedicated non-superuser DEFINER, read-only
    body).

    The helper excludes NULL-``tenant_id`` orphans (F3), so they can never
    consume a batch slot at the head of the ``ORDER BY created_at`` window and
    starve legitimate events behind them; ``_worker_backlog`` still counts them.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, tenant_id FROM public.as_outbox_candidates(%s, %s)",
            [batch_size, _reclaim_cutoff()],
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]


@contextlib.contextmanager
def _armed_tenant(tenant_id: UUID) -> Iterator[None]:
    """Arm ``app.current_tenant`` for the enclosed per-row work (A4).

    Genuinely nesting-safe (F1): the previously armed tenant — both the
    thread-local ``TenantContext`` and the ``app.current_tenant`` GUC — is saved
    and restored on exit, so an outer context is never silently replaced by an
    inner one. If no tenant was armed before, the context armed here is cleared
    on exit (mirroring ``memory.backends._tenant_context``).
    """
    previous = TenantContext.get_tenant() if TenantContext.is_set() else None
    set_request_tenant(tenant_id)
    try:
        yield
    finally:
        if previous is not None:
            set_request_tenant(previous)
        elif TenantContext.is_set():
            clear_request_tenant()


def _worker_backlog() -> tuple:
    """Return ``(outbox_pending, dlq_total, orphan_pending)`` for monitoring.

    Under enforcement a plain app-role ``count()`` would see only the currently
    armed tenant (or nothing), so the tenant-agnostic aggregate comes from the
    ``SECURITY DEFINER`` helper. With the flag off the ORM counts are unchanged,
    except that ``orphan_pending`` is also computed from the ORM.

    ``orphan_pending`` counts the unpublished NULL-tenant rows that
    ``as_outbox_candidates`` excludes (F3): they are skipped fail-closed and can
    never be claimed, so they are surfaced here instead of silently disappearing
    from the backlog.
    """
    if _enforcement_enabled():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT outbox_pending, dlq_total, orphan_pending "
                "FROM public.as_worker_backlog()"
            )
            row = cursor.fetchone()
        return int(row[0]), int(row[1]), int(row[2])
    return (
        DomainEventOutbox.objects.filter(published=False).count(),
        DomainEventDLQ.objects.count(),
        DomainEventOutbox.objects.filter(
            published=False, tenant_id__isnull=True
        ).count(),
    )


def _process_one(pk: Any, bus: DomainEventBus) -> int:
    """Claim, dispatch and write back a single outbox row.

    Extracted verbatim from the poll loop so the DEFAULT-OFF and the
    ENFORCEMENT-ON path share exactly one implementation of the
    claim/dispatch/write-back sequence (SA-04). The only difference between the
    paths is the surrounding tenant context. Returns 1 if the row was marked
    published, else 0.
    """
    record = _claim_event(pk)
    if record is None:
        return 0

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
        return 0

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
        return 0
    if _finalize_success(pk):
        return 1
    return 0


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

    Tenant arming (#1183 / A4): while ``RLS_AS_ENFORCED`` is off (the ship
    default) this method is byte-for-byte the previous behaviour — plain ORM
    candidate listing and no tenant context. With the flag on, candidates come
    from ``public.as_outbox_candidates`` and each row is processed inside an
    ``app.current_tenant`` context armed from that row's ``tenant_id``. Rows
    with a NULL ``tenant_id`` (unresolvable workspace anchor, O-2) are excluded
    from the candidate list by the helper (F3) so a head-of-line block of them
    cannot starve legitimate events; they stay visible via the orphan counter in
    ``_worker_backlog``. The in-loop NULL guard below is kept as a defensive
    backstop should a candidate ever arrive without a tenant.

    Returns:
        Number of events processed in this poll cycle.
    """
    bus = get_event_bus()
    processed = 0

    if _enforcement_enabled():
        for pk, tenant_id in _list_candidates_enforced(batch_size):
            if tenant_id is None:
                # Fail closed: an orphan row cannot be processed without
                # guessing a tenant, and arming the wrong tenant would violate
                # the policy. Leave it for operator attention (O-2: never
                # delete). Defensive backstop — as_outbox_candidates already
                # excludes NULL-tenant rows (F3).
                logger.warning(
                    "DomainEventBus: skipping outbox event %s — tenant_id is "
                    "NULL (unresolvable workspace); fail-closed under "
                    "RLS_AS_ENFORCED",
                    pk,
                )
                continue
            with _armed_tenant(UUID(str(tenant_id))):
                processed += _process_one(pk, bus)
    else:
        for pk in _list_candidate_pks(batch_size):
            processed += _process_one(pk, bus)

    # Outbox monitoring (REQ-069): surface dispatch throughput and backlog so a
    # growing outbox or DLQ is observable without querying the DB manually.
    backlog, dlq_count, orphan_count = _worker_backlog()
    if orphan_count:
        logger.warning(
            "DomainEventBus: %d orphaned outbox event(s) have no tenant_id and "
            "are excluded from the candidate list (fail-closed); backfill or "
            "inspect them (O-2: never deleted)",
            orphan_count,
        )
    logger.info("DomainEventBus: dispatched %d event(s) this cycle", processed)
    logger.info("DomainEventBus: outbox backlog is %d pending event(s)", backlog)
    logger.info("DomainEventBus: dead-letter queue holds %d event(s)", dlq_count)

    return processed


__all__ = [
    "SUBSCRIBER_DEDUP_TTL_SECONDS",
    "DomainEvent",
    "DomainEventBus",
    "SubscriberRegistry",
    "TenantMismatchError",
    "UnresolvedTenantError",
    "get_event_bus",
    "mark_subscriber_processed",
    "poll_and_dispatch",
    "subscriber_already_processed",
]
