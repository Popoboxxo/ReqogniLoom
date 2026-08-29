"""SA-18 regressions for COMP-RO-003 CircuitBreaker (Systemaudit 2026-08-27 §4.2 #10/#11).

Two independent defects, both in the accumulation path:

#10  ``_locked_or_create`` raced on the *first* report for a (tenant, target)
     pair. ``select_for_update`` cannot lock a row that does not exist yet, so
     two workers both fell through to the INSERT and the loser hit the
     ``uniq_circuit_per_tenant_target`` constraint — an IntegrityError raised
     out of the very component whose job is to absorb downstream failure.

#11  ``failure_count`` was a lifetime counter. Four failures months ago plus one
     today tripped the breaker today, fast-failing a healthy target because of
     history that had long since recovered.

Traceability: REQ-L3-RO-003-01/02 -> REQ-L2-RO-004 -> REQ-L1-032
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from persistence.tenancy import TenantContext
from resilience.circuit_breaker import CircuitBreaker
from resilience.models import CircuitBreakerState
from resilience.policies import Policy

pytestmark = pytest.mark.django_db


def _breaker(**policy_kwargs) -> CircuitBreaker:
    defaults = {"failure_threshold": 3, "recovery_timeout_seconds": 30.0}
    defaults.update(policy_kwargs)
    return CircuitBreaker("llm", Policy(**defaults))


# ---------------------------------------------------------------------------
# #11 — sliding failure window
# ---------------------------------------------------------------------------


def test_stale_failures_do_not_accumulate_across_the_window(active_tenant) -> None:
    """A failure older than the window starts a fresh burst instead of adding to it.

    This is the whole point of SA-18 #11: two isolated blips a long time apart
    must not add up to a trip.
    """
    breaker = _breaker(failure_threshold=3, failure_window_seconds=60.0)

    breaker.report_failure()
    breaker.report_failure()

    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.failure_count == 2
    assert row.state == CircuitBreakerState.STATE_CLOSED

    # Age the last failure past the window, as if the next blip happened much
    # later. Bypass the append guard by updating the column directly.
    CircuitBreakerState.objects.filter(pk=row.pk).update(
        last_failure_at=timezone.now() - timedelta(seconds=120)
    )

    breaker.report_failure()

    row.refresh_from_db()
    assert row.failure_count == 1, (
        "a failure outside the window must restart the burst, not extend it"
    )
    assert row.state == CircuitBreakerState.STATE_CLOSED, (
        "the breaker tripped on failures that were never concurrent"
    )


def test_failures_inside_the_window_still_accumulate_and_trip(active_tenant) -> None:
    """The window must not defang the breaker: a real burst still opens it."""
    breaker = _breaker(failure_threshold=3, failure_window_seconds=3600.0)

    breaker.report_failure()
    breaker.report_failure()
    breaker.report_failure()

    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.failure_count == 3
    assert row.state == CircuitBreakerState.STATE_OPEN


def test_window_boundary_uses_last_failure_not_first(active_tenant) -> None:
    """A steady trickle inside the window keeps accumulating.

    Each failure refreshes ``last_failure_at``, so a target failing every 30s
    with a 60s window accumulates rather than resetting — which is the intended
    "still broken" semantics.
    """
    breaker = _breaker(failure_threshold=3, failure_window_seconds=60.0)

    breaker.report_failure()
    row = CircuitBreakerState.objects.get(target_subsystem="llm")

    for _ in range(2):
        CircuitBreakerState.objects.filter(pk=row.pk).update(
            last_failure_at=timezone.now() - timedelta(seconds=30)
        )
        breaker.report_failure()

    row.refresh_from_db()
    assert row.failure_count == 3
    assert row.state == CircuitBreakerState.STATE_OPEN


def test_success_resets_the_counter(active_tenant) -> None:
    """Unchanged contract (REQ-L3-RO-003-04) — the window must not break it."""
    breaker = _breaker(failure_threshold=3, failure_window_seconds=3600.0)
    breaker.report_failure()
    breaker.report_failure()
    breaker.report_success()

    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.failure_count == 0
    assert row.state == CircuitBreakerState.STATE_CLOSED


# ---------------------------------------------------------------------------
# #10 — create race
# ---------------------------------------------------------------------------


def test_create_race_is_absorbed_instead_of_raising(active_tenant, monkeypatch) -> None:
    """A lost INSERT race resolves to the winner's row, not an IntegrityError.

    Reproduces the interleaving without threads: the rival worker's row is
    already committed, but this breaker's *first* lookup is forced to miss it —
    exactly what happens when the rival commits between our SELECT and our
    INSERT. The INSERT then hits ``uniq_circuit_per_tenant_target``, and the
    breaker must recover by re-reading rather than propagating a 500.

    Before the SA-18 fix this raised ``IntegrityError`` out of ``report_failure``.
    """
    rival_row = CircuitBreakerState.objects.create(
        target_subsystem="llm", tenant_id=TenantContext.get_tenant()
    )

    breaker = _breaker()
    real_select_locked = breaker._select_locked
    lookups: list[int] = []

    def _miss_once():
        lookups.append(1)
        if len(lookups) == 1:
            return None  # rival's row not visible to us yet
        return real_select_locked()

    monkeypatch.setattr(breaker, "_select_locked", _miss_once)

    # Must not raise.
    breaker.report_failure()

    assert len(lookups) == 2, (
        "the breaker must re-read after losing the create race"
    )
    rows = list(CircuitBreakerState.objects.filter(target_subsystem="llm"))
    assert len(rows) == 1, "the race must not leave duplicate breaker rows"
    assert rows[0].pk == rival_row.pk, (
        "the loser must adopt the winner's row rather than creating its own"
    )
    assert rows[0].failure_count == 1, (
        "the failure report must still be recorded on the adopted row"
    )


def test_unique_constraint_actually_exists(active_tenant) -> None:
    """Guards the premise of the retry: the DB really rejects the second row.

    If this constraint were ever dropped, the retry above would be dead code and
    concurrent workers would silently keep two independent breakers per target.
    """
    CircuitBreakerState.objects.create(
        target_subsystem="webhook", tenant_id=TenantContext.get_tenant()
    )
    with pytest.raises(IntegrityError):
        CircuitBreakerState.objects.create(
            target_subsystem="webhook", tenant_id=TenantContext.get_tenant()
        )
