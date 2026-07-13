"""
ARCH-L1-012 AuditLog — Application configuration.

Registers AuditLogWriter as a DomainEventBus subscriber at application startup
(REQ-L3-AL001-001: subscribe to AuditableOperationOccurred on DomainEventBus).
"""
from django.apps import AppConfig


class AuditConfig(AppConfig):
    """ARCH-L1-012 AuditLog — Append-only Change History.

    Responsibilities:
    - Append-only log of all write operations via REST and MCP.
    - Captures: actor (User or Agent-Client + API Key), operation, entity_id,
      timestamp, optional field-diff.
    - In v1: operation-level logging. Field-level diff as v2 extension (ADR-10).
    - Written by ApplicationService after every write operation via DomainEventBus.

    See: docs/se/L1/Gesamtsystem/L2/AuditLogSystem/L2_AuditLogSystem_Architecture.md
    REQ-L1: REQ-L1-011 (Audit trail)
    COMP: COMP-AL-001 (AuditLogWriter), COMP-AL-002 (AuditLogQuery),
          COMP-AL-003 (ArchiveLifecycleManager)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "ARCH-L1-012 AuditLog"

    def ready(self) -> None:
        """Register AuditLogWriter on the DomainEventBus at startup.

        REQ-L3-AL001-001: AuditLogWriter subscribes to AuditableOperationOccurred
        events at application startup via this hook.
        """
        from audit.writer import register_writer_on_event_bus

        register_writer_on_event_bus()
