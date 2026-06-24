"""
Tests for COMP-RO-004 DegradationManager fallback generation and audit forwarding.

Traceability: REQ-L3-RO-004-01/02 -> REQ-L2-RO-005 -> REQ-L1-032
"""
from __future__ import annotations

import pytest

from resilience import degradation
from resilience.policies import (
    CircuitOpenError,
    FallbackResponse,
    NonRetryableError,
    TimeoutError as ResilienceTimeoutError,
    TransientError,
)


@pytest.fixture
def captured_audit(monkeypatch):
    events = []
    monkeypatch.setattr(
        degradation.audit_logger,
        "log_degradation",
        lambda **kwargs: events.append(kwargs),
    )
    return events


def test_fallback_is_deterministic_and_degraded(captured_audit) -> None:
    """REQ-L3-RO-004-01: returns a degraded, frontend-recognisable FallbackResponse."""
    resp = degradation.handle_failure(TransientError("boom"), "llm")
    assert isinstance(resp, FallbackResponse)
    assert resp.degraded is True
    assert resp.target_subsystem == "llm"
    assert resp.as_dict()["degraded"] is True


@pytest.mark.parametrize(
    "exc,code",
    [
        (CircuitOpenError("x"), "circuit_open"),
        (ResilienceTimeoutError("x"), "timeout"),
        (NonRetryableError("x"), "non_retryable"),
        (TransientError("x"), "transient_exhausted"),
    ],
)
def test_error_codes_mapped(captured_audit, exc, code) -> None:
    """Each exception maps to its stable error code."""
    resp = degradation.handle_failure(exc, "github")
    assert resp.error_code == code


def test_event_forwarded_to_audit(captured_audit) -> None:
    """REQ-L3-RO-004-02: a degradation event is forwarded to the audit logger."""
    degradation.handle_failure(TransientError("down"), "webhook")
    assert len(captured_audit) == 1
    assert captured_audit[0]["target_subsystem"] == "webhook"
    assert captured_audit[0]["error_code"] == "transient_exhausted"
