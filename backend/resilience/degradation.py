"""
COMP-RO-004 DegradationManager — graceful-degradation fallback generation.

On final failure of an optional call (timeout, retries exhausted, or circuit Open)
this component produces a deterministic, frontend-recognisable FallbackResponse so
that core ReqFlow availability (CRUD, baselines) is unaffected by optional-subsystem
outages, and forwards a degradation event to the ResilienceAuditLogger.

Requirements:
- REQ-L3-RO-004-01 (deterministic fallback isolating the error)
- REQ-L3-RO-004-02 (forward degradation event to audit, non-blocking)

Interfaces:
- IF-RO-INT-003 (input)  : handle_failure(exception, target) -> FallbackResponse  (from PolicyEngine)
- IF-RO-INT-006 (output) : ResilienceAuditLogger.log_degradation(...)             (to COMP-RO-005)

Traceability: REQ-L2-RO-005 -> REQ-L1-032
"""
from __future__ import annotations

from resilience import audit_logger
from resilience.policies import (
    CircuitOpenError,
    FallbackResponse,
    NonRetryableError,
    TimeoutError as ResilienceTimeoutError,
)


def _error_code(exc: BaseException) -> str:
    """Map an exception to a stable machine-readable error code."""
    if isinstance(exc, CircuitOpenError):
        return "circuit_open"
    if isinstance(exc, ResilienceTimeoutError):
        return "timeout"
    if isinstance(exc, NonRetryableError):
        return "non_retryable"
    return "transient_exhausted"


def handle_failure(exception: BaseException, target_subsystem: str) -> FallbackResponse:
    """IF-RO-INT-003: build a fallback response for a failed optional call.

    REQ-L3-RO-004-01: returns a deterministic :class:`FallbackResponse` with
    ``degraded=True`` so the frontend can detect that the optional subsystem is
    temporarily inactive.
    REQ-L3-RO-004-02: forwards the degradation event to the ResilienceAuditLogger
    via IF-RO-INT-006 (best-effort, non-blocking).

    Args:
        exception: The terminal exception that ended the policy execution.
        target_subsystem: The target that failed.

    Returns:
        A :class:`FallbackResponse` describing the degraded state.
    """
    code = _error_code(exception)
    reason = f"{type(exception).__name__}: {exception}" if str(exception) else code

    response = FallbackResponse(
        degraded=True,
        target_subsystem=target_subsystem,
        reason=reason,
        error_code=code,
        detail={"exception_type": type(exception).__name__},
    )

    # IF-RO-INT-006 — forward to audit (the logger itself is non-blocking).
    audit_logger.log_degradation(
        target_subsystem=target_subsystem,
        error_code=code,
        reason=reason,
        detail=response.detail,
    )
    return response
