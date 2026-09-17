"""
Tests for COMP-RO-003 CircuitBreaker state machine.

Covers: initial Closed, failure accumulation -> Open, fast-fail while Open,
recovery Open -> Half-Open after timeout, Half-Open success -> Closed and
Half-Open failure -> Open, plus audit emission on every transition.

Traceability: REQ-L3-RO-003-01..04 -> REQ-L2-RO-004 -> REQ-L1-032
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from resilience import audit_logger
from resilience.circuit_breaker import CircuitBreaker
from resilience.models import CircuitBreakerState
from resilience.policies import Policy

pytestmark = pytest.mark.django_db


def _breaker(threshold: int = 3, recovery: float = 30.0) -> CircuitBreaker:
    policy = Policy(failure_threshold=threshold, recovery_timeout_seconds=recovery)
    return CircuitBreaker("llm", policy)


def test_new_target_starts_closed_and_can_execute(active_tenant) -> None:
    """REQ-L3-RO-003-01: a fresh target is Closed and allows traffic."""
    breaker = _breaker()
    assert breaker.can_execute() is True
    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.state == CircuitBreakerState.STATE_CLOSED


def test_trips_to_open_at_threshold(active_tenant, monkeypatch) -> None:
    """REQ-L3-RO-003-02: N consecutive failures open the circuit and emit audit."""
    calls = []
    monkeypatch.setattr(
        audit_logger, "log_state_change",
        lambda t, o, n: calls.append((t, o, n)),
    )
    breaker = _breaker(threshold=3)
    breaker.report_failure()
    breaker.report_failure()
    assert breaker.can_execute() is True  # still closed below threshold
    breaker.report_failure()  # 3rd -> open

    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.state == CircuitBreakerState.STATE_OPEN
    assert ("llm", "closed", "open") in calls


def test_fast_fail_while_open(active_tenant) -> None:
    """REQ-L3-RO-003-03: can_execute returns False while Open."""
    breaker = _breaker(threshold=1, recovery=999)
    breaker.report_failure()  # opens immediately
    assert breaker.can_execute() is False


def test_recovery_to_half_open_after_timeout(active_tenant) -> None:
    """REQ-L3-RO-003-04: after the recovery timeout, one probe is allowed."""
    breaker = _breaker(threshold=1, recovery=30.0)
    breaker.report_failure()  # open
    # Backdate opened_at so the recovery window has elapsed.
    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    row.opened_at = timezone.now() - timedelta(seconds=31)
    row.save(update_fields=["opened_at"])

    assert breaker.can_execute() is True  # probe allowed -> Half-Open
    row.refresh_from_db()
    assert row.state == CircuitBreakerState.STATE_HALF_OPEN
    # Second concurrent probe is rejected (single probe).
    assert breaker.can_execute() is False


def test_half_open_success_closes(active_tenant) -> None:
    """REQ-L3-RO-003-04: success in Half-Open closes the circuit."""
    breaker = _breaker(threshold=1, recovery=0.0)
    breaker.report_failure()  # open
    breaker.can_execute()  # recovery=0 -> immediately half-open
    breaker.report_success()
    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.state == CircuitBreakerState.STATE_CLOSED
    assert row.failure_count == 0


def test_half_open_failure_reopens(active_tenant) -> None:
    """REQ-L3-RO-003-04: failure in Half-Open re-opens the circuit."""
    breaker = _breaker(threshold=1, recovery=0.0)
    breaker.report_failure()  # open
    breaker.can_execute()  # -> half-open
    breaker.report_failure()  # -> open again
    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.state == CircuitBreakerState.STATE_OPEN


# ---------------------------------------------------------------------------
# peek_state() — read-only diagnostic snapshot (issue #714)
# ---------------------------------------------------------------------------


def test_peek_state_returns_none_for_untouched_target(active_tenant) -> None:
    """A target with no recorded failure has no row yet — nothing to peek."""
    breaker = _breaker()
    assert breaker.peek_state() is None


def test_peek_state_reflects_open_state_and_failure_count(active_tenant) -> None:
    breaker = _breaker(threshold=1, recovery=999)
    breaker.report_failure()  # opens immediately

    snapshot = breaker.peek_state()
    assert snapshot is not None
    state, failure_count, opened_at = snapshot
    assert state == CircuitBreakerState.STATE_OPEN
    assert failure_count == 1
    assert opened_at is not None


def test_peek_state_does_not_lock_or_create_a_row(active_tenant) -> None:
    """peek_state() must not itself create the row (pure read, no side effect)."""
    breaker = _breaker()
    breaker.peek_state()
    assert not CircuitBreakerState.objects.filter(target_subsystem="llm").exists()
