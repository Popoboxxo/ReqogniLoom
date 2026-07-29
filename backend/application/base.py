"""
ApplicationService — ServiceBase and shared utilities.

leaf_id : ApplicationService Foundation
req_id  : REQ-L2-AS-018 (ACID), REQ-L2-AS-019 (Audit), REQ-L2-AS-021 (Auth),
          REQ-L2-AS-022 (Tenant), REQ-L2-AS-023 (Performance)

ServiceBase is the common ancestor for all CRUD-oriented domain services in
the ApplicationServiceSystem. Subclasses (ArtifactService, RequirementService,
…) inherit:

  - _assert_permission(ctx, required_role): RBAC gate
  - _set_tenant_context(ctx): thread-local propagation for ORM queries
  - _emit_event(event): schedules a DomainEvent in the on_commit hook
  - _audit(ctx, operation, entity_type, entity_id, **kw): synchronous AuditLog
    write inside the current transaction (MVP path; async path via event bus)

Extension pattern for Steps 2+3:
  1. Create e.g. backend/application/services_step2.py
  2. Define new service classes that inherit from ServiceBase.
  3. Import them in backend/application/services.py (the thin re-export facade)
     without modifying the existing imports:

       # services.py (unchanged existing imports stay)
       from application.services_step2 import NewService
       __all__ += ["NewService"]

  Do NOT modify ServiceBase or any file in this module for new services.

Reference:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    L2_ApplicationServiceSystem_Architecture.md  (ADR-AS-01)
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

from application.event_bus import DomainEvent, get_event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class PermissionDeniedError(PermissionError):
    """Raised when an operation is attempted without the required role."""


class NotFoundError(LookupError):
    """Raised when a requested entity does not exist in the active tenant."""


class ValidationError(ValueError):
    """Raised when domain validation fails (cycle detection, missing fields, …)."""


class OptimisticLockError(RuntimeError):
    """Raised when an update targets a stale version (REQ-L2-AS-004)."""


class LlmNotConfiguredError(RuntimeError):
    """Raised when an LLM capability is requested but no provider is configured."""


# ---------------------------------------------------------------------------
# ServiceBase
# ---------------------------------------------------------------------------


class ServiceBase:
    """Abstract base for all ApplicationService domain services.

    Provides cross-cutting capabilities:
      - Auth/permission assertion (REQ-L2-AS-021)
      - Tenant context propagation (REQ-L2-AS-022)
      - AuditLog write shortcut (REQ-L2-AS-019)
      - DomainEvent emission via Transactional Outbox (REQ-L2-AS-029)

    Convention: all public write methods must call _set_tenant_context(ctx)
    at entry and wrap the DB operations in @atomic_transaction (via
    persistence.transactions) or an explicit TransactionContextManager.
    """

    # ---------- Auth / Permission ----------

    @staticmethod
    def _assert_permission(ctx: AuthContext, required_role: str) -> None:
        """Raise PermissionDeniedError if ctx does not have *required_role*.

        REQ-L2-AS-021: Auth context is forwarded and checked before any operation.
        """
        if not ctx.has_role(required_role):
            raise PermissionDeniedError(
                f"Permission denied: role '{required_role}' required, "
                f"user has {ctx.active_roles}"
            )

    @staticmethod
    def _assert_write_permission(ctx: AuthContext) -> None:
        """Raise PermissionDeniedError unless *ctx* holds a role that permits WRITE.

        Positive check against the RBAC matrix (AuthorizationService), not a
        deny-list of known-bad role sets: an empty role tuple (no UserRole row
        resolved) or any role unrecognised by the matrix is fail-closed, i.e.
        denied, instead of silently allowed. This is the last line of defence
        for all callers in application/*_service.py (REQ-L2-AS-021).

        Imported lazily: auth_tenancy.services.__init__ imports
        auth_tenancy.services.item_permission, which imports
        application.base.ServiceBase — a module-level import here would
        create a circular import at package-init time.
        """
        from auth_tenancy.services.authorization import AuthorizationService, Operation

        decision = AuthorizationService().decide_access(
            ctx.active_roles, Operation.WRITE
        )
        if not decision.allow:
            raise PermissionDeniedError(
                f"Permission denied: write operation requires at least 'editor' "
                f"role, user has {ctx.active_roles}"
            )

    # ---------- Tenant Context ----------

    @staticmethod
    def _set_tenant_context(ctx: AuthContext) -> None:
        """Propagate tenant_id from *ctx* into the thread-local ORM filter.

        REQ-L2-AS-022: Every DB query is scoped to the active tenant.
        """
        TenantContext.set_tenant(ctx.tenant_id)

    # ---------- AuditLog ----------

    @staticmethod
    def _audit(
        ctx: AuthContext,
        operation: str,
        entity_type: str,
        entity_id: UUID,
        change_reason: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Write a synchronous AuditLog entry inside the current transaction.

        REQ-L2-AS-019: Every write operation produces an audit entry.
        The entry is written in the same transaction as the mutation;
        a rollback removes both (atomic consistency, REQ-L2-AL-004).
        """
        try:
            from audit.services import log_write

            log_write(
                actor=str(ctx.user_id),
                actor_type="user",
                operation=operation,
                entity_type=entity_type,
                entity_id=entity_id,
                change_reason=change_reason,
                details=details,
            )
        except Exception:
            logger.exception(
                "ServiceBase._audit: failed to write audit entry "
                "op=%s entity_type=%s entity_id=%s",
                operation,
                entity_type,
                entity_id,
            )
            raise

    # ---------- DomainEvent emission ----------

    @staticmethod
    def _emit_event(event: DomainEvent) -> None:
        """Schedule *event* for post-commit outbox insertion.

        Transaction boundary (REQ-073, see docs/ARCHITECTURE.md):
        Domain events fire *after* the surrounding transaction commits. The
        outbox row is written in a ``transaction.on_commit`` hook, so a rolled
        back transaction never produces an event. Contrast with ``_audit``,
        which writes synchronously inside the same transaction.

        REQ-L2-AS-029: Event is atomically bound to the current transaction.
        Must be called inside an active transaction.atomic() block.
        """
        get_event_bus().publish(event)

    # ---------- Helpers ----------

    @staticmethod
    def _make_event(
        event_type: str,
        entity_id: UUID,
        workspace_id: UUID,
        payload: Optional[dict] = None,
    ) -> DomainEvent:
        """Construct a DomainEvent with optional extra payload."""
        return DomainEvent(
            event_type=event_type,
            entity_id=entity_id,
            workspace_id=workspace_id,
            payload=payload or {},
        )


__all__ = [
    "ServiceBase",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "OptimisticLockError",
    "LlmNotConfiguredError",
]
