"""
Tests for COMP-RO-005 ResilienceAuditLogger forwarding to the AuditLog facade.

Verifies state-change and degradation events reach audit.services.log_write, and
that the logger never raises (non-blocking, REQ-L3-RO-005-03).

Traceability: REQ-L3-RO-005-01..03 -> REQ-L2-RO-006 -> REQ-L1-032
"""
from __future__ import annotations

import pytest
from django.db import transaction

from resilience import audit_logger


def test_state_change_forwarded_to_log_write(monkeypatch) -> None:
    """REQ-L3-RO-005-01: circuit state changes are forwarded to log_write."""
    calls = []
    monkeypatch.setattr(audit_logger, "log_write", lambda **kw: calls.append(kw))

    audit_logger.log_state_change("llm", "closed", "open")

    assert len(calls) == 1
    kw = calls[0]
    assert kw["operation"] == audit_logger._RESILIENCE_OP
    assert kw["entity_type"] == "ResilienceEvent"
    assert kw["ctx"]["event"] == "circuit_state_change"
    assert kw["ctx"]["old_state"] == "closed"
    assert kw["ctx"]["new_state"] == "open"
    assert kw["ctx"]["source"] == "resilience"


def test_degradation_forwarded_to_log_write(monkeypatch) -> None:
    """REQ-L3-RO-005-02: degradation events are forwarded with error code + target."""
    calls = []
    monkeypatch.setattr(audit_logger, "log_write", lambda **kw: calls.append(kw))

    audit_logger.log_degradation("github", "timeout", "exceeded", {"x": 1})

    assert len(calls) == 1
    assert calls[0]["ctx"]["event"] == "degradation"
    assert calls[0]["ctx"]["error_code"] == "timeout"
    assert calls[0]["ctx"]["target"] == "github"


def test_logger_is_non_blocking_on_audit_failure(monkeypatch) -> None:
    """REQ-L3-RO-005-03: a failing audit write must not propagate to the caller."""
    def boom(**kwargs):
        raise RuntimeError("audit backend down")

    monkeypatch.setattr(audit_logger, "log_write", boom)

    # Must not raise.
    audit_logger.log_state_change("llm", "open", "half_open")
    audit_logger.log_degradation("llm", "x", "y")


def test_stable_entity_id_is_deterministic() -> None:
    """The derived entity id is stable per target (groups audit rows)."""
    a = audit_logger._stable_entity_id("llm")
    b = audit_logger._stable_entity_id("llm")
    c = audit_logger._stable_entity_id("github")
    assert a == b
    assert a != c


@pytest.mark.django_db(transaction=True)
def test_audit_write_is_deferred_until_commit(monkeypatch) -> None:
    """An audit write inside an atomic block must run at commit, not inline.

    The breaker calls ``log_state_change`` from inside its own
    ``transaction.atomic()``. Performing the best-effort audit INSERT there
    couples a non-critical side effect to the business transaction: a DB
    error raised by the audit backend marks the whole transaction as
    needing rollback, and the breaker's commit then fails with
    ``TransactionManagementError``. Deferring the write to ``on_commit``
    keeps the audit path strictly out of the breaker's transaction.
    """
    calls = []
    monkeypatch.setattr(audit_logger, "log_write", lambda **kw: calls.append(kw))

    with transaction.atomic():
        audit_logger.log_state_change("llm", "closed", "open")
        # Still inside the breaker-like transaction: nothing written yet.
        assert calls == []

    # The outermost atomic committed -> the deferred callback ran.
    assert len(calls) == 1
    assert calls[0]["ctx"]["event"] == "circuit_state_change"


@pytest.mark.django_db(transaction=True)
def test_audit_failure_does_not_poison_breaker_transaction(
    active_tenant, monkeypatch, caplog
) -> None:
    """A failing audit write must not break the enclosing breaker commit.

    ``audit.services.log_write`` raising (here simulated with a RuntimeError
    from the audit backend) used to run inline inside
    ``CircuitBreaker.report_failure``'s atomic block. With the write deferred
    to commit, the exception is caught in the callback, a warning is logged,
    and the breaker's own state change commits cleanly.
    """
    from resilience.circuit_breaker import CircuitBreaker
    from resilience.models import CircuitBreakerState
    from resilience.policies import Policy

    def boom(**kwargs):
        raise RuntimeError("audit backend down")

    monkeypatch.setattr(audit_logger, "log_write", boom)

    breaker = CircuitBreaker(
        "llm", Policy(failure_threshold=1, recovery_timeout_seconds=30.0)
    )
    # Must commit without raising TransactionManagementError.
    with transaction.atomic():
        breaker.report_failure()

    row = CircuitBreakerState.objects.get(target_subsystem="llm")
    assert row.state == CircuitBreakerState.STATE_OPEN
    assert "ResilienceAuditLogger failed to forward event" in caplog.text
