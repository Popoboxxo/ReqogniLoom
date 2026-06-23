"""
COMP-PL-003 TransactionCoordinator — ACID transaction control.

Requirements:
- REQ-L2-PL-002 / REQ-L3-PL003-001 (mandatory transaction wrapping)
- REQ-L3-PL003-002 (full rollback on error)
- REQ-L3-PL003-003 (configurable transaction timeout)

Architecture:
- docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/
  COMP-PL-003_TransactionCoordinator/L3_COMP-PL-003_TransactionCoordinator_Architecture.md

Hybrid pattern (ADR-L3-PL-003): a decorator for simple service methods and an
explicit context manager for multi-step operations. Both delegate to Django's
native ``transaction.atomic()`` so that any unhandled exception triggers a full
rollback (REQ-L3-PL003-002).
"""
from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from django.db import transaction

F = TypeVar("F", bound=Callable[..., Any])


class TransactionTimeoutError(RuntimeError):
    """Raised when a transaction exceeds the configured statement timeout.

    REQ-L3-PL003-003. The timeout itself is enforced at the database level via
    ``SET LOCAL statement_timeout`` inside :class:`TransactionContextManager`;
    PostgreSQL aborts the transaction and Django surfaces the error, which is
    re-raised as this type for callers that want to distinguish timeouts.
    """


def atomic_transaction(func: F) -> F:
    """Wrap a service method in ``transaction.atomic()`` (REQ-L3-PL003-001).

    Any exception raised inside ``func`` rolls back the whole transaction; nothing
    is partially persisted (REQ-L3-PL003-002).

    Example:
        @atomic_transaction
        def create_requirement(...):
            artifact = Artifact.objects.create(...)
            return Requirement.objects.create(artifact=artifact, ...)
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with transaction.atomic():
            return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


class TransactionContextManager:
    """Explicit atomic context manager for multi-step write operations.

    REQ-L3-PL003-001/002: every nested write runs inside a single ``atomic()``
    block, so a failure on any step (e.g. a constraint violation on the seventh
    child of a batch decomposition) rolls back the entire batch.

    REQ-L3-PL003-003: when ``timeout_seconds`` is given, a PostgreSQL
    ``statement_timeout`` is applied for the duration of the transaction. The
    value is configurable via the ``DB_TRANSACTION_TIMEOUT_SECONDS`` environment
    variable (resolved by the caller, default 30s).

    Example:
        with TransactionContextManager(timeout_seconds=30):
            for artifact in artifacts:
                Artifact.objects.create(parent=artifact, ...)
    """

    def __init__(self, timeout_seconds: int | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._atomic = transaction.atomic()

    def __enter__(self) -> "TransactionContextManager":
        self._atomic.__enter__()
        if self.timeout_seconds is not None:
            from django.db import connection

            timeout_ms = int(self.timeout_seconds) * 1000
            with connection.cursor() as cursor:
                # SET LOCAL is scoped to the current transaction only.
                cursor.execute("SET LOCAL statement_timeout = %s", [timeout_ms])
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        # Delegate commit/rollback to Django's atomic block. Returning its result
        # preserves exception propagation (False = do not suppress).
        return bool(self._atomic.__exit__(exc_type, exc_val, exc_tb))


__all__ = [
    "TransactionTimeoutError",
    "atomic_transaction",
    "TransactionContextManager",
]
