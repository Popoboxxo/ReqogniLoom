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
) -> AuditEntry:
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
        The newly created AuditEntry (INSERT only — never UPDATE).

    Raises:
        MissingTenantContextError: If no active tenant context is set.
        RuntimeError: On DB failure (propagates for transaction rollback).
    """
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
    # DTOs re-exported for caller convenience
    "AuditQueryFilters",
    "PaginatedAuditResult",
    # Model re-exported so callers can type-hint return values
    "AuditEntry",
]
