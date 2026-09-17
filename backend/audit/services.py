"""
ARCH-L1-012 AuditLog — Public Service Facade.

This module is the single public entry point for downstream consumers
(application, llm_adapter, mcp_server, resilience) of the AuditLog system.

Requirements:
- REQ-L2-AL-001 (log_write for all write operations)
- REQ-L2-AL-002 (MCP enrichment via ctx)
- REQ-L2-AL-003 (append-only: no update/delete exposed)
- REQ-L2-AL-004 (atomic consistency with business operation)
- REQ-L2-AL-005 (query with filters and pagination)
- REQ-L2-AL-006 (tenant isolation via TenantContext)

Architecture:
- docs/se/L1/Gesamtsystem/L2/AuditLogSystem/L2_AuditLogSystem_Architecture.md

Public Import Paths (for downstream consumers):
    from audit.services import log_write, query
    from audit.services import AuditQueryFilters, PaginatedAuditResult

Interface:
    IF-AL-EXT-IN-001: log_write() — writes one audit entry for a write operation
    IF-AL-EXT-IN-002: query() — retrieves paginated, filtered audit entries

Usage example (ApplicationService):
    from audit.services import log_write

    @atomic_transaction
    def create_requirement(actor, tenant, ...):
        req = Requirement.objects.create(...)
        log_write(
            actor=str(actor.id),
            actor_type="user",
            operation="create",
            entity_type="Requirement",
            entity_id=req.id,
            version=req.version,
        )
        return req

MCP usage example (mcp_server):
    log_write(
        actor="agent-client-id",
        actor_type="agent",
        operation="create",
        entity_type="Requirement",
        entity_id=req.id,
        ctx={"source": "mcp", "client_name": "claude-code/1.0", "api_key": raw_key},
    )
"""
from __future__ import annotations

import contextlib
import threading
from typing import Any, Dict, Optional
from uuid import UUID

from audit.events import AuditableOperationOccurred
from audit.models import AuditEntry
from audit.query import (
    AuditLogQuery,
    AuditQueryFilters,
    DEFAULT_PAGE_SIZE,
    PaginatedAuditResult,
)
from audit.writer import get_writer


# ---------------------------------------------------------------------------
# MCP audit handoff (Codeberg #313): suppress the redundant internal entry
# ---------------------------------------------------------------------------
#
# Some MCP tool handlers call an ApplicationService method (which writes its
# own audit entry via ServiceBase._audit -> log_write) and then immediately
# write a second, MCP-enriched entry for the *same* entity via
# mcp_server.tools.base.write_mcp_audit — producing two identical-looking
# rows per logical write (Codeberg #313).
#
# ``mcp_audit_handoff()`` lets such a handler suppress the inner entry for
# the duration of a single, tightly-scoped service call, so the MCP-level
# call (with agent identity, client_name, hashed api_key) becomes the sole
# entry. It is deliberately checked here in ``log_write`` — the one choke
# point every write path funnels through (ServiceBase._audit,
# diagram.manager's direct log_write calls, etc.) — rather than only in
# ServiceBase._audit, so it also covers audit writers that bypass
# ServiceBase entirely.
#
# threading.local (not contextvars.ContextVar): mirrors
# persistence.tenancy.TenantContext, the codebase's existing pattern for
# request-scoped state. Django serves each request on a single thread
# (WSGI); the MCP SSE transport is async (mcp_server/views.py) but routes
# every sync call through asgiref's sync_to_async with the default
# thread_sensitive=True, which pins all sync calls for one async context to
# the same worker thread — the same guarantee TenantContext already relies
# on. A handler's ``with mcp_audit_handoff():`` block and the service call
# inside it always run synchronously on that one thread.
_audit_suppression = threading.local()


@contextlib.contextmanager
def mcp_audit_handoff():
    """Suppress :func:`log_write` for the wrapped call.

    Scope this tightly around ONLY the single inner service call whose audit
    entry would duplicate the caller's own ``write_mcp_audit()`` — never
    around an entire request/handler. Wrapping more than that inner call
    would silently drop any *other*, legitimate audit entry the same
    handler's call graph writes for a different entity (e.g. a TraceLink
    created alongside the primary entity) — those are not duplicates and
    must not be suppressed.
    """
    previous = getattr(_audit_suppression, "active", False)
    _audit_suppression.active = True
    try:
        yield
    finally:
        _audit_suppression.active = previous


# ---------------------------------------------------------------------------
# IF-AL-EXT-IN-001: log_write
# ---------------------------------------------------------------------------


def log_write(
    actor: str,
    actor_type: str,
    operation: str,
    entity_type: str,
    entity_id: UUID,
    version: Optional[int] = None,
    change_reason: Optional[str] = None,
    ctx: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[AuditEntry]:
    """Write an append-only audit log entry for a completed write operation.

    This is the primary entry point for COMP-AL-001 (AuditLogWriter). Callers
    must invoke this inside an active Django transaction.atomic() block so that
    a failure rolls back both the business entity and the audit entry
    (REQ-L2-AL-004).

    MCP callers provide ctx with source='mcp', client_name, and api_key.
    The api_key is hashed (SHA-256) before storage; the raw key is never
    persisted (REQ-L2-AL-002).

    Args:
        actor: User ID string or Agent/client ID string.
        actor_type: 'user' for human callers, 'agent' for MCP clients.
        operation: 'create' | 'update' | 'delete' | 'transition'.
        entity_type: Affected entity class name (e.g. 'Requirement').
        entity_id: UUID primary key of the affected entity.
        version: Entity version at time of operation (optional).
        change_reason: Optional human-readable reason (workflow transitions).
        ctx: Request context dict. MCP callers include:
             {'source': 'mcp', 'client_name': '...', 'api_key': '...'}
             REST callers may omit or pass {'source': 'rest'}.
        details: Reserved for v2 field-level diff (ADR-10). Ignored in v1.

    Returns:
        The newly created AuditEntry (INSERT only — never UPDATE), or
        ``None`` if the call was suppressed by an active
        :func:`mcp_audit_handoff` (Codeberg #313).

    Raises:
        MissingTenantContextError: If no active tenant context is set.
        RuntimeError: On DB failure (propagates for transaction rollback).
    """
    if getattr(_audit_suppression, "active", False):
        return None

    event = AuditableOperationOccurred(
        actor=actor,
        actor_type=actor_type,
        op=operation,
        entity_type=entity_type,
        entity_id=entity_id,
        version=version,
        change_reason=change_reason,
        ctx=ctx or {},
    )
    writer = get_writer()
    return writer.write(event)


# ---------------------------------------------------------------------------
# IF-AL-EXT-IN-002: query
# ---------------------------------------------------------------------------


def query(
    filters: Optional[AuditQueryFilters] = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> PaginatedAuditResult:
    """Query audit log entries with optional filters and pagination.

    Tenant isolation is enforced automatically via the active TenantContext.
    Results are sorted descending by timestamp (most recent first).

    Args:
        filters: Optional AuditQueryFilters specifying filter criteria.
                 All fields are optional; omitted fields are not applied.
        page: 1-based page number (default 1).
        page_size: Entries per page (default 50, max 200).

    Returns:
        PaginatedAuditResult with total count, page metadata, and entries.

    Raises:
        ValueError: If page_size > 200 or page < 1.
        TenantContextNotSetError: If no active tenant context is set.
    """
    return AuditLogQuery.query(filters=filters, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# Re-exports for downstream consumers
# ---------------------------------------------------------------------------

__all__ = [
    # Primary service functions
    "log_write",
    "query",
    # MCP audit handoff (Codeberg #313)
    "mcp_audit_handoff",
    # DTOs re-exported for caller convenience
    "AuditQueryFilters",
    "PaginatedAuditResult",
    # Model re-exported so callers can type-hint return values
    "AuditEntry",
]
