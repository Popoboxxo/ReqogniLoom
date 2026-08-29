"""
ARCH-L1-016 ResilienceOrchestrator — Shared policy types and exceptions.

Cross-cutting value objects used by COMP-RO-001..005: the per-target
:class:`Policy` (timeout, retry, backoff, breaker thresholds), the resilience
exception hierarchy that distinguishes retryable transient failures from
permanent non-retryable ones (REQ-L3-RO-002-02), and the :class:`FallbackResponse`
DTO returned on graceful degradation (REQ-L3-RO-004-01).

Traceability: REQ-L2-RO-002, REQ-L2-RO-003, REQ-L2-RO-004, REQ-L2-RO-005 -> REQ-L1-032
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class ResilienceError(Exception):
    """Base class for all resilience-orchestrator errors."""


class TransientError(ResilienceError):
    """A retryable failure (network error, 5xx, timeout).

    REQ-L3-RO-002-02: only transient errors are retried with exponential backoff.
    """


class NonRetryableError(ResilienceError):
    """A permanent failure (e.g. HTTP 400) that must NOT be retried.

    REQ-L3-RO-002-02: non-retryable errors short-circuit the retry loop.
    """


class TimeoutError(TransientError):
    """The wrapped operation exceeded its configured timeout (REQ-L3-RO-002-01).

    Modelled as a transient error so a hung call is retried within the policy.
    """


class CircuitOpenError(ResilienceError):
    """Raised on fast-fail when the circuit for a target is Open.

    REQ-L3-RO-003-03: ``can_execute`` returned False; the call is rejected without
    touching the external subsystem.
    """


# ---------------------------------------------------------------------------
# Policy value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    """Per-target resilience policy (COMP-RO-002 / COMP-RO-003 configuration).

    REQ-L3-RO-002-01: ``timeout_seconds`` bounds a single attempt.
    REQ-L3-RO-002-02: ``max_retries`` (>= 1) and exponential backoff parameters.
    REQ-L3-RO-003-02/04: ``failure_threshold`` and ``recovery_timeout_seconds``
    drive the circuit-breaker transitions.

    Frozen so a policy can be shared safely across threads/workers.
    """

    timeout_seconds: float = 5.0
    max_retries: int = 2
    backoff_base_seconds: float = 0.2
    backoff_factor: float = 2.0
    backoff_max_seconds: float = 10.0
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    # SA-18 (Systemaudit 2026-08-27): sliding window for failure accumulation.
    # Without it, ``failure_count`` was a lifetime counter: four failures on
    # Monday plus one on Friday tripped the breaker on Friday, reporting an
    # outage that never happened. A failure that arrives more than this many
    # seconds after the previous one starts a fresh burst at 1, so the count
    # always describes "failures in the current window", which is what
    # ``failure_threshold`` is meant to compare against.
    #
    # The default spans several recovery windows so that a genuinely flapping
    # target still accumulates, while an isolated blip decays on its own.
    failure_window_seconds: float = 300.0

    def backoff_delay(self, attempt: int) -> float:
        """Return the backoff delay before ``attempt`` (1-based retry number).

        Exponential: ``base * factor**(attempt-1)``, capped at ``backoff_max``.
        REQ-L3-RO-002-02 (the wait grows exponentially between attempts).

        Args:
            attempt: 1-based retry index (1 = first retry).

        Returns:
            Delay in seconds before performing this retry.
        """
        if attempt < 1:
            return 0.0
        delay = self.backoff_base_seconds * (self.backoff_factor ** (attempt - 1))
        return min(delay, self.backoff_max_seconds)


# Default policies per known target subsystem. Application code may override by
# passing an explicit ``policy`` to ``execute_optional``.
DEFAULT_POLICIES: Dict[str, Policy] = {
    "llm": Policy(timeout_seconds=30.0, max_retries=2, failure_threshold=5),
    "webhook": Policy(timeout_seconds=10.0, max_retries=3, failure_threshold=5),
    "github": Policy(timeout_seconds=15.0, max_retries=2, failure_threshold=5),
}


def resolve_policy(target_subsystem: str, override: Optional[Policy] = None) -> Policy:
    """Return the effective policy for a target.

    Args:
        target_subsystem: Target identifier (e.g. ``"llm"``).
        override: Explicit policy supplied by the caller; wins if present.

    Returns:
        ``override`` if given, else the configured default, else a generic
        :class:`Policy`.
    """
    if override is not None:
        return override
    return DEFAULT_POLICIES.get(target_subsystem, Policy())


# ---------------------------------------------------------------------------
# Fallback DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FallbackResponse:
    """Graceful-degradation response returned when an optional call fails.

    REQ-L3-RO-004-01: deterministic, frontend-recognisable shape that signals the
    optional subsystem is temporarily inactive (``degraded=True``).
    """

    degraded: bool
    target_subsystem: str
    reason: str
    error_code: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation for API responses."""
        return {
            "degraded": self.degraded,
            "target_subsystem": self.target_subsystem,
            "reason": self.reason,
            "error_code": self.error_code,
            "detail": dict(self.detail),
        }
