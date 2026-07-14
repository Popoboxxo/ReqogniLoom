"""
COMP-LA-005 AsyncTaskDispatcher — Celery-based async dispatch for LLM long-runners.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-005
REQ-IDs: REQ-L2-LA-008, REQ-L3-LA005-001, REQ-L3-LA005-002,
         REQ-L3-LA005-003, REQ-L3-LA005-004

Architecture:
    docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/Components/
    COMP-LA-005_AsyncTaskDispatcher/L3_COMP-LA-005_AsyncTaskDispatcher_Architecture.md

Interface contracts:
    IF-LA-INT-005 (inbound from COMP-LA-003):
        dispatch_async(capability, kwargs) -> str (task_id)
        get_task_status(task_id) -> TaskStatusResult
    IF-LA-EXT-OUT-003 (outbound to Celery Broker):
        Celery task queue (Redis/RabbitMQ) via CELERY_BROKER_URL

Graceful stub:
    When Celery broker is not configured (CELERY_BROKER_URL unset), dispatch_async
    returns {"error": {"code": "BROKER_NOT_CONFIGURED"}} immediately.
    The module is importable without celery installed.

Celery configuration (env vars):
    CELERY_BROKER_URL          — Redis or RabbitMQ URL
    CELERY_TASK_SOFT_TIME_LIMIT — Worker soft timeout (seconds)
    CELERY_TASK_TIME_LIMIT      — Worker hard timeout (seconds)
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

BROKER_NOT_CONFIGURED = "BROKER_NOT_CONFIGURED"

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TaskStatusResult:
    """Structured response for get_task_status (REQ-L3-LA005-002).

    Attributes:
        task_id: UUID string identifying the dispatched task.
        status: One of "pending", "running", "done", "failed", "not_found".
        result: Task result dict when status is "done".
        error: Error message string when status is "failed".
    """

    task_id: str
    status: str  # pending | running | done | failed | not_found
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Broker / tenant helpers
# ---------------------------------------------------------------------------


def _broker_configured() -> bool:
    """Return True when a Celery broker URL is configured.

    The graceful stub (BROKER_NOT_CONFIGURED) relies on this: without a broker
    there is no point queueing a message no worker will consume.
    """
    return bool(os.environ.get("CELERY_BROKER_URL", ""))


def _resolve_tenant_id() -> Optional[str]:
    """Return the active tenant id as a string, or None when no context is set.

    The task runs in a Celery worker outside the request thread, so the tenant
    context must be propagated explicitly. We read it from the caller's thread
    and pass it as a plain string argument (UUIDs are not JSON-serialisable).
    """
    try:
        from persistence.tenancy import TenantContext  # noqa: PLC0415

        return str(TenantContext.get_tenant())
    except Exception:  # noqa: BLE001 — no/invalid context → dispatch tenant-less
        return None


# ---------------------------------------------------------------------------
# AsyncTaskDispatcher
# ---------------------------------------------------------------------------


class AsyncTaskDispatcher:
    """Dispatches LLM long-runner tasks to Celery and queries their status.

    Called by COMP-LA-003 (CapabilityRouter) via IF-LA-INT-005.
    """

    def dispatch_async(
        self,
        capability: str,
        kwargs: Dict[str, Any],
    ) -> Union[str, Dict[str, Any]]:
        """Dispatch a capability to the Celery task queue.

        Returns immediately with a task_id (UUID string). The actual LLM call
        runs in a Celery worker process (REQ-L3-LA005-001).

        Args:
            capability: Capability name ("decompose_requirement" or "check_consistency").
            kwargs: Arguments to pass to the provider method.

        Returns:
            task_id string (UUID) on success.
            Structured error dict if broker is not configured:
            {"error": {"code": "BROKER_NOT_CONFIGURED", "message": "..."}}.
        """
        if not _broker_configured():
            return {
                "error": {
                    "code": BROKER_NOT_CONFIGURED,
                    "message": (
                        "Celery broker not configured. "
                        "Set CELERY_BROKER_URL to enable async task dispatch."
                    ),
                }
            }

        try:
            # Registered as a @shared_task and autodiscovered by reqflow.celery,
            # so the running worker knows this task by name.
            from llm_adapter.tasks import run_capability  # noqa: PLC0415
        except ImportError:
            warnings.warn(
                "celery package not installed. Async dispatch is unavailable. "
                "Install with: pip install celery",
                RuntimeWarning,
                stacklevel=2,
            )
            return {
                "error": {
                    "code": BROKER_NOT_CONFIGURED,
                    "message": "Celery is not installed. Async task dispatch is unavailable.",
                }
            }

        tenant_id = _resolve_tenant_id()
        async_result = run_capability.apply_async(
            args=[capability, kwargs, tenant_id],
        )
        return async_result.id

    def get_task_status(self, task_id: str) -> TaskStatusResult:
        """Query the status of a previously dispatched task (REQ-L3-LA005-002).

        Args:
            task_id: UUID string returned by dispatch_async.

        Returns:
            TaskStatusResult with status in {"pending","running","done","failed","not_found"}.
        """
        if not _broker_configured():
            return TaskStatusResult(
                task_id=task_id,
                status="not_found",
                error="Celery broker not configured",
            )

        try:
            from celery.result import AsyncResult  # noqa: PLC0415
            from reqflow.celery import app as celery_app  # noqa: PLC0415

            async_result = AsyncResult(task_id, app=celery_app)
            state = async_result.state  # PENDING | STARTED | SUCCESS | FAILURE | RETRY

            if state == "PENDING":
                return TaskStatusResult(task_id=task_id, status="pending")
            elif state in ("STARTED", "RETRY"):
                return TaskStatusResult(task_id=task_id, status="running")
            elif state == "SUCCESS":
                return TaskStatusResult(
                    task_id=task_id,
                    status="done",
                    result=async_result.result,
                )
            elif state == "FAILURE":
                exc = async_result.result
                return TaskStatusResult(
                    task_id=task_id,
                    status="failed",
                    error=str(exc) if exc is not None else "Unknown error",
                )
            else:
                # REVOKED or unknown state
                return TaskStatusResult(
                    task_id=task_id,
                    status="not_found",
                )
        except Exception as exc:  # noqa: BLE001
            return TaskStatusResult(
                task_id=task_id,
                status="not_found",
                error=str(exc),
            )


__all__ = [
    "AsyncTaskDispatcher",
    "TaskStatusResult",
    "BROKER_NOT_CONFIGURED",
]
