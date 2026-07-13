"""
ARCH-L1-012 AuditLog — Domain Event definitions and in-process Event Bus.

Implements IF-AL-EXT-IN-001: AuditableOperationOccurred event that ApplicationService
publishes (post_commit) and COMP-AL-001 AuditLogWriter subscribes to.

Requirements:
- REQ-L3-AL001-001 (Event-Bus-Subscription and field extraction)
- REQ-L2-AL-004 (atomic consistency: post_commit ensures audit write happens only
  after the business transaction has committed successfully)

Architecture:
- docs/se/L1/Gesamtsystem/L2/AuditLogSystem/Components/
  COMP-AL-001_AuditLogWriter/L3_COMP-AL-001_AuditLogWriter_Architecture.md
- ADR-AL-02: synchronous audit logging via DomainEventBus post_commit hook.

Design note (ADR-AL-02):
  The EventBus is in-process and synchronous. Subscribers are called within the
  same database transaction when ``publish_in_transaction`` is used, satisfying
  atomic consistency (REQ-L2-AL-004). When called via ``publish_post_commit``,
  Django's ``on_commit`` hook defers the call until after the outer transaction
  commits — useful when the audit write should be decoupled from the originating
  transaction (non-critical path). For mandatory atomic writes, callers should
  use the synchronous path directly via AuditLogWriter.write().
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event dataclass — IF-AL-EXT-IN-001
# ---------------------------------------------------------------------------


@dataclass
class AuditableOperationOccurred:
    """Domain event published by ApplicationService after every write operation.

    Implements IF-AL-EXT-IN-001 contract:
      actor, actor_type, op, entity_type, entity_id, version, change_reason?, ctx

    ``ctx`` carries MCP enrichment data (client_name, api_key) when the
    originating call came from an MCP client. AuditLogWriter's ContextEnricher
    extracts and hashes these fields (REQ-L3-AL001-002).

    Forward-compatibility: extra fields on ``ctx`` are silently ignored
    (REQ-L3-AL001-001 AC: event with unknown extra fields is accepted).
    """

    actor: str
    """User ID or Agent ID string."""

    actor_type: str
    """'user' | 'agent'"""

    op: str
    """'create' | 'update' | 'delete' | 'transition'"""

    entity_type: str
    """Affected entity class name (e.g. 'Requirement', 'TestCase')."""

    entity_id: UUID
    """Primary key of the affected entity."""

    version: Optional[int] = None
    """Entity version at the time of the operation (may be None for deletes)."""

    change_reason: Optional[str] = None
    """Optional human-readable reason (e.g. workflow transition label)."""

    ctx: Dict[str, Any] = field(default_factory=dict)
    """Request context. MCP path provides: source, client_name, api_key."""


# ---------------------------------------------------------------------------
# In-process event bus — ADR-AL-02
# ---------------------------------------------------------------------------


_HandlerType = Callable[[AuditableOperationOccurred], None]
_subscribers: List[_HandlerType] = []


class DomainEventBus:
    """Minimal in-process event bus for AuditableOperationOccurred events.

    AuditLogWriter (COMP-AL-001) registers itself at application startup via
    ``subscribe()``. ApplicationService publishes events via ``publish()``.

    Thread-safety: subscriber list is populated at startup and read-only during
    request processing. Registration after startup is not supported.
    """

    @staticmethod
    def subscribe(handler: _HandlerType) -> None:
        """Register a handler for AuditableOperationOccurred events.

        REQ-L3-AL001-001: AuditLogWriter subscribes at application startup.

        Args:
            handler: Callable that receives an AuditableOperationOccurred event.
        """
        if handler not in _subscribers:
            _subscribers.append(handler)
            logger.debug("DomainEventBus: registered handler %s", handler)

    @staticmethod
    def publish(event: AuditableOperationOccurred) -> None:
        """Publish an event synchronously to all registered subscribers.

        Called within an active database transaction for atomic consistency
        (REQ-L2-AL-004). Exceptions in handlers propagate to the caller,
        which triggers a transaction rollback.

        Args:
            event: The AuditableOperationOccurred instance to dispatch.
        """
        for handler in _subscribers:
            try:
                handler(event)
            except Exception:
                # Re-raise: a failed audit write must roll back the transaction
                # (REQ-L2-AL-004, ADR-AL-02).
                logger.exception(
                    "DomainEventBus: handler %s raised during publish; re-raising to roll back TX.",
                    handler,
                )
                raise

    @staticmethod
    def publish_post_commit(event: AuditableOperationOccurred) -> None:
        """Schedule event dispatch for after the current transaction commits.

        Uses Django's ``transaction.on_commit`` hook. If no transaction is
        active, the handler is called immediately. This path does NOT guarantee
        atomic consistency with the triggering operation — use only for
        best-effort, non-critical audit paths.

        Args:
            event: The AuditableOperationOccurred instance to dispatch.
        """
        from django.db import transaction

        def _dispatch():
            DomainEventBus.publish(event)

        transaction.on_commit(_dispatch)

    @staticmethod
    def clear_subscribers() -> None:
        """Remove all registered subscribers.

        For use in tests only — allows clean isolation between test cases.
        """
        _subscribers.clear()


__all__ = [
    "AuditableOperationOccurred",
    "DomainEventBus",
]
