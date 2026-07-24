"""
COMP-AS-021 ChangeRequestService — Change Request CRUD + CCB Workflow.

leaf_id : COMP-AS-021
req_id  : REQ-157

Orchestrates:
  IF-AS-INT-003   WorkflowFacade.transition (status transitions via ccb_approval preset)
  IF-AS-EXT-OUT-021  application.models.ChangeRequest (Django ORM)

Architecture:
  Follows the same pattern as AdrService (COMP-AS-013) — plain Model (not
  TenantScopedModel) with explicit workspace_id/tenant_id UUID fields.
  All mutations are wrapped in atomic transactions (ADR-L3-ADR-03 pattern).

CCB workflow states: draft → submitted → under_review → approved|rejected → implemented
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from django.db import transaction
from django.db.models import F, QuerySet

from application.base import NotFoundError, ServiceBase, ValidationError
from application.models import ChangeRequest, DomainEventOutbox

logger = logging.getLogger(__name__)

# CCB workflow states in lifecycle order.
CCB_STATES = frozenset(ChangeRequest.Status.values)

# Statuses that are valid for creation (not the terminal/reviewed ones by user init).
VALID_CREATE_STATUSES = frozenset({"draft"})


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class ChangeRequestDTO:
    """Read-oriented DTO returned by ChangeRequestService methods.

    leaf_id : COMP-AS-017
    req_id  : REQ-157
    """

    id: UUID
    workspace_id: UUID
    tenant_id: UUID
    title: str
    description: str
    impact_assessment: str
    change_reason: str
    status: str
    requestor_id: Optional[UUID]
    assigned_reviewer_id: Optional[UUID]
    version: int

    @classmethod
    def from_orm(cls, cr: ChangeRequest) -> "ChangeRequestDTO":
        return cls(
            id=cr.id,
            workspace_id=cr.workspace_id,
            tenant_id=cr.tenant_id,
            title=cr.title,
            description=cr.description,
            impact_assessment=cr.impact_assessment,
            change_reason=cr.change_reason,
            status=cr.status,
            requestor_id=cr.requestor_id,
            assigned_reviewer_id=cr.assigned_reviewer_id,
            version=cr.version,
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class ChangeRequestValidator:
    """Schema validation for ChangeRequest payloads (REQ-157).

    leaf_id : COMP-AS-017
    req_id  : REQ-157
    """

    @classmethod
    def validate_create(cls, title: str, description: str = "") -> None:
        """Validate fields for ChangeRequest creation."""
        if not title or len(title.strip()) < 3:
            raise ValidationError("ChangeRequest title must be at least 3 characters")
        if len(title) > 255:
            raise ValidationError("ChangeRequest title must not exceed 255 characters")
        if len(description) > 20000:
            raise ValidationError(
                "ChangeRequest description must not exceed 20,000 characters"
            )

    @classmethod
    def validate_status(cls, status: str) -> None:
        """Validate that *status* is a member of the CCB state set."""
        if status not in CCB_STATES:
            raise ValidationError(
                f"ChangeRequest status '{status}' invalid; "
                f"must be one of {sorted(CCB_STATES)}"
            )


# ---------------------------------------------------------------------------
# ChangeRequestService
# ---------------------------------------------------------------------------


class ChangeRequestService(ServiceBase):
    """COMP-AS-017 — Change Request CRUD with CCB Workflow.

    leaf_id : COMP-AS-017
    req_id  : REQ-157
    """

    # ---------- CRUD ----------

    @transaction.atomic
    def create_change_request(
        self,
        workspace_id: UUID,
        title: str,
        ctx,
        description: str = "",
        impact_assessment: str = "",
        change_reason: str = "",
        requestor_id: Optional[UUID] = None,
        assigned_reviewer_id: Optional[UUID] = None,
    ) -> ChangeRequest:
        """Create a ChangeRequest in draft status (REQ-157).

        Args:
            workspace_id: Target workspace UUID.
            title: CR title (3–255 chars).
            ctx: Resolved AuthContext (tenant + roles).
            description: Full description (max 20,000 chars).
            impact_assessment: Impact text (optional).
            change_reason: Initial change rationale (optional at create time).
            requestor_id: UUID of the requesting user (defaults to ctx.user_id).
            assigned_reviewer_id: UUID of CCB reviewer (optional).

        Returns:
            Persisted ChangeRequest ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        ChangeRequestValidator.validate_create(title=title, description=description)

        cr = ChangeRequest.objects.create(
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            impact_assessment=impact_assessment,
            change_reason=change_reason,
            status=ChangeRequest.Status.DRAFT,
            requestor_id=requestor_id or ctx.user_id,
            assigned_reviewer_id=assigned_reviewer_id,
            created_by=str(ctx.user_id),
        )

        # Initialize workflow state via WorkflowEngine (ccb_approval preset).
        # Only a missing/unconfigured workflow definition is tolerated here —
        # any other failure (e.g. a real DB error) must propagate and roll
        # back the whole create_change_request transaction.
        try:
            from workflow.services import (
                WorkflowDefinitionError,
                WorkflowStateError,
                initialize_workflow_states,
            )

            initialize_workflow_states(
                item_ids=[cr.id],
                item_type="ChangeRequest",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except ImportError:
            logger.debug(
                "ChangeRequestService: WorkflowEngine unavailable, "
                "workflow init skipped for cr=%s", cr.id
            )
        except (WorkflowDefinitionError, WorkflowStateError):
            logger.debug(
                "ChangeRequestService: no WorkflowDefinition configured, "
                "workflow init skipped for cr=%s", cr.id
            )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="ChangeRequest",
            entity_id=cr.id,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.CHANGE_REQUEST_CREATED,
                entity_id=cr.id,
                workspace_id=workspace_id,
                payload={"title": title},
            )
        )
        return cr

    @transaction.atomic
    def update_change_request(
        self,
        cr_id: UUID,
        ctx,
        title: Optional[str] = None,
        description: Optional[str] = None,
        impact_assessment: Optional[str] = None,
        change_reason: Optional[str] = None,
        assigned_reviewer_id: Optional[UUID] = None,
    ) -> ChangeRequest:
        """Update a ChangeRequest, incrementing its version (REQ-157).

        Args:
            cr_id: UUID of the ChangeRequest to update.
            ctx: Resolved AuthContext.
            title: New title (optional).
            description: New description (optional).
            impact_assessment: New impact assessment text (optional).
            change_reason: Update rationale for audit (optional).
            assigned_reviewer_id: New CCB reviewer UUID (optional).

        Returns:
            Updated ChangeRequest ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cr = ChangeRequest.objects.filter(
            id=cr_id, tenant_id=ctx.tenant_id
        ).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")

        if title is not None:
            if not title or len(title.strip()) < 3:
                raise ValidationError(
                    "ChangeRequest title must be at least 3 characters"
                )
            cr.title = title
        if description is not None:
            if len(description) > 20000:
                raise ValidationError(
                    "ChangeRequest description must not exceed 20,000 characters"
                )
            cr.description = description
        if impact_assessment is not None:
            cr.impact_assessment = impact_assessment
        if change_reason is not None:
            cr.change_reason = change_reason
        if assigned_reviewer_id is not None:
            cr.assigned_reviewer_id = assigned_reviewer_id

        cr.save()
        ChangeRequest.objects.filter(id=cr.id).update(version=F("version") + 1)
        cr.refresh_from_db(fields=["version"])

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="ChangeRequest",
            entity_id=cr_id,
            change_reason=change_reason,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.CHANGE_REQUEST_UPDATED,
                entity_id=cr_id,
                workspace_id=cr.workspace_id,
                payload={"change_reason": change_reason, "version": cr.version},
            )
        )
        return cr

    @transaction.atomic
    def delete_change_request(self, cr_id: UUID, ctx) -> None:
        """Outdate a change request (soft-delete via the workflow engine).

        Transitions the item's WorkflowItemState to "outdated" — the record is
        never removed from the database, and can be restored via
        workflow.services.reactivate().

        Args:
            cr_id: UUID of the ChangeRequest to delete.
            ctx: Resolved AuthContext.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cr = ChangeRequest.objects.filter(
            id=cr_id, tenant_id=ctx.tenant_id
        ).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")

        workspace_id = cr.workspace_id

        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of a queryset-level hard delete.
        from workflow.services import outdate

        outdate(
            item_id=cr_id,
            item_type="ChangeRequest",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via change_request.delete",
        )

        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="ChangeRequest",
            entity_id=cr_id,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.CHANGE_REQUEST_DELETED,
                entity_id=cr_id,
                workspace_id=workspace_id,
            )
        )

    def get_change_request(self, cr_id: UUID, ctx) -> ChangeRequest:
        """Fetch a single ChangeRequest (tenant-scoped, REQ-157).

        Args:
            cr_id: UUID of the ChangeRequest to retrieve.
            ctx: Resolved AuthContext.

        Returns:
            ChangeRequest ORM instance.
        """
        self._set_tenant_context(ctx)
        cr = ChangeRequest.objects.filter(
            id=cr_id, tenant_id=ctx.tenant_id
        ).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")
        return cr

    def list_change_requests(
        self,
        workspace_id: UUID,
        ctx,
        status_filter: Optional[str] = None,
    ) -> QuerySet:
        """Return ChangeRequests in *workspace_id* (tenant-scoped, REQ-157).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.
            status_filter: Optional CCB state to filter by (e.g. 'under_review').

        Returns:
            QuerySet of ChangeRequest ORM instances ordered by creation date.
        """
        self._set_tenant_context(ctx)
        qs = ChangeRequest.objects.filter(
            workspace_id=workspace_id, tenant_id=ctx.tenant_id
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by("created_at")

    # ---------- Status Transition (REQ-157, IF-AS-INT-003) ----------

    @transaction.atomic
    def transition_status(
        self,
        cr_id: UUID,
        target_status: str,
        ctx,
        change_reason: Optional[str] = None,
    ) -> ChangeRequest:
        """Transition a ChangeRequest's CCB workflow status (REQ-157).

        Delegates to WorkflowFacade when available; falls back to direct
        status update if the workflow engine is not configured.

        The ccb_approval preset enforces:
          - Role checks (editor for submit/implement, approver for review decisions)
          - change_reason requirement on submit and reject transitions

        Args:
            cr_id: UUID of the ChangeRequest.
            target_status: Target CCB state (draft/submitted/under_review/
                           approved/rejected/implemented).
            ctx: Resolved AuthContext.
            change_reason: Transition rationale (required for some transitions).

        Returns:
            Updated ChangeRequest ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cr = ChangeRequest.objects.filter(
            id=cr_id, tenant_id=ctx.tenant_id
        ).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")

        ChangeRequestValidator.validate_status(target_status)

        # Delegate to WorkflowFacade (IF-AS-INT-003) with ccb_approval preset.
        # Only a missing/unconfigured workflow (no WorkflowDefinition for this
        # workspace+item_type, or no WorkflowItemState yet for this item) is
        # tolerated as a fallback to a direct status update. ValidationError,
        # PermissionDeniedError, WorkflowTransitionError and
        # WorkflowConflictError from the CCB gate are NOT caught here — they
        # must propagate to the caller and abort this atomic transaction
        # without touching cr.status.
        try:
            from application.workflow_facade import WorkflowFacade
            from workflow.services import WorkflowDefinitionError, WorkflowStateError

            wf = WorkflowFacade()
            wf.transition(
                item_id=cr_id,
                item_type="ChangeRequest",
                target_state=target_status,
                workspace_id=cr.workspace_id,
                ctx=ctx,
                change_reason=change_reason,
            )
        except ImportError:
            logger.debug(
                "ChangeRequestService.transition_status: WorkflowEngine "
                "unavailable for cr=%s, applying direct status update",
                cr_id,
            )
        except (WorkflowDefinitionError, WorkflowStateError):
            logger.debug(
                "ChangeRequestService.transition_status: no WorkflowEngine "
                "configuration for cr=%s, applying direct status update",
                cr_id,
            )

        cr.status = target_status
        if change_reason is not None:
            cr.change_reason = change_reason
        cr.save()
        ChangeRequest.objects.filter(id=cr.id).update(version=F("version") + 1)
        cr.refresh_from_db(fields=["version", "status", "change_reason"])

        self._audit(
            ctx=ctx,
            operation="transition",
            entity_type="ChangeRequest",
            entity_id=cr_id,
            change_reason=change_reason,
            details={"target_status": target_status},
        )
        return cr


__all__ = [
    "ChangeRequestService",
    "ChangeRequestDTO",
    "ChangeRequestValidator",
]
