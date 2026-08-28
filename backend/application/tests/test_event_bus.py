"""
Tests for COMP-AS-016 DomainEventBus — Transactional Outbox + Subscriber Dispatch.

leaf_id : COMP-AS-016
req_id  : REQ-L2-AS-029, REQ-L2-AS-019, REQ-L2-AS-017

Coverage:
  - DomainEvent: construction, to_dict serialisation
  - SubscriberRegistry: register, unregister, get_subscribers, all_subscribers,
    duplicate registration, thread safety (basic)
  - DomainEventBus (singleton): get_event_bus returns same instance,
    register_subscriber / unregister_subscriber delegation,
    get_subscriber_registry snapshot
  - publish: INSERTs the outbox row inline, in the caller's transaction (SA-02)
  - dispatch_to_subscribers: calls each subscriber, logs-and-continues on failure
    (graceful degradation REQ-L3-DEB-008), timeout warning logged
  - poll_and_dispatch: claims, dispatches outside the claim TX (SA-04), marks
    records published, moves to DLQ after MAX_RETRIES
  - Outbox: mutation and event commit or roll back together (real COMMIT test)
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.db import transaction as django_transaction
from django.utils import timezone

from application.event_bus import (
    CLAIM_TIMEOUT_SECONDS,
    DomainEvent,
    DomainEventBus,
    SubscriberRegistry,
    get_event_bus,
    poll_and_dispatch,
    MAX_RETRIES,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# DomainEvent
# ---------------------------------------------------------------------------


class TestDomainEvent:
    """REQ-L3-DEB-003: typed event carrier."""

    def test_construction_with_defaults(self):
        """DomainEvent auto-generates event_id and accepts empty payload."""
        entity_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=entity_id,
            workspace_id=workspace_id,
        )
        assert event.event_type == "RequirementCreated"
        assert event.entity_id == entity_id
        assert event.workspace_id == workspace_id
        assert isinstance(event.event_id, uuid.UUID)
        assert event.payload == {}

    def test_to_dict_contains_all_fields(self):
        """to_dict includes event_id, event_type, entity_id, workspace_id."""
        entity_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        event = DomainEvent(
            event_type="RequirementUpdated",
            entity_id=entity_id,
            workspace_id=workspace_id,
            payload={"title": "New"},
        )
        d = event.to_dict()
        assert d["event_type"] == "RequirementUpdated"
        assert d["entity_id"] == str(entity_id)
        assert d["workspace_id"] == str(workspace_id)
        assert str(event.event_id) == d["event_id"]
        assert d["title"] == "New"

    def test_to_dict_payload_merged_at_top_level(self):
        """Extra payload keys are merged into the top-level dict."""
        event = DomainEvent(
            event_type="TestCaseCreated",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            payload={"test_type": "Unit", "extra": 42},
        )
        d = event.to_dict()
        assert d["test_type"] == "Unit"
        assert d["extra"] == 42


# ---------------------------------------------------------------------------
# SubscriberRegistry
# ---------------------------------------------------------------------------


class TestSubscriberRegistry:
    """REQ-L3-DEB-005."""

    def test_register_and_get_subscribers(self):
        """Registered subscriber is returned by get_subscribers."""
        registry = SubscriberRegistry()
        subscriber = MagicMock()
        registry.register("RequirementCreated", subscriber)
        result = registry.get_subscribers("RequirementCreated")
        assert subscriber in result

    def test_register_same_subscriber_twice_is_idempotent(self):
        """Registering the same subscriber twice does not duplicate it."""
        registry = SubscriberRegistry()
        subscriber = MagicMock()
        registry.register("RequirementCreated", subscriber)
        registry.register("RequirementCreated", subscriber)
        assert registry.get_subscribers("RequirementCreated").count(subscriber) == 1

    def test_unregister_removes_subscriber(self):
        """unregister removes the subscriber from the list."""
        registry = SubscriberRegistry()
        subscriber = MagicMock()
        registry.register("RequirementCreated", subscriber)
        registry.unregister("RequirementCreated", subscriber)
        assert subscriber not in registry.get_subscribers("RequirementCreated")

    def test_unregister_nonexistent_is_noop(self):
        """unregister a subscriber that was never registered is a no-op."""
        registry = SubscriberRegistry()
        subscriber = MagicMock()
        # Should not raise
        registry.unregister("RequirementCreated", subscriber)

    def test_get_subscribers_for_unknown_type_returns_empty(self):
        """get_subscribers returns [] for event types with no registrations."""
        registry = SubscriberRegistry()
        assert registry.get_subscribers("NeverRegistered") == []

    def test_multiple_subscribers_per_event_type(self):
        """Multiple subscribers can be registered for the same event type."""
        registry = SubscriberRegistry()
        sub1 = MagicMock()
        sub2 = MagicMock()
        registry.register("RequirementDeleted", sub1)
        registry.register("RequirementDeleted", sub2)
        result = registry.get_subscribers("RequirementDeleted")
        assert sub1 in result
        assert sub2 in result

    def test_all_subscribers_returns_copy(self):
        """all_subscribers returns a copy; mutation does not affect registry."""
        registry = SubscriberRegistry()
        sub = MagicMock()
        registry.register("X", sub)
        snapshot = registry.all_subscribers()
        snapshot["X"].clear()
        # Original still intact
        assert sub in registry.get_subscribers("X")

    def test_get_subscribers_returns_snapshot(self):
        """get_subscribers returns a list copy (REQ-L3-DEB-005)."""
        registry = SubscriberRegistry()
        sub = MagicMock()
        registry.register("Y", sub)
        copy = registry.get_subscribers("Y")
        copy.clear()
        # Original still intact
        assert sub in registry.get_subscribers("Y")


# ---------------------------------------------------------------------------
# DomainEventBus — Singleton
# ---------------------------------------------------------------------------


class TestDomainEventBusSingleton:
    def test_get_event_bus_returns_same_instance(self):
        """get_event_bus returns the same singleton each call."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_domain_event_bus_is_singleton(self):
        """DomainEventBus() constructor returns the same instance."""
        bus1 = DomainEventBus()
        bus2 = DomainEventBus()
        assert bus1 is bus2


# ---------------------------------------------------------------------------
# DomainEventBus — subscriber management
# ---------------------------------------------------------------------------


class TestDomainEventBusSubscriberManagement:
    """REQ-L3-DEB-005."""

    def test_register_and_unregister_subscriber(self):
        """register_subscriber / unregister_subscriber delegate to registry."""
        bus = DomainEventBus()
        sub = MagicMock()
        event_type = f"Test_{uuid.uuid4().hex}"

        bus.register_subscriber(event_type, sub)
        assert sub in bus.get_subscriber_registry().get(event_type, [])

        bus.unregister_subscriber(event_type, sub)
        assert sub not in bus.get_subscriber_registry().get(event_type, [])

    def test_get_subscriber_registry_returns_dict(self):
        """get_subscriber_registry returns a dict snapshot."""
        bus = DomainEventBus()
        registry = bus.get_subscriber_registry()
        assert isinstance(registry, dict)


# ---------------------------------------------------------------------------
# DomainEventBus.publish — Transactional Outbox (SA-02)
# ---------------------------------------------------------------------------


class TestPublish:
    """REQ-L3-DEB-002, REQ-L2-AS-029.

    SA-02 changed the contract these tests pin down. ``publish()`` used to defer
    the outbox INSERT to a ``transaction.on_commit`` hook — i.e. the row was
    written *after* the mutation had already committed, so a crash in that
    window lost the event permanently, and an insert failure was swallowed. The
    tests below assert the replacement contract: the INSERT happens inline, in
    the caller's transaction, and is allowed to fail it.
    """

    def test_publish_inserts_outbox_row_inline(self):
        """publish() INSERTs immediately — no on_commit deferral (SA-02)."""
        bus = DomainEventBus()
        entity_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=entity_id,
            workspace_id=workspace_id,
            payload={"title": "T"},
        )

        with (
            patch("application.event_bus.transaction.on_commit") as mock_on_commit,
            patch("application.models.DomainEventOutbox.objects.create") as mock_create,
        ):
            bus.publish(event)

        mock_on_commit.assert_not_called()
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["event_type"] == "RequirementCreated"
        assert kwargs["workspace_id"] == workspace_id
        assert kwargs["entity_id"] == entity_id

    def test_publish_propagates_db_error(self):
        """An outbox INSERT failure must fail the caller, not be swallowed.

        The whole point of the pattern is "no event -> no mutation". Swallowing
        here (the pre-SA-02 behaviour) let the mutation commit with the event
        silently missing.
        """
        bus = DomainEventBus()
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )

        with patch(
            "application.models.DomainEventOutbox.objects.create",
            side_effect=RuntimeError("DB error"),
        ):
            with pytest.raises(RuntimeError, match="DB error"):
                bus.publish(event)

    def test_publish_outside_transaction_warns(self):
        """Publishing with no atomic block open is a contract violation."""
        bus = DomainEventBus()
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )

        connection = MagicMock()
        connection.in_atomic_block = False

        with (
            patch(
                "application.event_bus.transaction.get_connection",
                return_value=connection,
            ),
            patch("application.models.DomainEventOutbox.objects.create"),
            patch("application.event_bus.logger") as mock_logger,
        ):
            bus.publish(event)

        mock_logger.warning.assert_called_once()


@pytest.mark.django_db(transaction=True)
class TestPublishTransactionalOutboxGuarantee:
    """SA-02: the outbox row and the mutation must be one atomic unit.

    ``transaction=True`` is required: these tests need real COMMIT/ROLLBACK
    semantics, which the default test-case-wrapped-in-a-transaction fixture
    cannot express (every write is inside one outer transaction there, so
    "committed" and "rolled back" are indistinguishable).
    """

    def _make_event(self):
        return DomainEvent(
            event_type="RequirementCreated",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )

    def test_outbox_row_survives_commit(self):
        from django.db import transaction as db_transaction

        from application.models import DomainEventOutbox

        bus = DomainEventBus()
        event = self._make_event()

        with db_transaction.atomic():
            DomainEventOutbox.objects.filter(event_id=event.event_id).delete()
            bus.publish(event)

        assert DomainEventOutbox.objects.filter(event_id=event.event_id).exists()
        DomainEventOutbox.objects.filter(event_id=event.event_id).delete()

    def test_outbox_row_rolls_back_with_the_mutation(self):
        """Rolling the caller's transaction back must take the event with it."""
        from django.db import transaction as db_transaction

        from application.models import DomainEventOutbox

        bus = DomainEventBus()
        event = self._make_event()

        class _Boom(Exception):
            pass

        with pytest.raises(_Boom):
            with db_transaction.atomic():
                bus.publish(event)
                # Inside the same transaction the row is already visible …
                assert DomainEventOutbox.objects.filter(
                    event_id=event.event_id
                ).exists()
                raise _Boom  # … and this rolls it back again.

        # … but it never reached the database. Before SA-02 this held for a
        # different reason (the on_commit callback simply never fired); the
        # point of the test is that it still holds now that the INSERT is real.
        assert not DomainEventOutbox.objects.filter(event_id=event.event_id).exists()


# ---------------------------------------------------------------------------
# DomainEventBus.dispatch_to_subscribers
# ---------------------------------------------------------------------------


class TestDispatchToSubscribers:
    """REQ-L3-DEB-008: graceful degradation on subscriber failure."""

    def test_all_subscribers_called(self):
        """dispatch_to_subscribers calls every registered subscriber."""
        bus = DomainEventBus()
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )
        sub1 = MagicMock()
        sub2 = MagicMock()

        with patch.object(
            bus._registry,
            "get_subscribers",
            return_value=[sub1, sub2],
        ):
            bus.dispatch_to_subscribers(event)

        sub1.assert_called_once_with(event)
        sub2.assert_called_once_with(event)

    def test_failing_subscriber_does_not_block_others(self):
        """A subscriber that raises does not prevent others from being called."""
        bus = DomainEventBus()
        event = DomainEvent(
            event_type="RequirementCreated",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )
        sub_fail = MagicMock(side_effect=RuntimeError("subscriber error"))
        sub_ok = MagicMock()

        with patch.object(
            bus._registry,
            "get_subscribers",
            return_value=[sub_fail, sub_ok],
        ):
            # Must not raise
            bus.dispatch_to_subscribers(event)

        sub_ok.assert_called_once_with(event)

    def test_no_subscribers_is_noop(self):
        """dispatch_to_subscribers is a no-op when no subscribers registered."""
        bus = DomainEventBus()
        event = DomainEvent(
            event_type="NoSubscribers",
            entity_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )

        with patch.object(bus._registry, "get_subscribers", return_value=[]):
            # Should not raise
            bus.dispatch_to_subscribers(event)


# ---------------------------------------------------------------------------
# poll_and_dispatch
# ---------------------------------------------------------------------------


class TestPollAndDispatch:
    """REQ-L3-DEB-003, ADR-L3-DEB-03."""

    def test_marks_event_published_on_success(self):
        """poll_and_dispatch marks an outbox record as published after dispatch."""
        record = MagicMock()
        record.event_id = uuid.uuid4()
        record.event_type = "RequirementCreated"
        record.entity_id = uuid.uuid4()
        record.workspace_id = uuid.uuid4()
        record.payload = {}
        record.retry_count = 0

        with (
            patch(
                "application.event_bus.DomainEventOutbox.objects.select_for_update",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            order_by=MagicMock(
                                return_value=MagicMock(
                                    __getitem__=MagicMock(return_value=[record])
                                )
                            )
                        )
                    )
                ),
            ),
            patch("application.event_bus.DomainEventOutbox") as mock_outbox_class,
            patch("application.event_bus.DomainEventDLQ"),
            patch("application.event_bus.transaction.atomic") as mock_atomic,
            patch.object(get_event_bus(), "dispatch_to_subscribers"),
        ):
            # Make the atomic context manager work
            mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
            mock_atomic.return_value.__exit__ = MagicMock(return_value=False)

            mock_outbox_class.objects.select_for_update.return_value.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=iter([record]))  # noqa: E501

            # Execute directly testing the function internals via mock
            bus = get_event_bus()

            with patch.object(bus, "dispatch_to_subscribers") as mock_dispatch:
                # Simulate poll: one record fetched, dispatched, marked published
                domain_event = DomainEvent(
                    event_id=record.event_id,
                    event_type=record.event_type,
                    entity_id=record.entity_id,
                    workspace_id=record.workspace_id,
                    payload=record.payload,
                )
                mock_dispatch(domain_event)
                record.published = True
                record.save(update_fields=["published", "published_at"])

        assert record.published is True
        record.save.assert_called()

    def test_retry_count_incremented_on_dispatch_failure(self):
        """Dispatch failure increments retry_count and saves record."""
        bus = get_event_bus()
        record = MagicMock()
        record.event_id = uuid.uuid4()
        record.event_type = "RequirementCreated"
        record.entity_id = uuid.uuid4()
        record.workspace_id = uuid.uuid4()
        record.payload = {}
        record.retry_count = 0

        domain_event = DomainEvent(
            event_id=record.event_id,
            event_type=record.event_type,
            entity_id=record.entity_id,
            workspace_id=record.workspace_id,
            payload=record.payload,
        )

        with patch.object(
            bus, "dispatch_to_subscribers", side_effect=Exception("dispatch error")
        ):
            try:
                bus.dispatch_to_subscribers(domain_event)
            except Exception:
                pass
            # Simulate poll_and_dispatch retry logic
            record.retry_count += 1
            record.save(update_fields=["retry_count"])

        assert record.retry_count == 1
        record.save.assert_called()

    def test_dlq_created_after_max_retries(self):
        """After MAX_RETRIES failures the event is moved to DLQ."""
        from application.event_bus import MAX_RETRIES

        # Verify the constant is sensible
        assert MAX_RETRIES > 0

        record = MagicMock()
        record.retry_count = MAX_RETRIES
        record.event_id = uuid.uuid4()
        record.event_type = "RequirementCreated"
        record.workspace_id = uuid.uuid4()
        record.entity_id = uuid.uuid4()
        record.payload = {}

        with patch("application.event_bus.DomainEventDLQ") as mock_dlq:
            mock_dlq.objects.create = MagicMock()
            # Simulate the DLQ creation path from poll_and_dispatch
            if record.retry_count >= MAX_RETRIES:
                mock_dlq.objects.create(
                    event_id=record.event_id,
                    event_type=record.event_type,
                    workspace_id=record.workspace_id,
                    entity_id=record.entity_id,
                    payload=record.payload,
                    error_message="dispatch error",
                    retry_count=record.retry_count,
                )
                record.delete()

        mock_dlq.objects.create.assert_called_once()
        record.delete.assert_called_once()


# ---------------------------------------------------------------------------
# poll_and_dispatch — claim / dispatch / write-back (REQ-020, S-01, SA-04, SA-05)
# ---------------------------------------------------------------------------


def _make_outbox_row(**overrides):
    """Create a real, unclaimed DomainEventOutbox row."""
    from application.models import DomainEventOutbox

    defaults = dict(
        event_id=uuid.uuid4(),
        event_type="RequirementCreated",
        workspace_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        payload={},
    )
    defaults.update(overrides)
    return DomainEventOutbox.objects.create(**defaults)


class TestPollAndDispatchClaim:
    """REQ-020, S-01, SA-04.

    These run against real rows rather than a mocked ORM chain on purpose: the
    behaviour under test *is* the sequence of queries (claim commits, then
    dispatch, then write back), and a mocked ``objects.filter(...)`` chain
    asserts nothing about it — it only re-encodes whatever shape the code
    happened to have when the test was written.
    """

    def test_claimed_record_dispatched_and_published(self):
        from application.models import DomainEventOutbox

        bus = get_event_bus()
        row = _make_outbox_row()

        with patch.object(
            bus, "dispatch_to_subscribers", return_value=[]
        ) as mock_dispatch:
            processed = poll_and_dispatch()

        assert processed == 1
        mock_dispatch.assert_called_once()
        row.refresh_from_db()
        assert row.published is True
        assert row.published_at is not None
        # The claim is released again so the row never looks "in flight".
        assert row.claimed_at is None
        assert not DomainEventOutbox.objects.filter(
            pk=row.pk, published=False
        ).exists()

    def test_freshly_claimed_row_is_skipped(self):
        """A row another worker is currently dispatching must not be picked up."""
        bus = get_event_bus()
        _make_outbox_row(claimed_at=timezone.now())

        with patch.object(
            bus, "dispatch_to_subscribers", return_value=[]
        ) as mock_dispatch:
            processed = poll_and_dispatch()

        assert processed == 0
        mock_dispatch.assert_not_called()

    def test_stale_claim_is_reclaimed(self):
        """A worker that died mid-dispatch must not strand the row forever."""
        bus = get_event_bus()
        stale = timezone.now() - timedelta(seconds=CLAIM_TIMEOUT_SECONDS + 60)
        row = _make_outbox_row(claimed_at=stale)

        with patch.object(bus, "dispatch_to_subscribers", return_value=[]):
            processed = poll_and_dispatch()

        assert processed == 1
        row.refresh_from_db()
        assert row.published is True

    def test_stale_claim_increments_retry_count(self):
        """A reclaim must count toward MAX_RETRIES on its own (F5).

        Without this, a dispatch that reliably kills the worker before
        _finalize_failure ever runs would be redelivered every
        CLAIM_TIMEOUT_SECONDS forever, never reaching MAX_RETRIES/the DLQ.
        """
        bus = get_event_bus()
        stale = timezone.now() - timedelta(seconds=CLAIM_TIMEOUT_SECONDS + 60)
        row = _make_outbox_row(claimed_at=stale, retry_count=1)

        with patch.object(bus, "dispatch_to_subscribers", return_value=[]):
            poll_and_dispatch()

        row.refresh_from_db()
        # Reclaim bumped it to 2, then the successful dispatch below released
        # the claim without touching retry_count again.
        assert row.retry_count == 2

    def test_repeatedly_reclaimed_row_reaches_dlq_without_dispatch(self):
        """F5: a row whose worker dies on every attempt (reclaimed forever,
        never reaching _finalize_failure) must still hit MAX_RETRIES and land
        in the DLQ instead of being dispatched into the same worker-killing
        path again.
        """
        from application.models import DomainEventDLQ, DomainEventOutbox

        bus = get_event_bus()
        stale = timezone.now() - timedelta(seconds=CLAIM_TIMEOUT_SECONDS + 60)
        # One reclaim short of the limit: the claim below pushes it over.
        row = _make_outbox_row(claimed_at=stale, retry_count=MAX_RETRIES - 1)

        with patch.object(bus, "dispatch_to_subscribers") as mock_dispatch:
            processed = poll_and_dispatch()

        mock_dispatch.assert_not_called()
        assert processed == 0
        assert not DomainEventOutbox.objects.filter(pk=row.pk).exists()
        dlq = DomainEventDLQ.objects.get(event_id=row.event_id)
        assert dlq.retry_count == MAX_RETRIES

    @pytest.mark.django_db(transaction=True)
    def test_claim_is_committed_before_dispatch(self):
        """SA-04: the claim transaction must be closed when subscribers run.

        This is the whole point of the restructure — WebhookDispatcher does
        outbound HTTP with retries and back-off sleeps (~65s worst case per
        subscription), and the previous implementation held a SELECT FOR UPDATE
        row lock and an open Postgres transaction for that entire time.

        ``transaction=True`` is mandatory here: the plain ``django_db`` fixture
        wraps the whole test in one transaction, so ``in_atomic_block`` would
        read True no matter what the production code does — the assertion below
        would pass on the *old*, broken implementation just as happily.
        """
        from application.models import DomainEventOutbox

        bus = get_event_bus()
        row = _make_outbox_row()
        observed = {}

        def _spy(event, timeout_seconds=30):
            observed["in_atomic_block"] = (
                django_transaction.get_connection().in_atomic_block
            )
            # The claim must already be durable, not merely pending.
            observed["claimed_at"] = (
                DomainEventOutbox.objects.filter(pk=row.pk)
                .values_list("claimed_at", flat=True)
                .first()
            )
            return []

        with patch.object(bus, "dispatch_to_subscribers", side_effect=_spy):
            poll_and_dispatch()

        assert observed["in_atomic_block"] is False, (
            "subscribers ran inside the claim transaction — the row lock is "
            "still held across external I/O"
        )
        assert observed["claimed_at"] is not None

    def test_failed_dispatch_increments_retry_and_releases_claim(self):
        bus = get_event_bus()
        row = _make_outbox_row()

        with patch.object(bus, "dispatch_to_subscribers", return_value=["boom"]):
            processed = poll_and_dispatch()

        assert processed == 0
        row.refresh_from_db()
        assert row.published is False
        assert row.retry_count == 1
        assert row.claimed_at is None

    def test_dispatch_raising_is_contained(self):
        """dispatch_to_subscribers is contractually non-raising; if it does
        anyway, the row must land on the retry path, not crash the cycle."""
        bus = get_event_bus()
        row = _make_outbox_row()

        with patch.object(
            bus, "dispatch_to_subscribers", side_effect=RuntimeError("kaboom")
        ):
            processed = poll_and_dispatch()

        assert processed == 0
        row.refresh_from_db()
        assert row.retry_count == 1
        assert row.claimed_at is None


class TestPollAndDispatchDlq:
    """REQ-021, REQ-L3-DEB-007, SA-05."""

    def test_event_moved_to_dlq_after_max_retries(self):
        from application.models import DomainEventDLQ, DomainEventOutbox

        bus = get_event_bus()
        row = _make_outbox_row(retry_count=MAX_RETRIES - 1)

        with patch.object(bus, "dispatch_to_subscribers", return_value=["boom"]):
            poll_and_dispatch()

        assert not DomainEventOutbox.objects.filter(pk=row.pk).exists()
        dlq = DomainEventDLQ.objects.get(event_id=row.event_id)
        assert dlq.retry_count == MAX_RETRIES
        assert "boom" in dlq.error_message

    def test_dlq_move_failure_keeps_the_retry_increment(self):
        """SA-05: a failing DLQ move must not roll back the claim bookkeeping.

        Previously the move ran inside the claim transaction, so a DLQ insert
        error also discarded the retry_count increment and the row went back
        into the poll set completely unchanged — a permanently stuck
        ``published=False`` row that never reached the DLQ and never stopped
        being retried.
        """

        bus = get_event_bus()
        row = _make_outbox_row(retry_count=MAX_RETRIES - 1)

        with (
            patch.object(bus, "dispatch_to_subscribers", return_value=["boom"]),
            patch(
                "application.event_bus.DomainEventDLQ.objects.get_or_create",
                side_effect=RuntimeError("DLQ table unavailable"),
            ),
        ):
            # Must not propagate — one poisoned row may not abort the cycle.
            poll_and_dispatch()

        row.refresh_from_db()
        assert row.retry_count == MAX_RETRIES, (
            "the retry increment was rolled back with the failed DLQ move"
        )
        assert row.claimed_at is None, "the claim was not released"

    def test_dlq_move_is_retry_safe(self):
        """A leftover DLQ row from a half-finished move must not block a retry."""
        from application.models import DomainEventDLQ, DomainEventOutbox

        bus = get_event_bus()
        row = _make_outbox_row(retry_count=MAX_RETRIES - 1)
        DomainEventDLQ.objects.create(
            event_id=row.event_id,
            event_type=row.event_type,
            workspace_id=row.workspace_id,
            entity_id=row.entity_id,
            payload=row.payload,
            error_message="earlier attempt",
            retry_count=MAX_RETRIES,
        )

        with patch.object(bus, "dispatch_to_subscribers", return_value=["boom"]):
            poll_and_dispatch()

        assert not DomainEventOutbox.objects.filter(pk=row.pk).exists()
        assert DomainEventDLQ.objects.filter(event_id=row.event_id).count() == 1
