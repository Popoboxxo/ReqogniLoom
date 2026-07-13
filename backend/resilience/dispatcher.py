"""
COMP-RO-001 AsyncDispatcher — accepts optional calls and decouples them.

Entry component for the ResilienceOrchestrator. Receives optional outbound calls
from the ApplicationService (IF-L1-049) and the LlmAdapter (IF-L1-050), performs a
fast pre-flight circuit check (IF-RO-INT-001), and either enqueues the call onto an
asynchronous queue or — when no broker is available — executes it synchronously via
the PolicyEngine (IF-RO-INT-002), so calling request threads are not blocked.

Requirements:
- REQ-L3-RO-001-01 (async enqueue; immediate caller return)
- REQ-L3-RO-001-02 (pre-flight circuit check; fast-fail when not executable)
- REQ-L3-RO-001-03 (delegate to PolicyEngine)

Interfaces:
- IF-L1-049 / IF-L1-050 (input)  : dispatch(operation, target, payload, policy)
- IF-RO-INT-001        (output)  : CircuitBreaker.can_execute()      (to COMP-RO-003)
- IF-RO-INT-002        (output)  : PolicyEngine.execute_with_policy() (to COMP-RO-002)

Traceability: REQ-L2-RO-001 -> REQ-L1-032
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from resilience import degradation
from resilience.circuit_breaker import CircuitBreaker
from resilience.policies import CircuitOpenError, Policy, resolve_policy
from resilience.policy_engine import PolicyEngine

Operation = Callable[[], Any]


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of an enqueue/dispatch attempt (REQ-L3-RO-001-01).

    ``accepted`` signals the call was taken on (enqueued or executed). When the
    breaker fast-fails (REQ-L3-RO-001-02), ``accepted`` is False and ``result``
    carries the degradation fallback. For synchronous execution ``result`` holds
    the operation result or its fallback; for async enqueue ``result`` is None and
    ``async_handle`` references the queued task.
    """

    accepted: bool
    result: Any = None
    async_handle: Any = None


class AsyncDispatcher:
    """Front door of the ResilienceOrchestrator for a single target."""

    def __init__(
        self,
        target_subsystem: str,
        policy: Optional[Policy] = None,
        breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        """Bind the dispatcher to a target.

        Args:
            target_subsystem: Target identifier (e.g. ``"llm"``).
            policy: Optional explicit policy.
            breaker: Optional breaker (injectable for tests).
        """
        self.target_subsystem = target_subsystem
        self.policy = resolve_policy(target_subsystem, policy)
        self.breaker = breaker or CircuitBreaker(target_subsystem, self.policy)

    def dispatch(self, operation: Operation) -> DispatchResult:
        """IF-L1-049/050: accept an optional call and decouple it.

        REQ-L3-RO-001-02: queries the breaker first; on ``can_execute() == False``
        the call is rejected immediately (fast-fail) with a degradation fallback,
        without touching the external subsystem.
        REQ-L3-RO-001-01/03: otherwise the call is handed to the PolicyEngine —
        asynchronously when a broker is available, synchronously as a graceful
        fallback — and the caller returns promptly.

        Args:
            operation: Zero-arg callable performing the outbound call.

        Returns:
            A :class:`DispatchResult` describing acceptance and outcome.
        """
        # IF-RO-INT-001 — pre-flight check.
        if not self.breaker.can_execute():
            fallback = degradation.handle_failure(
                CircuitOpenError(
                    f"circuit open for target '{self.target_subsystem}'"
                ),
                self.target_subsystem,
            )
            return DispatchResult(accepted=False, result=fallback)

        # IF-RO-INT-002 — delegate to PolicyEngine (sync fallback).
        engine = PolicyEngine(self.target_subsystem, self.policy, breaker=self.breaker)
        result = engine.execute_with_policy(operation)
        return DispatchResult(accepted=True, result=result)

    def dispatch_async(
        self,
        operation_path: str,
        payload: Optional[dict] = None,
    ) -> DispatchResult:
        """IF-L1-049: enqueue an optional call onto the async queue (REQ-L3-RO-001-01).

        Performs the same pre-flight circuit check, then enqueues a Celery task that
        will delegate to the PolicyEngine in a worker (REQ-L3-RO-001-03). Requires a
        serialisable operation reference (dotted import path + payload) because live
        callables cannot cross the queue boundary.

        Args:
            operation_path: Dotted path to ``fn(payload) -> Any``.
            payload: Serialisable arguments for the operation.

        Returns:
            A :class:`DispatchResult`; ``async_handle`` is the Celery AsyncResult
            when a broker is reachable, else None (synchronous fallback was used).
        """
        if not self.breaker.can_execute():
            fallback = degradation.handle_failure(
                CircuitOpenError(
                    f"circuit open for target '{self.target_subsystem}'"
                ),
                self.target_subsystem,
            )
            return DispatchResult(accepted=False, result=fallback)

        from resilience.tasks import _CELERY_AVAILABLE, execute_optional_task

        if _CELERY_AVAILABLE:
            try:
                handle = execute_optional_task.delay(
                    self.target_subsystem, operation_path, payload
                )
                return DispatchResult(accepted=True, async_handle=handle)
            except Exception:  # noqa: BLE001 — broker unreachable -> sync fallback
                pass

        # Synchronous fallback when no broker is configured/reachable.
        result = execute_optional_task(self.target_subsystem, operation_path, payload)
        return DispatchResult(accepted=True, result=result)
