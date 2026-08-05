"""
COMP-LA-003 CapabilityRouter — Central entry point for all LLM capability calls.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-003
REQ-IDs: REQ-L2-LA-002, REQ-L2-LA-003, REQ-L2-LA-005, REQ-L2-LA-008,
         REQ-L3-LA003-001, REQ-L3-LA003-002, REQ-L3-LA003-003

Architecture:
    docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/Components/
    COMP-LA-003_CapabilityRouter/L3_COMP-LA-003_CapabilityRouter_Architecture.md

Interface contracts:
    IF-LA-EXT-IN-001 (inbound from ApplicationService):
        execute_capability(capability_name, **kwargs) -> LlmResult | dict
    IF-LA-INT-001 (outbound to COMP-LA-001):
        _ALLOWED_CAPABILITIES = {
        "validate_artifact",
        "decompose_requirement",
        "check_consistency",
        "derive_requirements",
    }IF-LA-INT-002 (outbound to COMP-LA-002):
        get_provider() -> LlmCapabilityInterface
    IF-LA-INT-004 (outbound to COMP-LA-004):
        log_llm_call(provider, capability, artifact_id, token_usage, success, error)
    IF-LA-INT-005 (outbound to COMP-LA-005):
        dispatch_async(capability, kwargs) -> task_id

Routing decisions (ADR-L3-LA003-01):
    validate_artifact        → synchronous provider call
    decompose_requirement    → async Celery dispatch → returns task_id immediately
    check_consistency        → async Celery dispatch → returns task_id immediately

Graceful Degradation:
    - LLM_PROVIDER not set  → {"error": {"code": "LLM_NOT_CONFIGURED"}}
    - capability disabled    → {"error": {"code": "LLM_NOT_CONFIGURED"}}
    - provider error         → {"error": {"code": "LLM_PROVIDER_ERROR", "message": ...}}
    No raw exception escapes this class (REQ-L3-LA003-003, ADR-L3-LA003-02).
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from typing import Any, Callable, Dict, Optional, Set, Union

from llm_adapter.audit_logger import LlmAuditLogger, extract_token_usage
from llm_adapter.dispatcher import AsyncTaskDispatcher
from llm_adapter.interface import LlmResult
from llm_adapter.providers import (
    LLM_NOT_CONFIGURED,
    LLM_PROVIDER_ERROR,
    LlmNotConfiguredError,
    LlmProviderUnknownError,
    get_provider,
)
from llm_adapter.timeouts import sync_timeout_seconds
from llm_adapter.token_tracking import (
    LLM_TOKEN_LIMIT_EXCEEDED,
    is_over_daily_limit,
    record_token_usage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Capabilities that are routed synchronously (validate_artifact only)
_SYNC_CAPABILITIES: Set[str] = {"validate_artifact"}

# Capabilities that are dispatched asynchronously via Celery
_ASYNC_CAPABILITIES: Set[str] = {"decompose_requirement", "check_consistency", "derive_requirements"}

# All known capabilities
_ALL_CAPABILITIES: Set[str] = _SYNC_CAPABILITIES | _ASYNC_CAPABILITIES


# ---------------------------------------------------------------------------
# Capability configuration — REQ-L3-LA003-002 / REQ-L2-LA-003
# ---------------------------------------------------------------------------


def _sync_timeout_seconds() -> float:
    """Return the hard sync-call timeout (REQ-084).

    Read from ``settings.LLM_SYNC_TIMEOUT_SECONDS`` (env ``LLM_SYNC_TIMEOUT``,
    default 25s — below the typical 30s Gunicorn worker timeout). Falls back
    to 25 when Django settings are not configured (isolated unit tests).

    Delegates to :mod:`llm_adapter.timeouts`, the single seam for LLM timeout
    resolution (issue #342). The router's own capabilities are all
    single-artifact, so no workspace-wide purpose applies here.
    """
    return sync_timeout_seconds()


def _read_enabled_capabilities() -> Set[str]:
    """Parse LLM_CAPABILITIES env var into a set of active capability names.

    Format: comma-separated list, e.g. "validate_artifact,decompose_requirement".
    Missing variable or empty string → empty set (fail-safe, all disabled).

    Returns:
        Set of enabled capability name strings.
    """
    raw = os.environ.get("LLM_CAPABILITIES", "").strip()
    if not raw:
        return set()
    return {c.strip() for c in raw.split(",") if c.strip()}


# ---------------------------------------------------------------------------
# Error response helpers
# ---------------------------------------------------------------------------


def _not_configured_response(message: str = "LLM not configured") -> Dict[str, Any]:
    """Build a LLM_NOT_CONFIGURED error response dict."""
    return {"error": {"code": LLM_NOT_CONFIGURED, "message": message}}


def _provider_error_response(message: str) -> Dict[str, Any]:
    """Build a LLM_PROVIDER_ERROR response dict."""
    return {"error": {"code": LLM_PROVIDER_ERROR, "message": message}}


def _token_limit_response(message: str) -> Dict[str, Any]:
    """Build a LLM_TOKEN_LIMIT_EXCEEDED response dict (REQ-106).

    Includes ``http_status: 429`` so a REST/MCP boundary can map the structured
    error to an HTTP 429 (Too Many Requests) response without inspecting the
    message text.
    """
    return {
        "error": {
            "code": LLM_TOKEN_LIMIT_EXCEEDED,
            "message": message,
            "http_status": 429,
        }
    }


# ---------------------------------------------------------------------------
# CapabilityRouter
# ---------------------------------------------------------------------------


class CapabilityRouter:
    """Central router for all LLM capability invocations (IF-LA-EXT-IN-001).

    Reads capability activation config from environment at instantiation time.
    For test isolation, pass explicit enabled_capabilities to override env vars.

    Args:
        enabled_capabilities: Override for active capabilities (default: env-driven).
        audit_logger: Injectable LlmAuditLogger (default: standard instance).
        dispatcher: Injectable AsyncTaskDispatcher (default: standard instance).
    """

    def __init__(
        self,
        enabled_capabilities: Optional[Set[str]] = None,
        audit_logger: Optional[LlmAuditLogger] = None,
        dispatcher: Optional[AsyncTaskDispatcher] = None,
    ) -> None:
        self._enabled: Set[str] = (
            enabled_capabilities
            if enabled_capabilities is not None
            else _read_enabled_capabilities()
        )
        self._audit_logger = audit_logger or LlmAuditLogger()
        self._dispatcher = dispatcher or AsyncTaskDispatcher()

    # ------------------------------------------------------------------
    # Public interface — IF-LA-EXT-IN-001
    # ------------------------------------------------------------------

    def execute_capability(
        self,
        capability_name: str,
        **kwargs: Any,
    ) -> Union[LlmResult, Dict[str, Any]]:
        """Execute an LLM capability by name.

        Synchronous capabilities (validate_artifact) return an LlmResult.
        Async capabilities (decompose_requirement, check_consistency) return
        {"task_id": "<uuid>"} immediately without blocking.
        Degradation cases return {"error": {"code": ..., "message": ...}}.

        Args:
            capability_name: One of "validate_artifact", "decompose_requirement",
                             "check_consistency".
            **kwargs: Arguments forwarded to the provider method.

        Returns:
            LlmResult for sync calls, {"task_id": ...} for async calls,
            or structured error dict on any failure.
        """
        # --- Capability disabled or not configured (REQ-L3-LA003-002) ---
        if capability_name not in self._enabled:
            self._audit_logger.log_llm_call(
                provider="none",
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=None,
                success=False,
                error=LLM_NOT_CONFIGURED,
            )
            return _not_configured_response(
                f"Capability '{capability_name}' is not enabled. "
                "Set LLM_CAPABILITIES to include it."
            )

        # --- Per-tenant daily token limit (REQ-106) ---
        # Enforced at the adapter boundary so every consumer (REST, MCP,
        # application services) is protected uniformly. Fail-open: a broken
        # accounting layer never blocks LLM calls (see token_tracking).
        if is_over_daily_limit():
            self._audit_logger.log_llm_call(
                provider="none",
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=None,
                success=False,
                error=LLM_TOKEN_LIMIT_EXCEEDED,
            )
            return _token_limit_response(
                "Daily token limit exceeded for this tenant. "
                "Try again later or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        # --- Async routing (REQ-L3-LA003-001) ---
        if capability_name in _ASYNC_CAPABILITIES:
            return self._dispatch_async(capability_name, kwargs)

        # --- Sync routing (REQ-L3-LA003-001) ---
        return self._execute_sync(capability_name, kwargs)

    # ------------------------------------------------------------------
    # Sync execution
    # ------------------------------------------------------------------

    def _execute_sync(
        self, capability_name: str, kwargs: Dict[str, Any]
    ) -> Union[LlmResult, Dict[str, Any]]:
        """Execute a capability synchronously via the provider.

        REQ-084: the provider call runs under a hard timeout
        (``LLM_SYNC_TIMEOUT_SECONDS``) so a slow provider can never block the
        request thread long enough to exhaust the Gunicorn worker pool.
        """
        provider_name = "unknown"
        try:
            provider = get_provider()
            provider_name = getattr(provider, "PROVIDER_NAME", type(provider).__name__)
            method = getattr(provider, capability_name)
            result: LlmResult = self._call_with_sync_timeout(
                provider_name, method, kwargs
            )

            self._audit_logger.log_llm_call(
                provider=provider_name,
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=result.token_usage,
                success=True,
                error=None,
            )
            # REQ-106: persist token consumption for per-tenant aggregation and
            # daily-limit enforcement. Best-effort — never breaks the result.
            record_token_usage(
                provider=provider_name,
                capability=capability_name,
                input_tokens=result.token_usage or 0,
                output_tokens=0,
                workspace_id=kwargs.get("workspace_id"),
            )
            return result

        except (LlmNotConfiguredError, LlmProviderUnknownError) as exc:
            # Not-configured errors map to LLM_NOT_CONFIGURED
            self._audit_logger.log_llm_call(
                provider=provider_name,
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=None,
                success=False,
                error=str(exc),
            )
            return _not_configured_response(str(exc))

        except TimeoutError:
            # Timeout from provider HTTP layer
            self._audit_logger.log_llm_call(
                provider=provider_name,
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=None,
                success=False,
                error="Request timed out",
            )
            return _provider_error_response("Request timed out")

        except Exception as exc:  # noqa: BLE001
            # Categorise by message content (Rate limit, API error, generic)
            msg = str(exc)
            if "429" in msg or "Rate limit" in msg.lower() or "rate limit" in msg.lower():
                error_msg = "Rate limit exceeded"
            elif any(f"API error: {c}" in msg or f"{c}" in msg for c in ["500", "502", "503", "504"]):
                # Extract HTTP status if present
                for code in ["500", "502", "503", "504", "400", "401", "403"]:
                    if code in msg:
                        error_msg = f"API error: {code}"
                        break
                else:
                    error_msg = msg
            else:
                error_msg = msg

            self._audit_logger.log_llm_call(
                provider=provider_name,
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=None,
                success=False,
                error=error_msg,
            )
            return _provider_error_response(error_msg)

    # ------------------------------------------------------------------
    # Sync timeout enforcement (REQ-084)
    # ------------------------------------------------------------------

    @staticmethod
    def _call_with_sync_timeout(
        provider_name: str,
        method: Callable[..., Any],
        kwargs: Dict[str, Any],
    ) -> Any:
        """Run a sync provider call under the hard LLM sync timeout (REQ-084).

        The call executes in a single worker thread; the caller waits at most
        ``LLM_SYNC_TIMEOUT_SECONDS``. On expiry the request thread is released
        immediately (``shutdown(wait=False)`` — the abandoned worker thread
        ends when the provider's own HTTP timeout fires) and a built-in
        ``TimeoutError`` is raised for the existing timeout handling path.

        The active tenant context (thread-local) is re-established inside the
        worker thread so tenant-scoped reads (LlmSettings, breaker state)
        behave exactly as in the request thread.

        Raises:
            TimeoutError: When the call exceeds the configured sync timeout.
        """
        timeout = _sync_timeout_seconds()

        tenant_id = None
        try:
            from persistence.tenancy import TenantContext  # noqa: PLC0415

            tenant_id = TenantContext.get_tenant()
        except Exception:  # noqa: BLE001 — no tenant context → run without one
            TenantContext = None  # type: ignore[assignment]

        def _call() -> Any:
            if tenant_id is not None and TenantContext is not None:
                TenantContext.set_tenant(tenant_id)
            try:
                return method(**kwargs)
            finally:
                if tenant_id is not None and TenantContext is not None:
                    TenantContext.clear_tenant()

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-sync")
        try:
            future = pool.submit(_call)
            try:
                return future.result(timeout=timeout)
            except FutureTimeoutError:
                future.cancel()
                logger.warning(
                    "LLM sync call timed out after %ds for provider %s",
                    timeout,
                    provider_name,
                )
                raise TimeoutError(
                    f"LLM sync call timed out after {timeout:g}s "
                    f"for provider {provider_name}"
                ) from None
        finally:
            # Never block the request thread on an abandoned provider call.
            pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Async dispatch
    # ------------------------------------------------------------------

    def _dispatch_async(
        self, capability_name: str, kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch a long-running capability to Celery and return task_id."""
        try:
            result = self._dispatcher.dispatch_async(capability_name, kwargs)

            if isinstance(result, dict) and "error" in result:
                # Broker not configured or other dispatch error
                self._audit_logger.log_llm_call(
                    provider="celery",
                    capability=capability_name,
                    artifact_id=kwargs.get("artifact_id")
                    or kwargs.get("requirement_id")
                    or kwargs.get("workspace_id"),
                    token_usage=None,
                    success=False,
                    error=result["error"].get("code", "DISPATCH_ERROR"),
                )
                return result

            # result is a task_id string
            self._audit_logger.log_llm_call(
                provider="celery",
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=None,
                success=True,
                error=None,
            )
            return {"task_id": result}

        except Exception as exc:  # noqa: BLE001
            self._audit_logger.log_llm_call(
                provider="celery",
                capability=capability_name,
                artifact_id=kwargs.get("artifact_id")
                or kwargs.get("requirement_id")
                or kwargs.get("workspace_id"),
                token_usage=None,
                success=False,
                error=str(exc),
            )
            return _provider_error_response(str(exc))

    # ------------------------------------------------------------------
    # Task status proxy
    # ------------------------------------------------------------------

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Proxy task status query to AsyncTaskDispatcher.

        Args:
            task_id: UUID string returned by execute_capability for async calls.

        Returns:
            Dict with keys: task_id, status, and optionally result or error.
        """
        status_result = self._dispatcher.get_task_status(task_id)
        out: Dict[str, Any] = {
            "task_id": status_result.task_id,
            "status": status_result.status,
        }
        if status_result.result is not None:
            out["result"] = status_result.result
        if status_result.error is not None:
            out["error"] = status_result.error
        return out


__all__ = [
    "CapabilityRouter",
]
