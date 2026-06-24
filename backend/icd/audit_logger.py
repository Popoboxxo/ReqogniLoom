"""
IcdManagement — AuditLogger (COMP-ICD-004).

leaf_id: COMP-ICD-004
req_id:  REQ-L1-028, REQ-L2-ICD-006
arch_id: ARCH-L1-014
IF:      IF-ICD-INT-003 (IcdManager -> AuditLogger)
         IF-L1-041 (AuditLogger -> AuditLog)

Adapter that formats ICD breaking-change events and submits them to the
external AuditLog system via audit.services.log_write (IF-L1-041).

The caller (IcdManager) invokes log_breaking_change inside the same atomic
transaction, so the audit entry is rolled back together with the business
operation if the transaction fails (REQ-L2-AL-004 pattern).
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)

# Event type constant (matches AuditEventDTO specification from L3 arch doc)
_EVENT_TYPE = "ICD_BREAKING_CHANGE"
_SOURCE_SYSTEM = "IcdManagementSystem"
_SEVERITY = "WARNING"


class AuditLogger:
    """Adapter for writing ICD breaking-change events to the AuditLog.

    leaf_id: COMP-ICD-004
    req_id:  REQ-L2-ICD-006
    IF:      IF-ICD-INT-003 (called by IcdManager)
             IF-L1-041 (calls audit.services.log_write)
    """

    def log_breaking_change(
        self,
        icd_id: uuid.UUID,
        details: str,
        actor: str = _SOURCE_SYSTEM,
    ) -> None:
        """Write a breaking-change audit event for the given ICD.

        Constructs a structured audit event and delegates to audit.services.log_write.
        The entry is append-only; no update or delete path exists in the AuditLog.

        Args:
            icd_id:  UUID of the ICD that has a breaking change.
            details: Human-readable description of what broke (from ValidationResult).
            actor:   Logical actor string; defaults to the system identifier.

        Raises:
            Any exception from audit.services.log_write is propagated to allow
            the calling transaction to roll back.

        req_id: REQ-L2-ICD-006
        IF:     IF-ICD-INT-003, IF-L1-041
        """
        # Deferred import to avoid circular imports at module load time.
        from audit.services import log_write

        logger.warning(
            "ICD breaking change detected: icd=%s — %s", icd_id, details
        )
        log_write(
            actor=actor,
            actor_type="agent",
            operation="update",
            entity_type="Icd",
            entity_id=icd_id,
            change_reason=f"{_SEVERITY}: {_EVENT_TYPE}",
            details={
                "source_system": _SOURCE_SYSTEM,
                "event_type": _EVENT_TYPE,
                "severity": _SEVERITY,
                "breaking_change_details": details,
            },
        )


# Module-level singleton — IcdManager uses this instance (IF-ICD-INT-003)
_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Return the module-level AuditLogger singleton.

    leaf_id: COMP-ICD-004
    """
    return _audit_logger


__all__ = [
    "AuditLogger",
    "get_audit_logger",
]
