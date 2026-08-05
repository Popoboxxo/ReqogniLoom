"""REQ-082 — Resilience integration for outbound LLM provider calls.

Bridges COMP-LA-002 (ProviderRegistry) to ARCH-L1-016 (ResilienceOrchestrator,
IF-L1-050). Every real provider wraps its outbound HTTP/SDK transport call in
:func:`resilient_call`, which applies the shared resilience policy:

- 3 retries with exponential backoff (1s, 2s, 4s) on transient failures:
  connection errors, timeouts, HTTP 5xx and rate-limit (429) responses.
- No retry on permanent failures: HTTP 400/401/403 (and other 4xx), or a
  missing provider SDK.
- A circuit breaker per provider *class* (breaker state is keyed by the
  ``llm:<provider_name>`` target, not by provider instance) that fast-fails
  while Open and probes recovery via Half-Open.

On final failure a :class:`LlmTransportError` is raised so the existing
CapabilityRouter error mapping (LLM_PROVIDER_ERROR, rate-limit / 5xx message
categorisation) keeps working unchanged — callers of the providers never see
a resilience-internal ``FallbackResponse``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from resilience.circuit_breaker import CircuitBreaker
from resilience.policies import (
    FallbackResponse,
    NonRetryableError,
    Policy,
    ResilienceError,
    TransientError,
)
from resilience.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)

# REQ-082: 3 retries with exponential backoff 1s -> 2s -> 4s per provider call.
LLM_MAX_RETRIES = 3

# Issue #342: the retry budget is per *attempt*, and PolicyEngine's timeout
# does not abort the worker thread (a timed-out attempt still blocks until the
# provider actually answers). With a long per-attempt timeout the worst-case
# wall clock therefore becomes (max_retries + 1) x timeout — minutes for a
# workspace-wide call, far past any client or proxy timeout. Calls that already
# get a generous per-attempt budget get a correspondingly smaller retry budget.
LLM_LONG_CALL_THRESHOLD_SECONDS = 60.0
LLM_LONG_CALL_MAX_RETRIES = 1
LLM_BACKOFF_BASE_SECONDS = 1.0
LLM_BACKOFF_FACTOR = 2.0
LLM_BACKOFF_MAX_SECONDS = 4.0

# Injectable sleep hook (module-level so provider-integration tests can
# monkeypatch it and run the backoff loop without real delays).
_sleep: Callable[[float], None] = time.sleep

# HTTP status classification (REQ-082):
#   retry     — 429 (rate limit) and any 5xx
#   no retry  — every other 4xx (400 invalid request, 401/403 auth, ...)
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class LlmTransportError(RuntimeError):
    """Outbound LLM call failed after the resilience policy was exhausted.

    Carries the final error text (including any HTTP status token) so the
    CapabilityRouter's message-based categorisation still applies.
    """


def _extract_status_code(exc: BaseException) -> Optional[int]:
    """Best-effort HTTP status extraction from heterogeneous SDK exceptions.

    Anthropic/OpenAI SDK errors expose ``status_code``; ``requests.HTTPError``
    exposes ``response.status_code``. Returns None when no status is found.
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def classify_exception(exc: BaseException) -> ResilienceError:
    """Map an arbitrary transport exception onto the resilience taxonomy.

    REQ-082 retry matrix:
      - connection/timeout errors            -> TransientError (retry)
      - HTTP 5xx and 429                     -> TransientError (retry)
      - HTTP 4xx other than 429 (400/401/..) -> NonRetryableError (no retry)
      - missing provider SDK                 -> NonRetryableError (no retry)
      - anything else                        -> TransientError (fail-safe retry,
        consistent with PolicyEngine's handling of unclassified errors)

    The original message is preserved so downstream error categorisation in
    the CapabilityRouter (rate-limit / 5xx detection) keeps working.
    """
    if isinstance(exc, ResilienceError):
        return exc

    status = _extract_status_code(exc)
    if status is not None:
        if status in _RETRYABLE_STATUS or status >= 500:
            return TransientError(str(exc))
        if 400 <= status < 500:
            return NonRetryableError(str(exc))

    # Missing SDK is permanent — retrying an ImportError is pointless.
    if isinstance(exc, ImportError) or isinstance(exc.__cause__, ImportError):
        return NonRetryableError(str(exc))
    if "not installed" in str(exc):
        return NonRetryableError(str(exc))

    # Connection resets, DNS failures, socket timeouts etc. have no status
    # code; treat them (and any unknown error) as transient so the retry
    # loop and the breaker can react.
    return TransientError(str(exc))


class _NullCircuitBreaker:
    """No-op breaker used when no tenant context is active.

    CircuitBreakerState rows are tenant-scoped (REQ-L1-032); outside a tenant
    context (e.g. isolated unit tests or management commands) there is no row
    to bind to, so breaker bookkeeping is skipped while retry/backoff still
    applies.
    """

    def can_execute(self) -> bool:
        return True

    def report_success(self) -> None:
        return None

    def report_failure(self) -> None:
        return None


def _breaker_for(target_subsystem: str, policy: Policy):
    """Return the circuit breaker bound to a provider-class target.

    One breaker per provider *class* (REQ-082): CircuitBreaker instances are
    stateless — the shared state lives in the ``CircuitBreakerState`` row keyed
    by ``(tenant, target_subsystem)``, so binding the target to the provider
    name yields exactly one breaker state per provider class and tenant.
    """
    try:
        from persistence.tenancy import TenantContext  # noqa: PLC0415

        TenantContext.get_tenant()  # raises when no context is active
    except Exception:  # noqa: BLE001 — no tenant context -> skip breaker state
        logger.debug(
            "No tenant context active; circuit breaker disabled for %s",
            target_subsystem,
        )
        return _NullCircuitBreaker()
    return CircuitBreaker(target_subsystem, policy)


def max_retries_for_timeout(timeout_seconds: float) -> int:
    """Return the retry budget that fits *timeout_seconds* (issue #342).

    Short per-attempt timeouts keep the full REQ-082 retry budget. Long ones
    (>= :data:`LLM_LONG_CALL_THRESHOLD_SECONDS`, i.e. the workspace-wide
    tools) are capped at :data:`LLM_LONG_CALL_MAX_RETRIES` so a hung provider
    cannot stretch a single request into several minutes.

    Args:
        timeout_seconds: Per-attempt timeout the call will run under.

    Returns:
        Number of retries (attempts = returned value + 1).
    """
    if float(timeout_seconds) >= LLM_LONG_CALL_THRESHOLD_SECONDS:
        return LLM_LONG_CALL_MAX_RETRIES
    return LLM_MAX_RETRIES


def resilient_call(
    operation: Callable[[], Any],
    *,
    provider_name: str,
    timeout_seconds: float,
) -> Any:
    """Execute an outbound LLM transport call under the resilience policy.

    Args:
        operation: Zero-arg callable performing the actual HTTP/SDK call.
        provider_name: Provider class identifier (e.g. ``"anthropic"``); used
            as the per-class circuit-breaker target ``llm:<provider_name>``.
        timeout_seconds: Hard per-attempt timeout (enforced by PolicyEngine).
            Also determines the retry budget — see
            :func:`max_retries_for_timeout` (issue #342).

    Returns:
        The operation result on success (possibly after retries).

    Raises:
        LlmTransportError: When the circuit is Open (fast-fail) or the call
            still fails after all retries / a non-retryable error occurred.
    """
    target = f"llm:{provider_name}"
    policy = Policy(
        timeout_seconds=float(timeout_seconds),
        max_retries=max_retries_for_timeout(timeout_seconds),
        backoff_base_seconds=LLM_BACKOFF_BASE_SECONDS,
        backoff_factor=LLM_BACKOFF_FACTOR,
        backoff_max_seconds=LLM_BACKOFF_MAX_SECONDS,
    )
    breaker = _breaker_for(target, policy)

    # Fast-fail while the circuit is Open (REQ-L3-RO-003-03).
    if not breaker.can_execute():
        raise LlmTransportError(
            f"circuit open for LLM provider '{provider_name}': "
            "calls are temporarily rejected"
        )

    def _classified_operation() -> Any:
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 — classified and re-raised
            raise classify_exception(exc) from exc

    engine = PolicyEngine(target, policy, breaker=breaker, sleep=lambda s: _sleep(s))
    result = engine.execute_with_policy(_classified_operation)

    if isinstance(result, FallbackResponse):
        # PolicyEngine degraded gracefully; providers must raise instead so
        # the CapabilityRouter maps the failure to LLM_PROVIDER_ERROR.
        logger.warning(
            "LLM call to provider %s failed after resilience policy: %s",
            provider_name,
            result.reason,
        )
        raise LlmTransportError(
            f"LLM provider '{provider_name}' call failed "
            f"({result.error_code}): {result.reason}"
        )
    return result


__all__ = [
    "LlmTransportError",
    "classify_exception",
    "resilient_call",
    "LLM_MAX_RETRIES",
    "LLM_BACKOFF_BASE_SECONDS",
]
