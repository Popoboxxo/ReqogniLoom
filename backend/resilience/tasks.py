"""
COMP-RO-001 AsyncDispatcher — Celery task definitions (broker-optional).

Defines the asynchronous worker entry point that delegates an enqueued optional
call to the PolicyEngine (IF-RO-INT-002). Celery is wired here when available; if
the Celery package or broker is absent, the dispatcher falls back to synchronous
execution (see :mod:`resilience.dispatcher`), so the system degrades gracefully in
environments without a running broker.

Requirements:
- REQ-L3-RO-001-03 (async workers delegate to PolicyEngine via IF-RO-INT-002)

Traceability: REQ-L2-RO-001 -> REQ-L1-032
"""
from __future__ import annotations

from typing import Any, Optional

# Celery is optional. When the package is unavailable we expose ``shared_task`` as
# a no-op decorator so this module imports cleanly and the synchronous fallback in
# the dispatcher is used instead.
try:  # pragma: no cover - exercised only when celery is installed
    from celery import shared_task

    _CELERY_AVAILABLE = True
except Exception:  # noqa: BLE001
    _CELERY_AVAILABLE = False

    def shared_task(*dargs: Any, **dkwargs: Any):  # type: ignore[no-redef]
        """No-op stand-in for ``celery.shared_task`` when Celery is absent."""

        def _wrap(func):
            return func

        # Support both @shared_task and @shared_task(...) usage.
        if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
            return dargs[0]
        return _wrap


@shared_task(name="resilience.execute_optional_task")
def execute_optional_task(
    target_subsystem: str,
    operation_path: str,
    payload: Optional[dict] = None,
) -> Any:
    """Celery worker entry point: resolve and run an optional call under policy.

    REQ-L3-RO-001-03: the async worker reconstructs the operation from a dotted
    import path (queue payloads must be serialisable, so we persist the import path
    plus payload rather than a live callable) and delegates to the PolicyEngine.

    Args:
        target_subsystem: Target identifier.
        operation_path: Dotted path to a callable ``fn(payload) -> Any``.
        payload: Serialisable arguments for the operation.

    Returns:
        The PolicyEngine result (operation result or FallbackResponse).
    """
    from django.utils.module_loading import import_string

    from resilience.policy_engine import PolicyEngine

    fn = import_string(operation_path)
    engine = PolicyEngine(target_subsystem)
    return engine.execute_with_policy(lambda: fn(payload))
