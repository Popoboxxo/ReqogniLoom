"""
ARCH-L1-012 AuditLog — COMP-AL-002 AuditLogQuery.

Filterable, paginated query interface for AuditEntry records with tenant
isolation and a memory-efficient export cursor for COMP-AL-003.

Requirements:
- REQ-L2-AL-005 / REQ-L3-AL002-001 (filterable, paginated query interface)
- REQ-L2-AL-006 / REQ-L3-AL002-002 (tenant isolation via TenantScopedModel manager)
- REQ-L2-AL-007 / REQ-L3-AL002-003 (performance via indexes)
- REQ-L2-AL-009 / REQ-L3-AL002-004 (paginated export cursor for ArchiveLifecycleManager)

Architecture:
- docs/se/L1/Gesamtsystem/L2/AuditLogSystem/Components/
  COMP-AL-002_AuditLogQuery/L3_COMP-AL-002_AuditLogQuery_Architecture.md
- ADR-L3-AL002-01: Custom Manager for tenant isolation
- ADR-L3-AL002-02: multi-field filter with AND logic
- ADR-L3-AL002-03: paginated export cursor (generator/iterator)

Interfaces:
- IF-AL-EXT-IN-002: incoming query request from ApplicationService/UI
- IF-AL-INT-001: shared AuditEntry model from COMP-AL-001
- IF-AL-INT-002: get_entries_before() called by COMP-AL-003 (internal only)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Iterator, List, Optional, Sequence
from uuid import UUID

from audit.models import AuditEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 200
EXPORT_CHUNK_SIZE: int = 500


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class AuditQueryFilters:
    """Filter parameters for AuditLogQuery.query().

    All fields are optional; omitted fields are not applied as filters.
    """

    entity_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    actor: Optional[str] = None
    operation: Optional[str] = None
    source: Optional[str] = None
    timestamp_from: Optional[datetime] = None
    timestamp_to: Optional[datetime] = None
    # Fix #572 (review F1): additive multi-id filter. Distinct from entity_id
    # (single-id, pre-existing) — callers that need to restrict to a known
    # *set* of entities (e.g. "all Requirements in workspace X") apply that
    # restriction at the DB level via entity_id__in instead of fetching a
    # truncated tenant-wide page and filtering it in Python, which silently
    # under-counts once a tenant's total entry volume for the period exceeds
    # the query's page budget.
    entity_ids: Optional[Sequence[UUID]] = None


@dataclass
class PaginatedAuditResult:
    """Paginated result wrapper for audit log queries.

    REQ-L3-AL002-001: entries are sorted DESC by timestamp.
    """

    total: int
    page: int
    page_size: int
    entries: List[AuditEntry]


# ---------------------------------------------------------------------------
# AuditLogQuery — COMP-AL-002
# ---------------------------------------------------------------------------


class AuditLogQuery:
    """Read-only query interface for AuditEntry records.

    Public API (IF-AL-EXT-IN-002):
        query(filters, page, page_size) -> PaginatedAuditResult

    Internal API (IF-AL-INT-002, COMP-AL-003 only):
        get_entries_before(cutoff_timestamp, page_size) -> Iterator[AuditEntry]

    Tenant isolation is automatic via AuditEntry.objects (AppendOnlyManager
    inherits TenantManager, which injects the tenant filter from TenantContext).
    Missing tenant context raises TenantContextNotSetError before any SQL.
    """

    # ------------------------------------------------------------------
    # Public query interface — IF-AL-EXT-IN-002
    # ------------------------------------------------------------------

    @staticmethod
    def query(
        filters: Optional[AuditQueryFilters] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedAuditResult:
        """Return a paginated, filtered list of AuditEntry records.

        REQ-L3-AL002-001: supports entity_id, entity_type, actor, operation,
        source, timestamp range filters. Results sorted DESC by timestamp.
        Tenant isolation is enforced via the default manager.

        Args:
            filters: Optional AuditQueryFilters instance. None means no filters.
            page: 1-based page number.
            page_size: Entries per page. Default 50, max 200.

        Returns:
            PaginatedAuditResult with total count and current page entries.

        Raises:
            ValueError: If page_size > MAX_PAGE_SIZE or page < 1.
            TenantContextNotSetError: If no tenant context is active (via manager).
        """
        if page_size > MAX_PAGE_SIZE:
            raise ValueError(
                f"page_size={page_size} exceeds maximum of {MAX_PAGE_SIZE}."
            )
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}.")

        qs = AuditEntry.objects.all()

        if filters:
            qs = AuditLogQuery._apply_filters(qs, filters)

        qs = qs.order_by("-timestamp")
        total = qs.count()
        offset = (page - 1) * page_size
        entries = list(qs[offset : offset + page_size])

        return PaginatedAuditResult(
            total=total,
            page=page,
            page_size=page_size,
            entries=entries,
        )

    @staticmethod
    def _apply_filters(qs, filters: AuditQueryFilters):
        """Build ORM filter chain from AuditQueryFilters.

        ADR-L3-AL002-02: optional parameters combined with AND logic via
        Django QuerySet.filter() chaining.
        """
        if filters.entity_id is not None:
            qs = qs.filter(entity_id=filters.entity_id)
        if filters.entity_ids is not None:
            qs = qs.filter(entity_id__in=filters.entity_ids)
        if filters.entity_type is not None:
            qs = qs.filter(entity_type=filters.entity_type)
        if filters.actor is not None:
            qs = qs.filter(actor=filters.actor)
        if filters.operation is not None:
            qs = qs.filter(op=filters.operation)
        if filters.source is not None:
            qs = qs.filter(source=filters.source)
        if filters.timestamp_from is not None:
            qs = qs.filter(timestamp__gte=filters.timestamp_from)
        if filters.timestamp_to is not None:
            qs = qs.filter(timestamp__lte=filters.timestamp_to)
        return qs

    # ------------------------------------------------------------------
    # Internal export cursor — IF-AL-INT-002 (COMP-AL-003 only)
    # ------------------------------------------------------------------

    @staticmethod
    def get_entries_before(
        cutoff_timestamp: datetime,
        page_size: int = EXPORT_CHUNK_SIZE,
    ) -> Generator[AuditEntry, None, None]:
        """Stream AuditEntry records older than cutoff_timestamp.

        REQ-L3-AL002-004: memory-efficient generator using Django's
        .iterator() to avoid loading all rows into RAM. Designed for the
        ArchiveLifecycleManager (IF-AL-INT-002).

        This method is INTERNAL and must NOT be exposed via the public
        query interface (REQ-L3-AL002-004 AC: not in external query interface).

        Note: This uses AuditEntry.unscoped because the ArchiveLifecycleManager
        operates in a system/maintenance context without a request-scoped tenant.
        Individual tenants' data is included in the export as-is (all tenants).

        Args:
            cutoff_timestamp: Export entries with timestamp strictly before this.
            page_size: Chunk size for the iterator (default 500).

        Yields:
            AuditEntry instances in ascending timestamp order (oldest first
            for sequential export).
        """
        qs = (
            AuditEntry.unscoped.filter(timestamp__lt=cutoff_timestamp)
            .order_by("timestamp")
            .iterator(chunk_size=page_size)
        )
        yield from qs


__all__ = [
    "AuditQueryFilters",
    "PaginatedAuditResult",
    "AuditLogQuery",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
]
