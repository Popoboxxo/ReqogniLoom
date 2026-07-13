"""
ARCH-L1-016 ResilienceOrchestrator — Public Service Facade.

Single public entry point for downstream consumers (ApplicationService — IF-L1-049,
LlmAdapter — IF-L1-050, WebhookDispatcher, GitHub integration) that wrap an
outbound call to an optional subsystem with the unified resilience policy:
circuit-breaker pre-check, configurable timeout, exponential-backoff retries, and
graceful degradation with audit logging.

Requirements (composed across components):
- REQ-L2-RO-001..006 -> REQ-L1-032

Components orchestrated:
- COMP-RO-001 AsyncDispatcher  (entry, circuit pre-check, decoupling)
- COMP-RO-002 PolicyEngine     (timeout, retry/backoff)
- COMP-RO-003 CircuitBreaker   (state machine)
- COMP-RO-004 DegradationManager (fallback)
- COMP-RO-005 ResilienceAuditLogger (audit)

Public Import Paths (for downstream consumers):
    from resilience.services import execute_optional, execute_optional_async
    from resilience.policies import Policy, FallbackResponse

Interface:
    IF-L1-049 / IF-L1-050: execute_optional() — wrap a synchronous outbound call
    IF-L1-049            : execute_optional_async() — enqueue an outbound call

Usage example (ApplicationService):
    from resilience.services import execute_optional

    result = execute_optional(
        operation=lambda payload: github_client.create_issue(payload),
        target_subsystem="github",
        payload={"title": "..."},
    )
    if getattr(result, "degraded", False):
        # optional subsystem is temporarily inactive — core flow continues
        ...

Note: rewiring the *callers* (ApplicationService, LlmAdapter) to route through this
facade is out of scope for this component; only the facade is provided here.

Traceability: REQ-L2-RO-001..006 -> REQ-L1-032
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resilience.dispatcher import AsyncDispatcher, DispatchResult
from resilience.policies import FallbackResponse, Policy

# An operation is a callable that takes the (optional) payload and performs the
# actual outbound call (IF-L1-051). It is transport-agnostic: the caller supplies
# the HTTP/SDK call; the orchestrator only wraps it with policy.
Operation = Callable[[Optional[dict]], Any]


def execute_optional(
    operation: Operation,
    target_subsystem: str,
    payload: Optional[dict] = None,
    policy: Optional[Policy] = None,
) -> Any:
    """IF-L1-049 / IF-L1-050: wrap a synchronous outbound call with resilience policy.

    Applies, in order: circuit-breaker pre-check (fast-fail when Open), per-attempt
    timeout, exponential-backoff retries on transient failures, and — on final
    failure — a graceful-degradation fallback that is also audit-logged. Core system
    availability is preserved because failures of the optional subsystem are isolated
    into a :class:`~resilience.policies.FallbackResponse` rather than propagated
    (REQ-L2-RO-005).

    Args:
        operation: Callable ``fn(payload) -> Any`` performing the outbound call.
        target_subsystem: Target identifier (``"llm"`` | ``"webhook"`` | ``"github"``
            or any custom key with a default policy).
        payload: Optional serialisable arguments passed to ``operation``.
        policy: Optional explicit :class:`Policy`; the per-target default is used
            otherwise.

    Returns:
        The operation's result on success, or a
        :class:`~resilience.policies.FallbackResponse` (``degraded=True``) when the
        call fails after retries or the circuit is Open.

    Raises:
        TenantContextNotSetError: If no tenant context is active (the breaker state
            is tenant-scoped).
    """
    dispatcher = AsyncDispatcher(target_subsystem, policy)
    result: DispatchResult = dispatcher.dispatch(lambda: operation(payload))
    return result.result


def execute_optional_async(
    operation_path: str,
    target_subsystem: str,
    payload: Optional[dict] = None,
    policy: Optional[Policy] = None,
) -> DispatchResult:
    """IF-L1-049: enqueue an outbound call for asynchronous execution (REQ-L2-RO-001).

    Decouples the caller's request thread from the outbound call by enqueueing a
    Celery task (or falling back to synchronous execution when no broker is
    reachable). The operation must be referenced by a dotted import path because
    queued payloads must be serialisable.

    Args:
        operation_path: Dotted path to a callable ``fn(payload) -> Any``.
        target_subsystem: Target identifier.
        payload: Optional serialisable arguments.
        policy: Optional explicit policy.

    Returns:
        A :class:`~resilience.dispatcher.DispatchResult`. ``accepted`` indicates the
        call was taken on; ``async_handle`` holds the queued task handle when a
        broker is available.
    """
    dispatcher = AsyncDispatcher(target_subsystem, policy)
    return dispatcher.dispatch_async(operation_path, payload)


__all__ = [
    "execute_optional",
    "execute_optional_async",
    "DispatchResult",
    "FallbackResponse",
    "Policy",
]
