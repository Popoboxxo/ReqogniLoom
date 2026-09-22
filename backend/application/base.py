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
  - _emit_event(event): writes a DomainEvent to the outbox in the current
    transaction (SA-02 — was previously deferred to an on_commit hook)
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
from typing import Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError
from persistence.tenancy import TenantContext

from application.event_bus import DomainEvent, get_event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
#
# PermissionDeniedError, NotFoundError and ValidationError now live in
# persistence/errors.py (Layer 0) — re-exported here unchanged so every
# existing `from application.base import NotFoundError` (etc.) keeps working.
# See persistence/errors.py's module docstring for why (SYSTEMAUDIT_2026-08-27
# P1-12).
# ---------------------------------------------------------------------------


class BaselineGateBlockedError(ValidationError):
    """Raised when the SE-Auditor gate refuses a baseline build (GH-513).

    A ``ValidationError`` subclass so every existing ``except ValidationError``
    caller (REST views, MCP tools, ChangeRequestService) keeps behaving exactly
    as before, but a *distinct* type so the API layer can answer a dedicated
    error code. That code is what lets a client tell the two dead ends apart:

      * this one — known BLOCKER findings, resolvable either by fixing them or
        by re-sending the request with a documented ``override_reason``;
      * a plain ``ValidationError`` from the same gate — the auditor itself
        could not be evaluated (GH-400 fail-closed), which is *not* waivable.

    Note for the REST layer: ``_service_error_response`` maps exception types
    by exact identity, not ``isinstance`` — a new subclass MUST be registered
    in ``_EXC_TO_HTTP``/``_EXC_TO_CODE`` or it degrades to a 500.
    """


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

        Codeberg #313: this call is a silent no-op while an
        ``audit.services.mcp_audit_handoff()`` context is active on the
        current thread — an MCP tool handler uses that to suppress this
        entry for the one service call whose write it is about to
        re-log itself (with MCP enrichment) via
        ``mcp_server.tools.base.write_mcp_audit``. See
        ``audit.services.log_write`` for the actual check.
        """
        try:
            from audit.services import log_write

            # Spec §3: the actor type is decided at the auth layer (an ApiKey
            # with principal_type="agent"), not reconstructed here. Previously
            # hardcoded to "user", which made every agent write look human.
            #
            # Defensive fallback: countless existing unit tests construct
            # `ctx` as a bare MagicMock() without setting .actor_type, which
            # was harmless while this method never read it. A Mock's
            # auto-generated attribute is not "user"/"agent", and AuditEntry
            # enforces that choice via full_clean() — normalize here rather
            # than let an audit-log field the caller never meant to control
            # fail an otherwise-valid business operation.
            actor_type = ctx.actor_type if ctx.actor_type in ("user", "agent") else "user"
            # #399: `details` is now persisted (ADR-10 groundwork) instead of
            # being dropped by the v1 writer. The agent label used to be merged
            # into a details dict even when the caller passed none, which was
            # harmless while details was ignored — now it would add a payload
            # to every agent write. Only enrich an existing payload so
            # "no details" still stores SQL NULL (default behaviour unchanged).
            audit_details = details
            if details is not None and actor_type == "agent" and ctx.agent_label:
                audit_details = {**details, "client_name": ctx.agent_label}

            log_write(
                actor=str(ctx.user_id),
                actor_type=actor_type,
                operation=operation,
                entity_type=entity_type,
                entity_id=entity_id,
                change_reason=change_reason,
                details=audit_details,
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

    # ---------- Baseline drift (#399) ----------

    @staticmethod
    def _baseline_drift_details(
        artifact_id: UUID, ctx: AuthContext
    ) -> Optional[dict]:
        """Return ``{"baseline_drift": [...]}`` for an edit's audit entry.

        #399 (cluster 5, decision D1): membership in a baseline produces a
        visible drift marking, not a hard block. The *audit trail* is where the
        marking is durable, so every edit of a baselined artifact records which
        baselines it drifted from.

        Fail-open on purpose: drift detection is a label, not an approval, so
        an error while computing it must never fail the edit
        (``logger.exception`` and ``None`` = "no drift details").

        Returns ``None`` when the artifact is in no baseline, when nothing
        drifted, or when detection failed.

        The payload is persisted on the edit's ``AuditEntry.details`` (nullable
        JSON, ADR-10 groundwork — see ``audit.models.AuditEntry.details``), so
        the marking outlives the request. The drift summary is separately
        observable via ``GET /artifacts/{id}/baseline-membership/``.
        """
        try:
            from application.baseline_facade import BaselineFacade

            memberships = BaselineFacade().memberships_for_artifact(
                artifact_id, ctx
            )
        except Exception:  # noqa: BLE001 — never fail the edit for a label
            logger.exception(
                "ServiceBase._baseline_drift_details: drift lookup failed for %s",
                artifact_id,
            )
            return None

        drifted = [m for m in memberships if m.drifted]
        if not drifted:
            return None
        return {
            "baseline_drift": [
                {
                    "baseline_id": str(m.baseline_id),
                    "scope": m.scope,
                    "baselined_version": m.baselined_version,
                    "current_version": m.current_version,
                    "drift_known": m.drift_known,
                }
                for m in drifted
            ]
        }

    # ---------- DomainEvent emission ----------

    @staticmethod
    def _emit_event(event: DomainEvent) -> None:
        """Write *event* to the outbox inside the current transaction.

        Transaction boundary (REQ-073, see docs/ARCHITECTURE.md):
        the outbox row is INSERTed synchronously, in the same transaction as the
        mutation — exactly like ``_audit``. A rolled back transaction therefore
        produces no event, and a crash cannot separate the two. *Delivery* to
        subscribers still happens asynchronously afterwards, driven by
        ``application.dispatch_outbox_events``.

        SA-02: this used to defer the INSERT to a ``transaction.on_commit``
        hook, which left a window between COMMIT and the callback in which a
        crash lost the event permanently.

        Must be called inside an active ``transaction.atomic()`` block. Failures
        of the outbox INSERT propagate and roll the caller's mutation back —
        see ``DomainEventBus.publish``.

        REQ-L2-AS-029: Event is atomically bound to the current transaction.
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
    "BaselineGateBlockedError",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "OptimisticLockError",
    "LlmNotConfiguredError",
]
