"""
ARCH-L1-012 AuditLog — COMP-AL-001 AuditLogWriter.

Append-Only persistence of audit entries with atomic transaction support,
MCP enrichment, and tenant-ID injection.

Requirements:
- REQ-L2-AL-001 / REQ-L3-AL001-001 (Event-Bus subscription and field extraction)
- REQ-L2-AL-002 / REQ-L3-AL001-002 (MCP enrichment: client_name, api_key_hash SHA-256)
- REQ-L2-AL-003 / REQ-L3-AL001-003 (Append-Only: no update/delete method exposed)
- REQ-L2-AL-004 / REQ-L3-AL001-004 (atomic transaction with triggering operation)
- REQ-L2-AL-006 / REQ-L3-AL001-005 (tenant-ID injection from request context)

Architecture:
- docs/se/L1/Gesamtsystem/L2/AuditLogSystem/Components/
  COMP-AL-001_AuditLogWriter/L3_COMP-AL-001_AuditLogWriter_Architecture.md
- ADR-L3-AL001-01: Event-Bus-Subscriber pattern
- ADR-L3-AL001-02: SHA-256 hashing with 'sha256:' prefix for API keys
- ADR-L3-AL001-03: DB trigger for append-only constraint
- ADR-L3-AL001-04: Monthly RANGE partitioning (managed by PartitionManager)
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from persistence.tenancy import TenantContext, TenantContextNotSetError

from audit.events import AuditableOperationOccurred, DomainEventBus
from audit.models import AuditEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception for missing tenant context
# ---------------------------------------------------------------------------


class MissingTenantContextError(RuntimeError):
    """Raised when AuditLogWriter cannot resolve a tenant from context.

    REQ-L3-AL001-005: cross-tenant writes are not possible via the public
    write() API; missing context is a hard error.
    """


# ---------------------------------------------------------------------------
# ContextEnricher — ADR-L3-AL001-02
# ---------------------------------------------------------------------------


class ContextEnricher:
    """Extracts and enriches MCP-specific fields from the event context.

    REQ-L3-AL001-002: when actor_type is 'agent', extracts client_name and
    hashes api_key with SHA-256 using the 'sha256:' prefix. The raw key is
    never stored or logged.
    """

    @staticmethod
    def enrich(actor_type: str, ctx: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """Return enrichment fields for MCP context.

        Args:
            actor_type: 'user' or 'agent'.
            ctx: Raw event context dict. May contain 'api_key', 'client_name',
                 'source', and arbitrary forward-compatible extra fields.

        Returns:
            Dict with 'source', 'client_name', 'api_key_hash' ready for
            AuditEntry field assignment.
        """
        source = ctx.get("source", "rest")
        if actor_type != AuditEntry.ACTOR_TYPE_AGENT:
            return {
                "source": source if source in ("rest", "mcp") else "rest",
                "client_name": None,
                "api_key_hash": None,
            }

        # MCP agent path
        client_name: Optional[str] = ctx.get("client_name")
        raw_key: Optional[str] = ctx.get("api_key")
        api_key_hash: Optional[str] = None

        if raw_key:
            digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            api_key_hash = f"sha256:{digest}"
            # Ensure raw key is not retained in any local variable after this
            raw_key = None  # noqa: F841 (intentional clear)

        return {
            "source": "mcp",
            "client_name": client_name,
            "api_key_hash": api_key_hash,
        }


# ---------------------------------------------------------------------------
# TenantContextInjector — REQ-L3-AL001-005
# ---------------------------------------------------------------------------


class TenantContextInjector:
    """Resolves the active tenant from the thread-local TenantContext.

    REQ-L3-AL001-005: raises MissingTenantContextError if no tenant context
    is set, preventing cross-tenant writes.
    """

    @staticmethod
    def get_tenant_id() -> UUID:
        """Return the active tenant UUID.

        Returns:
            Active tenant primary key as UUID.

        Raises:
            MissingTenantContextError: If no tenant context is active.
        """
        try:
            return TenantContext.get_tenant()
        except TenantContextNotSetError as exc:
            raise MissingTenantContextError(
                "AuditLogWriter requires an active tenant context. "
                "Ensure TenantContext.set_tenant() was called before write()."
            ) from exc


# ---------------------------------------------------------------------------
# AuditLogWriter — COMP-AL-001 public API
# ---------------------------------------------------------------------------


class AuditLogWriter:
    """Append-only writer for AuditEntry records.

    Public API:
        write(event: AuditableOperationOccurred) -> AuditEntry

    No update_entry() or delete_entry() methods are exposed (REQ-L3-AL001-003).

    The writer is registered as a DomainEventBus subscriber at application
    startup via AuditConfig.ready() (REQ-L3-AL001-001).

    Transaction semantics (REQ-L2-AL-004):
        ``write()`` performs a direct ORM INSERT. It must be called from
        within an active Django transaction.atomic() block so that a failure
        rolls back both the business entity and the audit entry. The
        DomainEventBus.publish() contract guarantees this when called from
        ApplicationService inside an atomic block.
    """

    def __init__(self) -> None:
        self._enricher = ContextEnricher()
        self._tenant_injector = TenantContextInjector()

    def write(self, event: AuditableOperationOccurred) -> AuditEntry:
        """Persist an AuditEntry from a domain event.

        REQ-L3-AL001-001: Extracts all mandatory fields from the event.
        REQ-L3-AL001-002: MCP enrichment via ContextEnricher.
        REQ-L3-AL001-005: Tenant injected from TenantContext.

        Args:
            event: AuditableOperationOccurred containing all audit fields.

        Returns:
            The newly created AuditEntry instance (INSERT, never UPDATE).

        Raises:
            MissingTenantContextError: If no tenant context is active.
            RuntimeError: If the DB INSERT fails (propagates for TX rollback).
        """
        from persistence.models import Tenant

        tenant_id = self._tenant_injector.get_tenant_id()
        enrichment = self._enricher.enrich(event.actor_type, event.ctx)

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            raise MissingTenantContextError(
                f"Tenant with id={tenant_id} not found. Cannot write audit entry."
            )

        entry = AuditEntry(
            tenant=tenant,
            actor=event.actor,
            actor_type=event.actor_type,
            op=event.op,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            entity_version=event.version,
            change_reason=event.change_reason,
            source=enrichment["source"],
            client_name=enrichment["client_name"],
            api_key_hash=enrichment["api_key_hash"],
        )
        # Use full_clean to validate choices/constraints before INSERT
        entry.full_clean(exclude=["timestamp"])
        # Bypass the append-only save guard (pk is None for new entries)
        AuditEntry.unscoped.model.save(entry)
        logger.debug(
            "AuditLogWriter: wrote entry id=%s actor=%s op=%s entity=%s:%s",
            entry.pk,
            entry.actor,
            entry.op,
            entry.entity_type,
            entry.entity_id,
        )
        return entry

    # ------------------------------------------------------------------
    # DomainEventBus subscriber handler
    # ------------------------------------------------------------------

    def handle_event(self, event: AuditableOperationOccurred) -> None:
        """DomainEventBus subscriber callback.

        REQ-L3-AL001-001: registered in AuditConfig.ready(). Called by
        DomainEventBus.publish() within the active transaction.

        Args:
            event: The published AuditableOperationOccurred.
        """
        self.write(event)


# ---------------------------------------------------------------------------
# Module-level singleton — registered in AuditConfig.ready()
# ---------------------------------------------------------------------------

_writer_instance: Optional[AuditLogWriter] = None


def get_writer() -> AuditLogWriter:
    """Return the module-level AuditLogWriter singleton."""
    global _writer_instance
    if _writer_instance is None:
        _writer_instance = AuditLogWriter()
    return _writer_instance


def register_writer_on_event_bus() -> None:
    """Register the AuditLogWriter singleton as a DomainEventBus subscriber.

    Called from AuditConfig.ready() so registration happens exactly once at
    application startup (REQ-L3-AL001-001).
    """
    writer = get_writer()
    DomainEventBus.subscribe(writer.handle_event)
    logger.info("AuditLogWriter registered on DomainEventBus.")


__all__ = [
    "MissingTenantContextError",
    "ContextEnricher",
    "TenantContextInjector",
    "AuditLogWriter",
    "get_writer",
    "register_writer_on_event_bus",
]
