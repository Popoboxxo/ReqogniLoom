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
import uuid
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
# Celery app — lazy initialisation
# ---------------------------------------------------------------------------


def _get_celery_app():
    """Return the project Celery app, or None if not configured.

    Tries to import the reqflow.celery module. If the broker URL is absent or
    the celery package is not installed, returns None so dispatch_async can
    return a BROKER_NOT_CONFIGURED error gracefully.
    """
    broker_url = os.environ.get("CELERY_BROKER_URL", "")
    if not broker_url:
        return None

    try:
        from celery import Celery  # noqa: PLC0415

        app = Celery("llm_adapter")
        app.conf.broker_url = broker_url
        app.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", broker_url)
        soft_limit = os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT")
        hard_limit = os.environ.get("CELERY_TASK_TIME_LIMIT")
        if soft_limit:
            app.conf.task_soft_time_limit = int(soft_limit)
        if hard_limit:
            app.conf.task_time_limit = int(hard_limit)
        return app
    except ImportError:
        warnings.warn(
            "celery package not installed. Async dispatch is unavailable. "
            "Install with: pip install celery",
            RuntimeWarning,
            stacklevel=2,
        )
        return None


# ---------------------------------------------------------------------------
# Celery task definition
# ---------------------------------------------------------------------------


def _make_task(app):
    """Define the Celery worker task bound to the given app."""

    @app.task(bind=True, name="llm_adapter.run_capability")
    def run_capability(self, capability: str, kwargs: dict) -> dict:
        """Execute an LLM capability inside the Celery worker.

        Args:
            capability: Name of the capability (decompose_requirement or check_consistency).
            kwargs: Arguments forwarded to the provider method.

        Returns:
            Serialisable dict of the LlmResult or LlmDecompositionResult /
            LlmConsistencyResult fields.
        """
        import dataclasses

        try:
            # Import here to avoid circular import in worker context
            from llm_adapter.providers import get_provider  # noqa: PLC0415

            provider = get_provider()
            method = getattr(provider, capability)
            result = method(**kwargs)
            # Dataclass → dict for Celery serialisation
            return dataclasses.asdict(result)
        except Exception as exc:  # noqa: BLE001
            # Store failure in result backend so get_task_status returns "failed"
            # We re-raise so Celery marks the task FAILURE and stores the exc.
            raise exc

    return run_capability


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
        app = _get_celery_app()
        if app is None:
            return {
                "error": {
                    "code": BROKER_NOT_CONFIGURED,
                    "message": (
                        "Celery broker not configured. "
                        "Set CELERY_BROKER_URL to enable async task dispatch."
                    ),
                }
            }

        task = _make_task(app)
        task_id = str(uuid.uuid4())
        task.apply_async(
            args=[capability, kwargs],
            task_id=task_id,
        )
        return task_id

    def get_task_status(self, task_id: str) -> TaskStatusResult:
        """Query the status of a previously dispatched task (REQ-L3-LA005-002).

        Args:
            task_id: UUID string returned by dispatch_async.

        Returns:
            TaskStatusResult with status in {"pending","running","done","failed","not_found"}.
        """
        app = _get_celery_app()
        if app is None:
            return TaskStatusResult(
                task_id=task_id,
                status="not_found",
                error="Celery broker not configured",
            )

        try:
            from celery.result import AsyncResult  # noqa: PLC0415

            async_result = AsyncResult(task_id, app=app)
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
