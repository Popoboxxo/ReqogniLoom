"""
Tests for COMP-RO-002 PolicyEngine: timeout, retry with backoff, reporting,
and degradation on final failure.

Uses a fake CircuitBreaker (no DB) and a recording sleep so backoff is observable
without real waits.

Traceability: REQ-L3-RO-002-01..04 -> REQ-L2-RO-002/003 -> REQ-L1-032
"""
from __future__ import annotations

import threading
import time

import pytest

from resilience import degradation
from resilience.policies import (
    FallbackResponse,
    NonRetryableError,
    Policy,
    TransientError,
)
from resilience.policy_engine import PolicyEngine


class FakeBreaker:
    """In-memory breaker stand-in capturing report calls (no DB)."""

    def __init__(self) -> None:
        self.successes = 0
        self.failures = 0

    def can_execute(self) -> bool:
        return True

    def report_success(self) -> None:
        self.successes += 1

    def report_failure(self) -> None:
        self.failures += 1


@pytest.fixture
def recorded_sleep():
    delays = []
    return delays, (lambda d: delays.append(d))


@pytest.fixture(autouse=True)
def _no_audit(monkeypatch):
    """Silence the real audit path (DegradationManager forwards to audit)."""
    monkeypatch.setattr(degradation.audit_logger, "log_degradation", lambda **k: None)


def _engine(breaker, sleep, policy=None):
    policy = policy or Policy(max_retries=2, timeout_seconds=5.0)
    return PolicyEngine("github", policy=policy, breaker=breaker, sleep=sleep)


def test_success_reports_and_returns(recorded_sleep) -> None:
    """REQ-L3-RO-002-03: a successful call reports success and returns the result."""
    delays, sleep = recorded_sleep
    breaker = FakeBreaker()
    engine = _engine(breaker, sleep)
    result = engine.execute_with_policy(lambda: "ok")
    assert result == "ok"
    assert breaker.successes == 1
    assert breaker.failures == 0
    assert delays == []  # no retries -> no backoff


def test_retries_with_exponential_backoff_then_succeeds(recorded_sleep) -> None:
    """REQ-L3-RO-002-02: transient failures are retried with growing backoff."""
    delays, sleep = recorded_sleep
    breaker = FakeBreaker()
    policy = Policy(max_retries=3, backoff_base_seconds=0.1, backoff_factor=2.0)
    engine = _engine(breaker, sleep, policy)

    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientError("temporary")
        return "recovered"

    result = engine.execute_with_policy(flaky)
    assert result == "recovered"
    assert attempts["n"] == 3
    # Two retries -> two backoff sleeps, exponentially increasing.
    assert delays == [0.1, 0.2]
    assert breaker.successes == 1


def test_non_retryable_error_stops_immediately(recorded_sleep) -> None:
    """REQ-L3-RO-002-02: non-retryable errors are not retried; degradation returned."""
    delays, sleep = recorded_sleep
    breaker = FakeBreaker()
    engine = _engine(breaker, sleep)

    attempts = {"n": 0}

    def bad_request():
        attempts["n"] += 1
        raise NonRetryableError("400")

    result = engine.execute_with_policy(bad_request)
    assert attempts["n"] == 1  # no retry
    assert delays == []
    assert breaker.failures == 1
    assert isinstance(result, FallbackResponse)
    assert result.error_code == "non_retryable"


def test_retries_exhausted_triggers_degradation(recorded_sleep) -> None:
    """REQ-L3-RO-002-04: exhausting retries reports failure and degrades."""
    delays, sleep = recorded_sleep
    breaker = FakeBreaker()
    policy = Policy(max_retries=2, backoff_base_seconds=0.1)
    engine = _engine(breaker, sleep, policy)

    def always_fail():
        raise TransientError("down")

    result = engine.execute_with_policy(always_fail)
    assert breaker.failures == 1
    assert isinstance(result, FallbackResponse)
    assert result.degraded is True
    assert result.error_code == "transient_exhausted"
    assert len(delays) == 2  # 2 retries


def test_timeout_is_enforced_and_degrades() -> None:
    """REQ-L3-RO-002-01: a call exceeding the timeout is aborted and counts as failure."""
    breaker = FakeBreaker()
    policy = Policy(max_retries=0, timeout_seconds=0.1)
    engine = PolicyEngine(
        "github", policy=policy, breaker=breaker, sleep=lambda d: None
    )

    def slow():
        time.sleep(1.0)
        return "too late"

    result = engine.execute_with_policy(slow)
    assert isinstance(result, FallbackResponse)
    assert result.error_code == "timeout"
    assert breaker.failures == 1


# ---------------------------------------------------------------------------
# SA-17 (Systemaudit 2026-08-27 §4.2 #5) — the timeout must bound wallclock time
# ---------------------------------------------------------------------------


def test_timeout_returns_within_its_budget_not_after_the_operation() -> None:
    """The caller regains control at the timeout, not when the operation ends.

    Before the SA-17 fix the executor lived in a ``with`` block whose
    ``__exit__`` calls ``shutdown(wait=True)``, so a 0.1s timeout still blocked
    for the operation's full 2s. The documented timeout was advisory only.

    The bound asserted here is deliberately generous (well under the operation's
    own duration, well over the timeout) so the test measures the missing join,
    not scheduler jitter on a loaded CI box.
    """
    breaker = FakeBreaker()
    policy = Policy(max_retries=0, timeout_seconds=0.1)
    engine = PolicyEngine(
        "github", policy=policy, breaker=breaker, sleep=lambda d: None
    )

    operation_finished = threading.Event()

    def slow():
        time.sleep(2.0)
        operation_finished.set()
        return "too late"

    started = time.monotonic()
    result = engine.execute_with_policy(slow)
    elapsed = time.monotonic() - started

    assert isinstance(result, FallbackResponse)
    assert result.error_code == "timeout"
    assert elapsed < 1.0, (
        f"execute_with_policy blocked {elapsed:.2f}s on a 0.1s timeout — it is "
        "waiting for the abandoned operation instead of abandoning it"
    )
    assert not operation_finished.is_set(), (
        "sanity check: the operation must still be running when we return"
    )

    # Do not leak the orphan into the next test: it is expected to keep running
    # (that is the documented trade-off), so wait it out before finishing.
    assert operation_finished.wait(timeout=10.0)


def test_retries_do_not_multiply_the_timeout_budget() -> None:
    """Worst case is bounded by ``(retries + 1) x timeout``, not x duration.

    This is the compound form of the SA-17 defect: with ``wait=True`` each
    attempt paid the *operation's* real duration, so 2 retries over a 0.1s
    timeout took ~4.5s instead of ~0.3s.
    """
    breaker = FakeBreaker()
    policy = Policy(max_retries=2, timeout_seconds=0.1, backoff_base_seconds=0.0)
    engine = PolicyEngine(
        "github", policy=policy, breaker=breaker, sleep=lambda d: None
    )

    done = [threading.Event() for _ in range(3)]
    attempts = {"n": 0}

    def slow():
        index = attempts["n"]
        attempts["n"] += 1
        time.sleep(1.5)
        done[index].set()

    started = time.monotonic()
    result = engine.execute_with_policy(slow)
    elapsed = time.monotonic() - started

    assert isinstance(result, FallbackResponse)
    assert result.error_code == "timeout"
    assert attempts["n"] == 3, "all attempts must be made"
    assert elapsed < 1.5, (
        f"3 attempts at a 0.1s timeout took {elapsed:.2f}s — the engine is "
        "serialising on the abandoned operations"
    )

    for event in done:
        assert event.wait(timeout=10.0)
