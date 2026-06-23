"""
ARCH-L1-012 AuditLog — Models.

TODO(COMP-AL-001): Implement AuditLogEntry model — append-only (no update/delete).
  Fields: id, tenant_id (FK), actor_type (user/agent), actor_id, actor_api_key_prefix,
  operation (create/update/delete/transition/etc.), entity_type, entity_id,
  timestamp (auto_now_add), details (JSONField, operation-level in v1),
  field_diff (JSONField, null=True — v2 extension, ADR-10).
  The model must NOT have an update() or delete() path in the manager.
TODO(COMP-AL-002): Implement AuditLogArchiveStrategy — partitioning or archiving
  policy for long-lived tenants (placeholder for v2, HOFF-20260621-004).

Reference: docs/se/L1/Gesamtsystem/L2/AuditLogSystem/L2_AuditLogSystem_Architecture.md
"""
from django.db import models  # noqa: F401
