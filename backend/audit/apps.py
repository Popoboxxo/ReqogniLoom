"""App configuration for ARCH-L1-012 AuditLog."""
from django.apps import AppConfig


class AuditConfig(AppConfig):
    """ARCH-L1-012 AuditLog — Append-only Change History.

    Responsibilities:
    - Append-only log of all write operations via REST and MCP.
    - Captures: actor (User or Agent-Client + API Key), operation, entity_id,
      timestamp, optional field-diff.
    - In v1: operation-level logging. Field-level diff as v2 extension (ADR-10).
    - Written by ApplicationService after every write operation.

    See: docs/se/L1/Gesamtsystem/L2/AuditLogSystem/L2_AuditLogSystem_Architecture.md
    REQ-L1: REQ-L1-011 (Audit trail)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "ARCH-L1-012 AuditLog"
