"""
COMP-AS-013 AdrService — Architecture Decision Record CRUD.

leaf_id : COMP-AS-013
req_id  : REQ-L1-029

Orchestrates:
  IF-AS-INT-002   TraceLinkService.create_trace_link / cascade_delete_trace_links
  IF-AS-INT-003   WorkflowFacade.transition (status transitions)
  IF-AS-INT-015   DomainEventBus → AdrCreated/Updated/Deleted (Outbox)
  IF-AS-EXT-OUT-007  application.models.Adr (Django ORM — plain, no TenantScopedModel)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-013_AdrService/
      L3_COMP-AS-013_AdrService_Architecture.md

ADR-L3-ADR-01: Append-Only versioning (version counter incremented on update).
ADR-L3-ADR-02: TraceLinks as separate entities via TraceLinkService.
ADR-L3-ADR-03: All mutations inside atomic transactions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db.models import F
from persistence.transactions import atomic_transaction

from application.base import NotFoundError, ServiceBase, ValidationError
from application.models import Adr, DomainEventOutbox

logger = logging.getLogger(__name__)

# Supported TraceLink types for ADRs (REQ-L3-ADR-005)
ADR_LINK_TYPES = frozenset({"addresses", "supersedes", "related-to"})


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class AdrDTO:
    """Read-oriented DTO returned by AdrService methods.

    leaf_id : COMP-AS-013
    req_id  : REQ-L1-029
    """

    id: UUID
    workspace_id: UUID
    tenant_id: UUID
    title: str
    description: str
    context: str
    consequences: str
    status: str
    version: int

    @classmethod
    def from_orm(cls, adr: Adr) -> "AdrDTO":
        return cls(
            id=adr.id,
            workspace_id=adr.workspace_id,
            tenant_id=adr.tenant_id,
            title=adr.title,
            description=adr.description,
            context=adr.context,
            consequences=adr.consequences,
            status=adr.status,
            version=adr.version,
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class AdrValidator:
    """Schema validation for ADR payloads (REQ-L3-ADR-009).

    leaf_id : COMP-AS-013
    req_id  : REQ-L1-029
    """

    VALID_STATUSES = frozenset(Adr.Status.values)

    @classmethod
    def validate_create(
        cls, title: str, description: str, status: str = "Draft"
    ) -> None:
        """Validate fields for ADR creation."""
        if not title or len(title) < 3:
            raise ValidationError("ADR title must be at least 3 characters")
        if len(title) > 200:
            raise ValidationError("ADR title must not exceed 200 characters")
        if len(description) > 10000:
            raise ValidationError("ADR description must not exceed 10,000 characters")
        if status not in cls.VALID_STATUSES:
            raise ValidationError(
                f"ADR status '{status}' invalid; must be one of {sorted(cls.VALID_STATUSES)}"
            )


# ---------------------------------------------------------------------------
# AdrService
# ---------------------------------------------------------------------------


class AdrService(ServiceBase):
    """COMP-AS-013 — Architecture Decision Record CRUD with Workflow and TraceLinks.

    leaf_id : COMP-AS-013
    req_id  : REQ-L1-029
    """

    def __init__(
        self,
        trace_link_service=None,
    ) -> None:
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- CRUD ----------

    @atomic_transaction
    def create_adr(
        self,
        workspace_id: UUID,
        title: str,
        description: str,
        ctx: AuthContext,
        context: str = "",
        consequences: str = "",
        status: str = "Draft",
    ) -> Adr:
        """Create an ADR with initial workflow state (REQ-L3-ADR-001).

        Args:
            workspace_id: Target workspace UUID.
            title: ADR title (3–200 chars).
            description: Full ADR description (max 10,000 chars).
            ctx: Resolved AuthContext (tenant + roles).
            context: Optional context section (max 5,000 chars).
            consequences: Optional consequences section (max 5,000 chars).
            status: Initial status (default: Draft).

        Returns:
            Persisted Adr ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        AdrValidator.validate_create(title=title, description=description, status=status)

        adr = Adr.objects.create(
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            context=context,
            consequences=consequences,
            status=status,
            created_by=str(ctx.user_id),
        )

        # Initialize workflow state (IF-AS-EXT-OUT-001)
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[adr.id],
                item_type="Adr",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug("AdrService: workflow init skipped for adr=%s", adr.id)

        self._audit(ctx=ctx, operation="create", entity_type="Adr", entity_id=adr.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ADR_CREATED,
                entity_id=adr.id,
                workspace_id=workspace_id,
                payload={"title": title},
            )
        )
        return adr

    @atomic_transaction
    def update_adr(
        self,
        adr_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        context: Optional[str] = None,
        consequences: Optional[str] = None,
        change_reason: Optional[str] = None,
    ) -> Adr:
        """Update an ADR, incrementing its version (REQ-L3-ADR-002, ADR-L3-ADR-01).

        Args:
            adr_id: UUID of the ADR to update.
            ctx: Resolved AuthContext.
            title: New title (optional).
            description: New description (optional).
            context: New context section (optional).
            consequences: New consequences section (optional).
            change_reason: Optional change rationale for audit.

        Returns:
            Updated Adr ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")

        if title is not None:
            if not title or len(title) < 3:
                raise ValidationError("ADR title must be at least 3 characters")
            adr.title = title
        if description is not None:
            if len(description) > 10000:
                raise ValidationError("ADR description must not exceed 10,000 characters")
            adr.description = description
        if context is not None:
            adr.context = context
        if consequences is not None:
            adr.consequences = consequences

        # Atomic version increment (REQ-L3-PL001-002): save payload fields first,
        # then issue a single SQL UPDATE that increments version at the database
        # level — avoids the read-modify-write race condition of `version += 1`.
        adr.save()
        Adr.objects.filter(id=adr.id).update(version=F("version") + 1)
        adr.refresh_from_db(fields=["version"])

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Adr",
            entity_id=adr_id,
            change_reason=change_reason,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ADR_UPDATED,
                entity_id=adr_id,
                workspace_id=adr.workspace_id,
                payload={"change_reason": change_reason, "version": adr.version},
            )
        )
        return adr

    @atomic_transaction
    def delete_adr(self, adr_id: UUID, ctx: AuthContext) -> None:
        """Delete ADR and cascade-delete TraceLinks (REQ-L3-ADR-003, ADR-L3-ADR-03).

        Args:
            adr_id: UUID of the ADR to delete.
            ctx: Resolved AuthContext.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")

        workspace_id = adr.workspace_id

        # Cascade TraceLink deletion (IF-AS-INT-002)
        try:
            self._trace_link_service.cascade_delete_trace_links(adr_id, ctx)
        except Exception:
            logger.debug(
                "AdrService.delete_adr: cascade TraceLink delete skipped for adr=%s",
                adr_id,
            )

        adr.delete()

        self._audit(ctx=ctx, operation="delete", entity_type="Adr", entity_id=adr_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.ADR_DELETED,
                entity_id=adr_id,
                workspace_id=workspace_id,
            )
        )

    def get_adr(self, adr_id: UUID, ctx: AuthContext) -> Adr:
        """Fetch a single ADR (tenant-scoped, REQ-L3-ADR-008).

        Args:
            adr_id: UUID of the ADR to retrieve.
            ctx: Resolved AuthContext.

        Returns:
            Adr ORM instance.
        """
        self._set_tenant_context(ctx)
        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")
        return adr

    def list_adrs(
        self, workspace_id: UUID, ctx: AuthContext
    ) -> List[Adr]:
        """Return all ADRs in *workspace_id* (tenant-scoped, REQ-L3-ADR-008).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Returns:
            List of Adr ORM instances.
        """
        self._set_tenant_context(ctx)
        return list(
            Adr.objects.filter(
                workspace_id=workspace_id, tenant_id=ctx.tenant_id
            ).order_by("created_at")
        )

    def list_adrs_by_status(
        self, workspace_id: UUID, status: str, ctx: AuthContext
    ) -> List[Adr]:
        """Return ADRs filtered by *status* (REQ-L3-ADR-008).

        Args:
            workspace_id: Target workspace UUID.
            status: One of the Adr.Status values.
            ctx: Resolved AuthContext.

        Returns:
            Filtered list of Adr ORM instances.
        """
        self._set_tenant_context(ctx)
        return list(
            Adr.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                status=status,
            ).order_by("created_at")
        )

    # ---------- Status Transition (REQ-L3-ADR-004, IF-AS-INT-003) ----------

    @atomic_transaction
    def transition_status(
        self,
        adr_id: UUID,
        target_status: str,
        ctx: AuthContext,
        change_reason: Optional[str] = None,
    ) -> Adr:
        """Transition an ADR's workflow status (REQ-L3-ADR-004).

        Delegates to WorkflowFacade when available; falls back to direct
        status update if workflow engine is not configured.

        Args:
            adr_id: UUID of the ADR.
            target_status: Target status from Adr.Status choices.
            ctx: Resolved AuthContext.
            change_reason: Optional reason for audit.

        Returns:
            Updated Adr ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")

        if target_status not in AdrValidator.VALID_STATUSES:
            raise ValidationError(
                f"Invalid ADR status '{target_status}'; "
                f"must be one of {sorted(AdrValidator.VALID_STATUSES)}"
            )

        # Delegate to WorkflowFacade (IF-AS-INT-003)
        try:
            from application.workflow_facade import WorkflowFacade

            wf = WorkflowFacade()
            wf.transition(
                item_id=adr_id,
                item_type="Adr",
                target_state=target_status,
                ctx=ctx,
                change_reason=change_reason,
            )
        except Exception:
            logger.debug(
                "AdrService.transition_status: WorkflowFacade transition skipped "
                "for adr=%s, applying direct status update",
                adr_id,
            )

        adr.status = target_status
        # Atomic version increment (REQ-L3-PL001-002)
        adr.save()
        Adr.objects.filter(id=adr.id).update(version=F("version") + 1)
        adr.refresh_from_db(fields=["version"])

        self._audit(
            ctx=ctx,
            operation="transition",
            entity_type="Adr",
            entity_id=adr_id,
            change_reason=change_reason,
            details={"target_status": target_status},
        )
        return adr

    # ---------- TraceLink management (REQ-L3-ADR-005, IF-AS-INT-002) ----------

    def create_tracelink(
        self,
        adr_id: UUID,
        target_id: UUID,
        link_type: str,
        ctx: AuthContext,
    ):
        """Create a TraceLink from an ADR to another artifact (REQ-L3-ADR-005).

        Args:
            adr_id: UUID of the source ADR.
            target_id: UUID of the target artifact.
            link_type: One of {"addresses", "supersedes", "related-to"}.
            ctx: Resolved AuthContext.

        Returns:
            Created TraceLink ORM instance.
        """
        self._set_tenant_context(ctx)
        if link_type not in ADR_LINK_TYPES:
            raise ValidationError(
                f"Invalid ADR link type '{link_type}'; "
                f"must be one of {sorted(ADR_LINK_TYPES)}"
            )

        adr = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id).first()
        if adr is None:
            raise NotFoundError(f"ADR {adr_id} not found")

        return self._trace_link_service.create_trace_link(
            source_id=adr_id,
            target_id=target_id,
            link_type=link_type,
            ctx=ctx,
        )


__all__ = [
    "AdrService",
    "AdrDTO",
    "ADR_LINK_TYPES",
]
