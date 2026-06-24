"""
Integration tests for COMP-RO-001 AsyncDispatcher and the public service facade
(resilience.services.execute_optional). Exercises the full sync path:
circuit pre-check -> policy execution -> degradation, against the real DB-backed
breaker.

Traceability: REQ-L3-RO-001-01..03 + REQ-L2-RO-001/005 -> REQ-L1-032
"""
from __future__ import annotations

import pytest

from resilience import audit_logger
from resilience.dispatcher import AsyncDispatcher
from resilience.models import CircuitBreakerState
from resilience.policies import FallbackResponse, Policy
from resilience.services import execute_optional

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _silence_audit(monkeypatch):
    """Avoid hitting the AuditLog DB path during resilience integration tests."""
    monkeypatch.setattr(audit_logger, "log_write", lambda **kw: None)


def test_dispatch_executes_and_returns_result(active_tenant) -> None:
    """REQ-L3-RO-001-01/03: an accepted call is delegated and its result returned."""
    dispatcher = AsyncDispatcher("github", Policy(max_retries=0))
    result = dispatcher.dispatch(lambda: "issue-created")
    assert result.accepted is True
    assert result.result == "issue-created"


def test_dispatch_fast_fails_when_circuit_open(active_tenant) -> None:
    """REQ-L3-RO-001-02: an Open circuit fast-fails without running the operation."""
    # Force the breaker Open up-front.
    CircuitBreakerState.objects.create(
        target_subsystem="github",
        state=CircuitBreakerState.STATE_OPEN,
        tenant_id=active_tenant.id,
    )
    ran = {"called": False}

    def op():
        ran["called"] = True
        return "should not run"

    dispatcher = AsyncDispatcher("github", Policy(recovery_timeout_seconds=999))
    result = dispatcher.dispatch(op)

    assert result.accepted is False
    assert ran["called"] is False
    assert isinstance(result.result, FallbackResponse)
    assert result.result.error_code == "circuit_open"


def test_execute_optional_facade_success(active_tenant) -> None:
    """Public facade returns the raw operation result on success."""
    result = execute_optional(
        operation=lambda payload: {"echo": payload},
        target_subsystem="webhook",
        payload={"a": 1},
        policy=Policy(max_retries=0),
    )
    assert result == {"echo": {"a": 1}}


def test_execute_optional_facade_degrades_on_failure(active_tenant) -> None:
    """REQ-L2-RO-005: failure is isolated into a FallbackResponse, not raised."""
    def boom(payload):
        raise RuntimeError("subsystem down")

    result = execute_optional(
        operation=boom,
        target_subsystem="llm",
        policy=Policy(max_retries=1, backoff_base_seconds=0.0),
    )
    assert isinstance(result, FallbackResponse)
    assert result.degraded is True
