"""
COMP-RO-005 ResilienceAuditLogger — forwards resilience events to the AuditLog.

Receives in-process resilience events from the CircuitBreaker (IF-RO-INT-005,
``log_state_change``) and the DegradationManager (IF-RO-INT-006, degradation
events) and forwards them as structured entries to the AuditLog system
(ARCH-L1-012) via its public facade ``audit.services.log_write`` (IF-L1-052).

Requirements:
- REQ-L3-RO-005-01 (circuit state-change logging)
- REQ-L3-RO-005-02 (degradation-event logging)
- REQ-L3-RO-005-03 (non-blocking: failures in the audit path never propagate to
  the caller)

Interfaces:
- IF-RO-INT-005 (input)  : log_state_change(target, old_state, new_state)
- IF-RO-INT-006 (input)  : log_degradation(...)
- IF-L1-052     (output) : audit.services.log_write

Traceability: REQ-L2-RO-006 -> REQ-L1-032
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import transaction

from audit.models import AuditEntry
from audit.services import log_write

logger = logging.getLogger("resilience.audit")

# AuditEntry.op is a constrained choice set owned by the AuditLog system
# (create/update/delete/transition). Resilience events are not domain writes, so
# we map every resilience event to ``transition`` (the closest semantic: a state
# transition of an external-call lifecycle) and carry the precise event type in
# change_reason / ctx. Changing the AuditEntry choice set is out of scope and would
# require an interface change to ARCH-L1-012 (escalation, not a unilateral edit).
_RESILIENCE_OP = AuditEntry.OP_TRANSITION
_ENTITY_TYPE = "ResilienceEvent"
_ACTOR = "resilience-orchestrator"
_ACTOR_TYPE = AuditEntry.ACTOR_TYPE_AGENT


def _stable_entity_id(target_subsystem: str) -> UUID:
    """Derive a deterministic UUID for a target so audit rows group per target.

    AuditEntry.entity_id is a non-null UUID; resilience events have no natural
    entity PK, so we derive one stably from the target name.
    """
    return uuid5(NAMESPACE_URL, f"resilience-target:{target_subsystem}")


def log_state_change(
    target_subsystem: str,
    old_state: str,
    new_state: str,
) -> None:
    """IF-RO-INT-005: record a circuit-breaker state transition.

    REQ-L3-RO-005-01: forwards target, old/new state and timestamp (the
    AuditEntry timestamp is auto-set at INSERT) to the AuditLog.
    REQ-L3-RO-005-03: never raises — a failure in the audit path must not affect
    the breaker's latency or correctness.

    Args:
        target_subsystem: External target whose breaker changed state.
        old_state: Previous circuit state.
        new_state: New circuit state.
    """
    _safe_write(
        change_reason=f"circuit_state_change:{old_state}->{new_state}",
        target_subsystem=target_subsystem,
        ctx={
            "event": "circuit_state_change",
            "target": target_subsystem,
            "old_state": old_state,
            "new_state": new_state,
        },
    )


def log_degradation(
    target_subsystem: str,
    error_code: str | None,
    reason: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """IF-RO-INT-006: record a graceful-degradation event.

    REQ-L3-RO-005-02: forwards error code, target, trigger and timestamp.
    REQ-L3-RO-005-03: never raises.

    Args:
        target_subsystem: Target that failed and triggered degradation.
        error_code: Optional machine-readable error code.
        reason: Human-readable trigger description.
        detail: Optional extra context.
    """
    _safe_write(
        change_reason=f"degradation:{reason}",
        target_subsystem=target_subsystem,
        ctx={
            "event": "degradation",
            "target": target_subsystem,
            "error_code": error_code,
            "reason": reason,
            "detail": detail or {},
        },
    )


def _safe_write(
    change_reason: str,
    target_subsystem: str,
    ctx: dict[str, Any],
) -> None:
    """Write to the AuditLog, swallowing any error (REQ-L3-RO-005-03).

    The forwarding is best-effort and non-blocking with respect to correctness:
    if the AuditLog write fails, we log a warning locally instead of propagating,
    so resilience callers (CircuitBreaker, DegradationManager) are never impacted.

    When an atomic block is active (the normal case — ``CircuitBreaker`` calls
    ``log_state_change`` from inside its own ``transaction.atomic()``), the write
    is deferred with ``transaction.on_commit``. A DB-level failure in the audit
    backend would otherwise mark the *enclosing business transaction* as needing
    rollback and turn the breaker's own commit into a ``TransactionManagementError``
    — a best-effort side effect must never take down the operation it observes.
    Outside an atomic block the write runs directly (the on-commit fallback for
    callers with no DB transaction), with the same error swallowing.
    """
    def _write() -> None:
        try:
            log_write(
                actor=_ACTOR,
                actor_type=_ACTOR_TYPE,
                operation=_RESILIENCE_OP,
                entity_type=_ENTITY_TYPE,
                entity_id=_stable_entity_id(target_subsystem),
                change_reason=change_reason,
                ctx={"source": "resilience", **ctx},
            )
        except Exception:  # noqa: BLE001 — best-effort audit must never break callers
            logger.warning(
                "ResilienceAuditLogger failed to forward event for target=%s reason=%s",
                target_subsystem,
                change_reason,
                exc_info=True,
            )

    if transaction.get_connection().in_atomic_block:
        # Defer past the breaker's commit: audit failures cannot poison it.
        transaction.on_commit(_write)
    else:
        # No active transaction (e.g. a plain in-process caller) — write now.
        _write()
