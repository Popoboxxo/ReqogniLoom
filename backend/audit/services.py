"""
ARCH-L1-012 AuditLog — Service stubs.

TODO(COMP-AL-001): Implement AuditLogService with:
  - log_write(actor, operation, entity_type, entity_id, details, tenant_id) -> None
  - query_changes(workspace_id, timeframe) -> QuerySet[AuditLogEntry]
    (used by SeMetrics for volatility calculation, IF-L1-044)

Reference: docs/se/L1/Gesamtsystem/L2/AuditLogSystem/L2_AuditLogSystem_Architecture.md
"""
