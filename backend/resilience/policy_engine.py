"""
COMP-RO-002 PolicyEngine — timeout enforcement and exponential-backoff retries.

Applies the per-target timeout and retry policy to an outbound operation, reports
the final outcome to the CircuitBreaker, and triggers the DegradationManager on
final failure.

Requirements:
- REQ-L3-RO-002-01 (enforce timeout; timeout counts as a failure)
- REQ-L3-RO-002-02 (exponential-backoff retries; no retry on non-retryable errors)
- REQ-L3-RO-002-03 (report success/failure to CircuitBreaker)
- REQ-L3-RO-002-04 (trigger DegradationManager on final failure)

Interfaces:
- IF-RO-INT-002 (input)  : execute_with_policy(operation, target, payload)  (from AsyncDispatcher)
- IF-L1-051     (output) : the delegated call to the external system        (the operation callable)
- IF-RO-INT-003 (output) : DegradationManager.handle_failure(...)           (to COMP-RO-004)
- IF-RO-INT-004 (output) : CircuitBreaker.report_success / report_failure   (to COMP-RO-003)

Traceability: REQ-L2-RO-002, REQ-L2-RO-003 -> REQ-L1-032
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable, Optional

from resilience import degradation
from resilience.circuit_breaker import CircuitBreaker
from resilience.policies import (
    NonRetryableError,
    Policy,
    ResilienceError,
    TimeoutError as ResilienceTimeoutError,
    TransientError,
    resolve_policy,
)

# Operation contract (IF-L1-051): a zero-arg callable that performs the actual
# outbound call with the bound payload and returns its result. The PolicyEngine is
# transport-agnostic — it never speaks HTTP itself; it wraps whatever callable the
# adapter supplies.
Operation = Callable[[], Any]


class PolicyEngine:
    """Applies timeout + retry policy around a single outbound operation."""

    def __init__(
        self,
        target_subsystem: str,
        policy: Optional[Policy] = None,
        breaker: Optional[CircuitBreaker] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind the engine to a target.

        Args:
            target_subsystem: Target identifier (e.g. ``"llm"``).
            policy: Optional explicit policy; resolved per target otherwise.
            breaker: Optional breaker instance (injectable for tests); a default
                bound to the same target/policy is created if omitted.
            sleep: Sleep function for backoff delays (injectable so tests run fast).
        """
        self.target_subsystem = target_subsystem
        self.policy = resolve_policy(target_subsystem, policy)
        self.breaker = breaker or CircuitBreaker(target_subsystem, self.policy)
        self._sleep = sleep

    def execute_with_policy(self, operation: Operation) -> Any:
        """IF-RO-INT-002: run ``operation`` under the target's timeout/retry policy.

        Control flow:
        1. Attempt the call with a wallclock timeout (REQ-L3-RO-002-01); see
           :meth:`_call_with_timeout` for what that does and does not guarantee.
        2. On a transient failure, retry with exponential backoff up to
           ``max_retries`` (REQ-L3-RO-002-02).
        3. On a non-retryable error, stop immediately (REQ-L3-RO-002-02).
        4. On success, report to the breaker and return the result (REQ-L3-RO-002-03).
        5. On final failure, report to the breaker (REQ-L3-RO-002-03) and trigger
           the DegradationManager (REQ-L3-RO-002-04); its fallback is returned.

        Args:
            operation: Zero-arg callable performing the outbound call (IF-L1-051).

        Returns:
            The operation result on success, or a
            :class:`~resilience.policies.FallbackResponse` on final failure.
        """
        last_exc: BaseException = ResilienceError("no attempt executed")

        # Total attempts = 1 initial + max_retries.
        for attempt in range(self.policy.max_retries + 1):
            if attempt > 0:
                self._sleep(self.policy.backoff_delay(attempt))
            try:
                result = self._call_with_timeout(operation)
                self.breaker.report_success()  # IF-RO-INT-004
                return result
            except NonRetryableError as exc:
                # REQ-L3-RO-002-02: never retry these.
                last_exc = exc
                break
            except (TransientError, ResilienceTimeoutError) as exc:
                last_exc = exc
                continue

        # Final failure path.
        self.breaker.report_failure()  # IF-RO-INT-004 / REQ-L3-RO-002-03
        # IF-RO-INT-003 / REQ-L3-RO-002-04
        return degradation.handle_failure(last_exc, self.target_subsystem)

    def _call_with_timeout(self, operation: Operation) -> Any:
        """Run ``operation`` with a wallclock timeout (REQ-L3-RO-002-01).

        Uses a worker thread + future timeout rather than ``signal`` so it works
        off the main thread (Celery/WSGI workers). A timed-out call raises
        :class:`~resilience.policies.TimeoutError`, which is transient and counts
        as a failure.

        .. note:: **What "timeout" guarantees here — SA-17 (Systemaudit
           2026-08-27).**

           Python cannot interrupt a thread that is blocked in a socket read, so
           the timeout bounds *the caller*, not the operation. On expiry this
           method returns control immediately and abandons the worker thread,
           which keeps running until the underlying call finishes or its own
           transport timeout fires.

           This used to be untrue: the executor lived in a ``with`` block, whose
           ``__exit__`` calls ``shutdown(wait=True)`` and therefore blocked until
           the abandoned operation actually finished. The timeout was purely
           advisory, and with the retry loop on top the worst case was
           ``(max_retries + 1) x real_duration`` — a 30s policy could pin a
           worker for minutes. ``shutdown(wait=False)`` makes the documented
           budget real.

           The cost is a possible orphan thread per timed-out attempt. It is
           bounded in practice: the LLM transport carries its own socket
           timeout, and the CircuitBreaker opens after ``failure_threshold``
           consecutive failures, so a permanently hung target stops receiving
           new attempts instead of accumulating threads indefinitely. Orphans
           carry the ``resilience-<target>`` thread-name prefix so they are
           identifiable in a stack dump.

        Raises:
            ResilienceTimeoutError: If the operation exceeds the policy timeout.
            NonRetryableError / TransientError: Propagated from the operation, with
                unclassified exceptions wrapped as transient.
        """
        pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"resilience-{self.target_subsystem}",
        )
        try:
            future = pool.submit(operation)
            try:
                return future.result(timeout=self.policy.timeout_seconds)
            except FutureTimeoutError:
                # No-op for an already-running future (documented Future
                # semantics); kept so a not-yet-started retry attempt is never
                # dispatched after its budget expired.
                future.cancel()
                raise ResilienceTimeoutError(
                    f"operation on '{self.target_subsystem}' exceeded "
                    f"{self.policy.timeout_seconds}s timeout"
                )
            except (NonRetryableError, TransientError, ResilienceTimeoutError):
                raise
            except Exception as exc:  # noqa: BLE001
                # Unknown exception from the outbound call: treat as transient so
                # the retry loop and breaker can react (REQ-L3-RO-002-02).
                raise TransientError(str(exc)) from exc
        finally:
            # wait=False is the whole point (see the note above): never block on
            # an operation whose timeout has already been reported to the caller.
            # A completed operation's thread is reclaimed here as usual.
            pool.shutdown(wait=False)
