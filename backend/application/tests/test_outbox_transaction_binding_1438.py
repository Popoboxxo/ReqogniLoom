"""Regression tests for issue #1438 — the outbox row must be bound to its mutation.

Issue #1438: ``manage.py seed_toothbrush`` logged 1879 warnings of the shape

    DomainEventBus: publish() called outside a transaction (event <uuid>
    type=TraceLinkCreated) — the outbox row is not atomically bound to any
    mutation

1879 is exactly the number of TraceLinks the seed creates. Two candidate
causes were on the table:

* **Case 2 — a broken detection.** ``publish()`` might have been looking at
  the wrong flag (``ATOMIC_REQUESTS``?), so it reported "outside a
  transaction" even for publishes that *were* inside one. Ruled out here by
  :class:`TestCase2RuledOut`: publishing inside a real ``atomic()`` block
  must not warn. The detection is correct.

* **Case 1 — a missing transaction.** ``TraceLinkService.create_trace_link``
  was the only event-producing service method without an
  ``@atomic_transaction`` wrapper, so its outbox row was autocommitted on
  its own. CONFIRMED here by :class:`TestCase1Confirmed`: the link creation
  must publish inside a transaction, and the outbox row must share the
  link's fate (:class:`TestAtomicity`).

The remaining classes pin the observability the fix introduced: a counter
instead of a log flood (:class:`TestCounter`, :class:`TestNoLogFlood`) and
the operator-visible surface in the readiness payload
(:class:`TestHealthAdvisory`).

Every test that has to observe a *real* transaction uses
``django_db(transaction=True)``: the default fixture wraps the whole test in
one transaction, so ``in_atomic_block`` would read True no matter what the
production code does and the assertion would pass vacuously.
"""
from __future__ import annotations

import logging
import uuid
from unittest.mock import MagicMock, call, patch

import pytest
from django.db import transaction as db_transaction
from django.test import override_settings

from application import event_bus, event_bus_metrics
from application.event_bus import DomainEvent, DomainEventBus
from application.models import DomainEventOutbox
from application.trace_link_service import TraceLinkService
from persistence.models import TraceLink
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

pytestmark = pytest.mark.django_db

#: Substring every "unbound publish" log line carries. The bus keeps this
#: wording so existing log greps keep working.
UNBOUND_MARKER = "publish() called outside a transaction"


def _unbound_records(caplog) -> list:
    """Return the captured records that report an unbound publish."""
    return [r for r in caplog.records if UNBOUND_MARKER in r.getMessage()]


def _make_event(event_type: str = "RequirementCreated") -> DomainEvent:
    return DomainEvent(
        event_type=event_type,
        entity_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
    )


@pytest.fixture(autouse=True)
def _clean_unbound_publish_state():
    """Every test starts with a clean counter and a clean throttle state.

    The throttle state is process-local (the bus warns once per process), so
    without this reset the "first warning" assertions would depend on the
    order in which the suite happened to run.
    """
    event_bus_metrics.reset_unbound_publish_counters()
    event_bus_metrics.reset_unbound_publish_state()
    yield
    event_bus_metrics.reset_unbound_publish_counters()
    event_bus_metrics.reset_unbound_publish_state()


@pytest.fixture
def tenant_workspace():
    """An active tenant with a provisioned workspace and an editor context."""
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        yield tenant, workspace, ctx


@pytest.fixture
def requirements(tenant_workspace):
    """Two requirements in the fixture workspace (link endpoints)."""
    _tenant, workspace, _ctx = tenant_workspace
    return [
        make_requirement(workspace, title="R-0"),
        make_requirement(workspace, title="R-1"),
    ]


# ---------------------------------------------------------------------------
# Case 2 — ruled out: the detection itself is correct
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestCase2RuledOut:
    """Publishing INSIDE a real transaction must not be reported."""

    def test_publish_inside_atomic_block_is_not_reported(self, caplog):
        caplog.set_level(logging.WARNING, logger="application.event_bus")
        bus = DomainEventBus()
        event = _make_event()

        before = event_bus_metrics.unbound_publish_count()

        with db_transaction.atomic():
            bus.publish(event)

        assert _unbound_records(caplog) == [], (
            "a publish inside a real atomic() block was reported as unbound — "
            "the detection itself is broken"
        )
        assert event_bus_metrics.unbound_publish_count() == before, (
            "a publish inside a real atomic() block was counted as unbound"
        )

    def test_publish_outside_atomic_block_is_reported(self, caplog):
        """The counterpart: outside a transaction the condition IS reported.

        Without this, the test above would also pass on a bus that never
        reports anything.
        """
        caplog.set_level(logging.WARNING, logger="application.event_bus")
        bus = DomainEventBus()
        event = _make_event()

        before = event_bus_metrics.unbound_publish_count()

        bus.publish(event)  # no atomic() block — the test body is not one

        assert len(_unbound_records(caplog)) == 1
        assert event_bus_metrics.unbound_publish_count() == before + 1


# ---------------------------------------------------------------------------
# Case 1 — confirmed: the link creation must publish inside a transaction
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestCase1Confirmed:
    """``create_trace_link`` must publish inside a transaction."""

    def test_link_creation_publishes_inside_a_transaction(
        self, caplog, tenant_workspace, requirements
    ):
        caplog.set_level(logging.WARNING, logger="application.event_bus")
        _tenant, _workspace, ctx = tenant_workspace

        before = event_bus_metrics.unbound_publish_count()

        link = TraceLinkService().create_trace_link(
            source_id=requirements[0].id,
            target_id=requirements[1].id,
            link_type="derives-from",
            ctx=ctx,
        )

        assert link is not None
        assert _unbound_records(caplog) == [], (
            "create_trace_link published its domain event outside a "
            "transaction — the outbox row is not bound to the link (#1438)"
        )
        assert event_bus_metrics.unbound_publish_count() == before, (
            "create_trace_link published its domain event outside a "
            "transaction — the condition was counted"
        )
        assert DomainEventOutbox.objects.filter(
            event_type="TraceLinkCreated",
            entity_id=link.id,
        ).exists(), "create_trace_link did not write a TraceLinkCreated outbox row"


# ---------------------------------------------------------------------------
# Atomicity — the outbox row and the link share one fate
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestAtomicity:
    """SA-02: a rollback of the mutation must take the event with it."""

    def test_link_and_outbox_row_roll_back_together(
        self, tenant_workspace, requirements
    ):
        _tenant, _workspace, ctx = tenant_workspace

        class _Boom(Exception):
            pass

        link_id = None
        with pytest.raises(_Boom), db_transaction.atomic():
            link = TraceLinkService().create_trace_link(
                source_id=requirements[0].id,
                target_id=requirements[1].id,
                link_type="derives-from",
                ctx=ctx,
            )
            link_id = link.id
            # The outbox row is already visible inside the block …
            assert DomainEventOutbox.objects.filter(
                event_type="TraceLinkCreated",
                entity_id=link.id,
            ).exists()
            raise _Boom  # … and this rolls both of them back.

        assert link_id is not None
        assert not TraceLink.objects.filter(id=link_id).exists(), (
            "the trace link survived the rollback of its transaction"
        )
        assert not DomainEventOutbox.objects.filter(
            event_type="TraceLinkCreated",
            entity_id=link_id,
        ).exists(), (
            "the outbox row survived the rollback of the link — the event is "
            "not atomic with its mutation"
        )

    def test_link_and_outbox_row_commit_together(
        self, tenant_workspace, requirements
    ):
        """The positive counterpart: a commit keeps both."""
        _tenant, _workspace, ctx = tenant_workspace

        with db_transaction.atomic():
            link = TraceLinkService().create_trace_link(
                source_id=requirements[0].id,
                target_id=requirements[1].id,
                link_type="derives-from",
                ctx=ctx,
            )

        assert TraceLink.objects.filter(id=link.id).exists()
        assert DomainEventOutbox.objects.filter(
            event_type="TraceLinkCreated",
            entity_id=link.id,
        ).exists()


# ---------------------------------------------------------------------------
# The counter (application.event_bus_metrics)
# ---------------------------------------------------------------------------


class TestCounter:
    """The counter replaces the per-occurrence warning flood."""

    def test_increment_returns_the_running_total(self):
        assert event_bus_metrics.unbound_publish_count() == 0
        assert event_bus_metrics.increment_unbound_publish("TraceLinkCreated") == 1
        assert event_bus_metrics.increment_unbound_publish("TraceLinkCreated") == 2
        assert event_bus_metrics.increment_unbound_publish("RequirementCreated") == 3
        assert event_bus_metrics.unbound_publish_count() == 3

    def test_per_type_breakdown(self):
        event_bus_metrics.increment_unbound_publish("TraceLinkCreated")
        event_bus_metrics.increment_unbound_publish("TraceLinkCreated")
        event_bus_metrics.increment_unbound_publish("RequirementCreated")

        assert event_bus_metrics.unbound_publish_counts_by_type() == {
            "TraceLinkCreated": 2,
            "RequirementCreated": 1,
        }

    def test_reset_clears_total_and_breakdown(self):
        event_bus_metrics.increment_unbound_publish("TraceLinkCreated")

        event_bus_metrics.reset_unbound_publish_counters()

        assert event_bus_metrics.unbound_publish_count() == 0
        assert event_bus_metrics.unbound_publish_counts_by_type() == {}

    def test_increment_fails_open_when_the_cache_is_down(self):
        """A cache outage must not break the producer."""
        with patch("application.event_bus_metrics.cache") as mock_cache:
            mock_cache.add.side_effect = RuntimeError("cache down")
            assert (
                event_bus_metrics.increment_unbound_publish("TraceLinkCreated") == 0
            )

    def test_reads_fail_open_when_the_cache_is_down(self):
        with patch("application.event_bus_metrics.cache") as mock_cache:
            mock_cache.get.side_effect = RuntimeError("cache down")
            assert event_bus_metrics.unbound_publish_count() == 0
            assert event_bus_metrics.unbound_publish_counts_by_type() == {}

    def test_reset_fails_open_when_the_cache_is_down(self):
        with patch("application.event_bus_metrics.cache") as mock_cache:
            mock_cache.get.side_effect = RuntimeError("cache down")
            event_bus_metrics.reset_unbound_publish_counters()  # must not raise


# ---------------------------------------------------------------------------
# No log flood
# ---------------------------------------------------------------------------


class TestNoLogFlood:
    """N unbound publishes must not produce N warnings (#1438)."""

    @staticmethod
    def _publish_unbound(count: int, event_type: str = "TraceLinkCreated") -> None:
        """Publish *count* events while pretending no transaction is open."""
        bus = DomainEventBus()
        connection = MagicMock()
        connection.in_atomic_block = False
        with (
            patch(
                "application.event_bus.transaction.get_connection",
                return_value=connection,
            ),
            patch("application.models.DomainEventOutbox.objects.create"),
        ):
            for _ in range(count):
                bus.publish(_make_event(event_type))

    def test_many_unbound_publishes_produce_at_most_one_warning(self, caplog):
        caplog.set_level(logging.WARNING, logger="application.event_bus")

        count = 50
        self._publish_unbound(count)

        records = _unbound_records(caplog)
        assert len(records) <= 1, (
            f"{len(records)} warnings for {count} unbound publishes — the "
            "flood is back"
        )
        assert len(records) == 1, (
            "the situation was not reported at all — the throttle must not "
            "silence the first occurrence"
        )
        assert event_bus_metrics.unbound_publish_count() == count
        assert event_bus_metrics.unbound_publish_counts_by_type() == {
            "TraceLinkCreated": count
        }

    def test_the_first_warning_keeps_the_original_wording(self, caplog):
        caplog.set_level(logging.WARNING, logger="application.event_bus")
        bus = DomainEventBus()
        event = _make_event("TraceLinkCreated")
        connection = MagicMock()
        connection.in_atomic_block = False

        with (
            patch(
                "application.event_bus.transaction.get_connection",
                return_value=connection,
            ),
            patch("application.models.DomainEventOutbox.objects.create"),
        ):
            bus.publish(event)

        records = _unbound_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert str(event.event_id) in message
        assert "TraceLinkCreated" in message
        assert "not atomically bound to any mutation" in message

    def test_a_periodic_summary_replaces_the_flood(self, caplog):
        """Every Nth occurrence logs a compact summary instead of the full text."""
        caplog.set_level(logging.WARNING, logger="application.event_bus")

        with override_settings(OUTBOX_UNBOUND_WARN_SUMMARY_INTERVAL=5):
            self._publish_unbound(5)

        summaries = [
            r
            for r in caplog.records
            if "outbox_unbound_publish_count" in r.getMessage()
            and "events" in r.getMessage()
        ]
        assert len(summaries) == 1, (
            "the periodic summary did not fire at the configured interval"
        )
        message = summaries[0].getMessage()
        assert "5 events" in message
        assert "TraceLinkCreated=5" in message
        assert "outbox_unbound_publish_count=5" in message
        # The window is part of the line: the count is bounded by it, so a
        # reader must be able to see how long a non-zero count stays relevant.
        assert (
            f"outbox_unbound_publish_window_seconds="
            f"{event_bus_metrics.counter_window_seconds()}" in message
        )


# ---------------------------------------------------------------------------
# Health advisory
# ---------------------------------------------------------------------------


class TestHealthAdvisory:
    """The counter is operator-visible on the readiness endpoint (ADR-010)."""

    def test_advisory_carries_the_counter(self):
        from reqogniloom.health import _collect_advisory

        event_bus_metrics.increment_unbound_publish("TraceLinkCreated")
        event_bus_metrics.increment_unbound_publish("TraceLinkCreated")

        advisory: dict[str, str] = {}
        warnings: list[str] = []
        _collect_advisory(advisory, warnings, db_ok=False)

        assert advisory["outbox_unbound_publishes"] == "2"
        assert any("outbox_unbound_publish_count" in w for w in warnings), (
            "a non-zero counter must produce an operator-visible warning"
        )

    def test_advisory_reports_zero_when_healthy(self):
        from reqogniloom.health import _collect_advisory

        advisory: dict[str, str] = {}
        warnings: list[str] = []
        _collect_advisory(advisory, warnings, db_ok=False)

        assert advisory["outbox_unbound_publishes"] == "0"
        assert not any("outbox_unbound_publish_count" in w for w in warnings)

    def test_the_health_check_never_crashes_on_a_broken_counter(self):
        from reqogniloom.health import _collect_advisory

        advisory: dict[str, str] = {}
        warnings: list[str] = []
        with patch(
            "application.event_bus_metrics.unbound_publish_count",
            side_effect=RuntimeError("counter exploded"),
        ):
            _collect_advisory(advisory, warnings, db_ok=False)

        assert warnings, "a broken counter must be reported, not swallowed"

    def test_advisory_carries_the_window(self):
        """The count is bounded by the window, so the window travels with it."""
        from reqogniloom.health import _collect_advisory

        advisory: dict[str, str] = {}
        warnings: list[str] = []
        _collect_advisory(advisory, warnings, db_ok=False)

        assert advisory["outbox_unbound_publish_window_seconds"] == str(
            event_bus_metrics.counter_window_seconds()
        )

    def test_the_warning_text_says_what_the_number_means(self):
        """The warning must not imply a count that can only grow."""
        from reqogniloom.health import _collect_advisory

        event_bus_metrics.increment_unbound_publish("TraceLinkCreated")

        advisory: dict[str, str] = {}
        warnings: list[str] = []
        _collect_advisory(advisory, warnings, db_ok=False)

        assert warnings
        text = " ".join(warnings)
        assert "outbox_unbound_publish_count" in text
        assert "outbox_unbound_publish_window_seconds" in text
        assert "within the last" in text
        assert "not a running total that can only grow" in text.lower()

    def test_the_window_is_zero_when_the_decay_is_disabled(self):
        from reqogniloom.health import _collect_advisory

        advisory: dict[str, str] = {}
        warnings: list[str] = []
        with override_settings(OUTBOX_UNBOUND_COUNTER_TTL=0):
            _collect_advisory(advisory, warnings, db_ok=False)

        assert advisory["outbox_unbound_publish_window_seconds"] == "0"


# ---------------------------------------------------------------------------
# The decay window of the counter (GAP: the readiness signal must be able to
# clear itself again)
# ---------------------------------------------------------------------------


class TestCounterWindow:
    """The counter lives in a bounded window, not forever.

    A monotonic counter can never clear, so ONE pre-fix publish would keep
    ``/health/ready`` at ``status: "warning"`` forever — alert fatigue, and
    an operator can no longer tell "broken right now" from "broken once,
    weeks ago". The window makes a resolved defect clear the signal by
    itself.
    """

    def test_the_window_is_read_from_the_setting(self):
        assert event_bus_metrics.counter_window_seconds() == 86400

        with override_settings(OUTBOX_UNBOUND_COUNTER_TTL=120):
            assert event_bus_metrics.counter_window_seconds() == 120

    def test_window_zero_disables_the_decay(self):
        with override_settings(OUTBOX_UNBOUND_COUNTER_TTL=0):
            assert event_bus_metrics.counter_window_seconds() == 0

    def test_the_counter_keys_are_created_with_the_window_ttl(self):
        """``cache.add`` carries the TTL — it creates the key that starts the window."""
        with patch("application.event_bus_metrics.cache") as mock_cache:
            mock_cache.get.return_value = []
            mock_cache.incr.side_effect = [1, 1]

            event_bus_metrics.increment_unbound_publish("TraceLinkCreated")

        assert mock_cache.add.call_args_list == [
            call(event_bus_metrics.TOTAL_KEY, 0, timeout=86400),
            call(
                f"{event_bus_metrics.TYPE_KEY_PREFIX}TraceLinkCreated",
                0,
                timeout=86400,
            ),
        ]

    def test_the_type_registry_gets_the_window_ttl(self):
        with patch("application.event_bus_metrics.cache") as mock_cache:
            mock_cache.get.return_value = []
            mock_cache.incr.side_effect = [1, 1]

            event_bus_metrics.increment_unbound_publish("TraceLinkCreated")

        assert mock_cache.set.call_args_list == [
            call(
                event_bus_metrics.TYPE_REGISTRY_KEY,
                ["TraceLinkCreated"],
                timeout=86400,
            )
        ]

    def test_the_value_error_recovery_uses_the_same_ttl(self):
        """The key can vanish between ``add`` and ``incr`` — the recovery must
        not silently fall back to "never expires"."""
        with patch("application.event_bus_metrics.cache") as mock_cache:
            mock_cache.get.return_value = []
            mock_cache.incr.side_effect = ValueError("Key not found")

            event_bus_metrics.increment_unbound_publish("TraceLinkCreated")

        assert mock_cache.set.call_args_list[0] == call(
            event_bus_metrics.TOTAL_KEY, 1, timeout=86400
        )

    def test_a_zero_window_means_no_decay(self):
        with (
            patch("application.event_bus_metrics.cache") as mock_cache,
            override_settings(OUTBOX_UNBOUND_COUNTER_TTL=0),
        ):
            mock_cache.get.return_value = []
            mock_cache.incr.side_effect = [1, 1]

            event_bus_metrics.increment_unbound_publish("TraceLinkCreated")

        assert mock_cache.add.call_args_list == [
            call(event_bus_metrics.TOTAL_KEY, 0, timeout=None),
            call(
                f"{event_bus_metrics.TYPE_KEY_PREFIX}TraceLinkCreated",
                0,
                timeout=None,
            ),
        ]

    def test_the_cache_key_is_named_after_the_count(self):
        """``...:total`` would be a lie now that the count is windowed."""
        assert event_bus_metrics.TOTAL_KEY == "outbox:unbound_publish:count"
        assert "total" not in event_bus_metrics.TOTAL_KEY


# ---------------------------------------------------------------------------
# Seed smoke — the path the seeder actually uses
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestSeedSmoke:
    """The seed's own path must not produce an unbound publish.

    ``manage.py seed_toothbrush`` creates its requirements through
    ``RequirementService.create_requirement`` and then links them through
    ``TraceLinkService.create_trace_link`` — the exact combination that
    produced the 1879 warnings of issue #1438. This test exercises that
    combination (a full seed run is a multi-minute, multi-thousand-row job
    and does not belong in the unit suite).
    """

    def test_requirement_plus_link_path_is_fully_bound(
        self, caplog, tenant_workspace
    ):
        from application.requirement_service import RequirementService

        caplog.set_level(logging.WARNING, logger="application.event_bus")
        _tenant, workspace, ctx = tenant_workspace

        before = event_bus_metrics.unbound_publish_count()

        parent = RequirementService().create_requirement(
            workspace_id=workspace.id,
            title="Parent requirement",
            ctx=ctx,
        )
        child = RequirementService().create_requirement(
            workspace_id=workspace.id,
            title="Child requirement",
            ctx=ctx,
        )
        link = TraceLinkService().create_trace_link(
            source_id=child.artifact_id,
            target_id=parent.artifact_id,
            link_type="derives-from",
            ctx=ctx,
        )

        assert _unbound_records(caplog) == [], (
            "the seed's requirement+link path published outside a "
            "transaction (#1438)"
        )
        assert event_bus_metrics.unbound_publish_count() == before

        assert (
            DomainEventOutbox.objects.filter(
                event_type="TraceLinkCreated",
                entity_id=link.id,
            ).count()
            == 1
        )
        assert (
            DomainEventOutbox.objects.filter(
                event_type="RequirementCreated",
                entity_id=parent.id,
            ).count()
            == 1
        )


# ---------------------------------------------------------------------------
# The on-commit dispatch nudge (OUTBOX_DISPATCH_ON_COMMIT, default OFF)
# ---------------------------------------------------------------------------


@pytest.fixture
def nudge_flag_reset():
    """Clear the nudge's rate-limiter flag around every test.

    The flag is a cache key shared by the whole process, so a leftover from an
    earlier test would silently suppress the nudge and make the assertions
    pass for the wrong reason.
    """
    from django.core.cache import cache

    from application.event_bus import OUTBOX_DISPATCH_NUDGE_KEY

    cache.delete(OUTBOX_DISPATCH_NUDGE_KEY)
    yield
    cache.delete(OUTBOX_DISPATCH_NUDGE_KEY)


@pytest.fixture
def on_commit_spy():
    """Record every module-level ``transaction.on_commit`` registration.

    The real function is still called, so the hook really fires on commit —
    the spy only makes the REGISTRATION observable, which is what the nudge
    contract is about.
    """
    calls: list = []
    real_on_commit = db_transaction.on_commit

    def _spy(func, using=None, robust=False):
        calls.append(func)
        return real_on_commit(func, using=using, robust=robust)

    with patch.object(event_bus.transaction, "on_commit", _spy):
        yield calls


@pytest.fixture
def dispatch_task():
    """Replace the Celery task so the poller never runs inside a test.

    The nudge calls ``application.tasks.dispatch_outbox_events.delay()``. With
    ``CELERY_TASK_ALWAYS_EAGER=True`` (the test settings) an unmocked call
    would run the poller INLINE inside the commit hook. The whole task object
    is replaced, so nothing of the real worker is touched.
    """
    with patch("application.tasks.dispatch_outbox_events") as task:
        yield task


@pytest.mark.django_db(transaction=True)
class TestDispatchNudge:
    """The on-commit dispatch nudge is a latency optimisation, not a mechanism.

    The outbox INSERT stays inline in the mutation's transaction (SA-02) and
    the subscriber dispatch already happens strictly after commit (SA-04), so
    the nudge only shortens the ≤5 s beat interval. It is therefore OFF by
    default and must never influence the atomicity of a publish.
    """

    def test_the_shipped_default_is_off(self):
        from reqogniloom import settings as prod_settings

        assert prod_settings.OUTBOX_DISPATCH_ON_COMMIT is False

    def test_default_off_registers_no_hook(
        self, on_commit_spy, dispatch_task, nudge_flag_reset
    ):
        with override_settings(OUTBOX_DISPATCH_ON_COMMIT=False):
            bus = DomainEventBus()
            with db_transaction.atomic():
                bus.publish(_make_event())

        assert on_commit_spy == [], (
            "the dispatch nudge registered an on_commit hook while it is off"
        )
        dispatch_task.delay.assert_not_called()

    def test_enabled_inside_a_transaction_registers_a_hook(
        self, on_commit_spy, dispatch_task, nudge_flag_reset
    ):
        with override_settings(OUTBOX_DISPATCH_ON_COMMIT=True):
            bus = DomainEventBus()
            with db_transaction.atomic():
                bus.publish(_make_event())
                assert on_commit_spy, (
                    "no on_commit hook was registered inside the transaction"
                )

    def test_the_nudge_runs_after_the_commit_not_before(
        self, on_commit_spy, dispatch_task, nudge_flag_reset
    ):
        with override_settings(OUTBOX_DISPATCH_ON_COMMIT=True):
            bus = DomainEventBus()
            with db_transaction.atomic():
                bus.publish(_make_event())
                dispatch_task.delay.assert_not_called()

            dispatch_task.delay.assert_called_once_with()

    def test_enabled_outside_a_transaction_registers_no_hook(
        self, on_commit_spy, dispatch_task, nudge_flag_reset
    ):
        """Without a transaction there is no commit to hook into."""
        with override_settings(OUTBOX_DISPATCH_ON_COMMIT=True):
            bus = DomainEventBus()
            bus.publish(_make_event())  # no atomic() block (transaction=True)

        assert on_commit_spy == [], (
            "the dispatch nudge registered an on_commit hook outside a "
            "transaction"
        )
        dispatch_task.delay.assert_not_called()

    def test_the_rate_limiter_allows_one_nudge_per_window(
        self, on_commit_spy, dispatch_task, nudge_flag_reset
    ):
        """Two publishes in the same window must not enqueue two Celery messages."""
        with override_settings(OUTBOX_DISPATCH_ON_COMMIT=True):
            bus = DomainEventBus()
            with db_transaction.atomic():
                bus.publish(_make_event())
                bus.publish(_make_event())

        assert len(on_commit_spy) == 2, "both publishes should have registered a hook"
        dispatch_task.delay.assert_called_once()

    def test_a_failing_nudge_never_breaks_the_commit(
        self, on_commit_spy, dispatch_task, nudge_flag_reset
    ):
        dispatch_task.delay.side_effect = RuntimeError("broker down")

        with override_settings(OUTBOX_DISPATCH_ON_COMMIT=True):
            bus = DomainEventBus()
            event = _make_event()
            with db_transaction.atomic():
                bus.publish(event)

        # The commit went through and the outbox row is there: a broken
        # broker must not cost the caller its transaction.
        assert DomainEventOutbox.objects.filter(event_id=event.event_id).exists()

    def test_a_failing_nudge_is_reported_but_contained(self, caplog):
        caplog.set_level(logging.WARNING, logger="application.event_bus")

        with patch("application.tasks.dispatch_outbox_events") as task:
            task.delay.side_effect = RuntimeError("broker down")
            with override_settings(OUTBOX_DISPATCH_ON_COMMIT=True):
                bus = DomainEventBus()
                with db_transaction.atomic():
                    bus.publish(_make_event())

        assert any(
            "nudge failed" in record.getMessage() for record in caplog.records
        ), "a failing nudge must be visible in the log"
