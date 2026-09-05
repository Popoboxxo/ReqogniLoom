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
import uuid as uuid_module
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from django.db import transaction
from django.db.models import F, QuerySet

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.models import (
    ChangeRequest,
    ChangeRequestAffectedItem,
    DomainEventOutbox,
)
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)
from application.preset_policy_service import get_preset_policy_service
from workflow import state_reader

logger = logging.getLogger(__name__)

# CCB workflow states in lifecycle order.
CCB_STATES = frozenset(ChangeRequest.Status.values)

# Statuses that are valid for creation (not the terminal/reviewed ones by user init).
VALID_CREATE_STATUSES = frozenset({"draft"})

# CCB decision transitions — the ones a Change Control Board actually decides.
# Separation of duties (requestor != approver) is enforced on these only.
CCB_DECISION_STATES = frozenset(
    {ChangeRequest.Status.APPROVED, ChangeRequest.Status.REJECTED}
)

# States at which the "after" side of the affected-item snapshot is captured
# and the configuration baseline of record is linked.
CCB_CLOSING_STATES = frozenset(
    {ChangeRequest.Status.APPROVED, ChangeRequest.Status.IMPLEMENTED}
)

# Preset feature keys (presets.registry.FEATURE_KEYS) used for rigor gating.
#   minimal  : baselines=False, approval_workflows=False
#   standard : baselines=True,  approval_workflows=False
#   extended : baselines=True,  approval_workflows=True
FEATURE_BASELINES = "baselines"
FEATURE_APPROVAL_WORKFLOWS = "approval_workflows"


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
    baseline_id: Optional[UUID] = None

    @classmethod
    def from_orm(cls, cr: ChangeRequest) -> "ChangeRequestDTO":
        """Build a DTO. ``status`` comes from the workflow engine (Phase 1).

        Task 12: the ``status`` column is dropped. Falls back to the
        ``ccb_approval`` preset's initial state when the engine has no
        ``WorkflowItemState`` row for it (e.g. workflow init was skipped at
        create time), or when no tenant context is active (e.g. a caller
        building the DTO outside a request-scoped service call). Documented,
        reviewed data-loss tradeoff (see Task 12 report Finding 2).
        """
        try:
            engine_status = state_reader.current_state("ChangeRequest", cr.id)
        except Exception:  # noqa: BLE001 -- TenantContextNotSetError or similar
            engine_status = None
        return cls(
            id=cr.id,
            workspace_id=cr.workspace_id,
            tenant_id=cr.tenant_id,
            title=cr.title,
            description=cr.description,
            impact_assessment=cr.impact_assessment,
            change_reason=cr.change_reason,
            status=engine_status or state_reader.initial_state("ChangeRequest"),
            requestor_id=cr.requestor_id,
            assigned_reviewer_id=cr.assigned_reviewer_id,
            version=cr.version,
            baseline_id=getattr(cr, "baseline_id", None),
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
        affected_item_ids: Optional[Sequence[UUID | str]] = None,
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
            affected_item_ids: Artifact UUIDs this CR proposes to change. Each
                is validated to exist inside *workspace_id* and the caller's
                tenant; the "before" state snapshot is captured immediately.

        Returns:
            Persisted ChangeRequest ORM instance.

        Raises:
            ValidationError: Title/description invalid, or an affected item is
                unknown / outside the target workspace.
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
            requestor_id=requestor_id or ctx.user_id,
            assigned_reviewer_id=assigned_reviewer_id,
            created_by_name=str(ctx.user_id),
        )

        if affected_item_ids:
            self._replace_affected_items(
                cr=cr, item_ids=affected_item_ids, tenant_id=ctx.tenant_id
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
            logger.warning(
                "ChangeRequestService: WorkflowEngine unavailable, "
                "workflow init skipped for cr=%s", cr.id
            )
        except (WorkflowDefinitionError, WorkflowStateError):
            # Tolerated so that CR creation never hard-fails on a provisioning
            # gap, but logged loudly: without a WorkflowItemState every later
            # transition_status() call now raises WorkflowStateError instead of
            # silently bypassing the CCB gate (see transition_status).
            logger.warning(
                "ChangeRequestService: no WorkflowDefinition configured for "
                "ChangeRequest in workspace=%s — workflow init skipped for "
                "cr=%s; CCB transitions will fail until "
                "'provision_workflow_definitions' has been run",
                workspace_id,
                cr.id,
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
        affected_item_ids: Optional[Sequence[UUID | str]] = None,
        expected_version: Optional[int] = None,
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
            affected_item_ids: When not None, *replaces* the affected-item set
                (an empty sequence clears it). ``None`` leaves it untouched.
            expected_version: Caller's last-seen ``version``. When supplied and
                stale, the update is refused with ``OptimisticLockError`` (409)
                instead of overwriting a concurrent edit. Omitting it keeps the
                previous last-writer-wins behaviour.

        Returns:
            Updated ChangeRequest ORM instance.

        Raises:
            OptimisticLockError: *expected_version* does not match the stored one.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cr = lock_for_version_check(
            ChangeRequest.objects.filter(id=cr_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")
        assert_expected_version(cr, expected_version, entity_type="ChangeRequest")

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
        if affected_item_ids is not None:
            self._replace_affected_items(
                cr=cr, item_ids=affected_item_ids, tenant_id=ctx.tenant_id
            )

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
        include_deleted: bool = False,
    ) -> QuerySet:
        """Return ChangeRequests in *workspace_id* (tenant-scoped, REQ-157).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.
            status_filter: Optional CCB state to filter by (e.g. 'under_review').
            include_deleted: If True, include outdated ChangeRequests.
                delete_change_request() routes through
                workflow.services.outdate(); the "outdated" state is read from
                WorkflowItemState (Datenmodell-Konsolidierung Phase 1).
                Excluded by default.

        Returns:
            QuerySet of ChangeRequest ORM instances ordered by creation date.
        """
        self._set_tenant_context(ctx)
        qs = ChangeRequest.objects.filter(
            workspace_id=workspace_id, tenant_id=ctx.tenant_id
        )
        if status_filter:
            qs = qs.filter(
                id__in=state_reader.item_ids_in_state(
                    "ChangeRequest", status_filter, tenant_id=ctx.tenant_id
                )
            )
        if not include_deleted and status_filter != "outdated":
            # GH-443: an explicit ``status_filter="outdated"`` implies
            # include_deleted. Without the guard the two filters contradicted
            # each other and the query could only ever return an empty result
            # set, so there was no way to list soft-deleted CRs through the
            # status filter.
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "ChangeRequest", "outdated", tenant_id=ctx.tenant_id
                )
            )
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

        The WorkflowEngine (``ccb_approval`` preset) is the SOLE authority for
        the transition — there is no direct-status-write fallback. It enforces:
          - Role checks (editor for submit/implement, approver for review decisions)
          - change_reason requirement on submit and reject transitions

        On top of the engine's gates this method enforces CCB separation of
        duties on the decision transitions (``approved`` / ``rejected``) —
        see :meth:`_enforce_separation_of_duties`. That check is rigor-gated on
        the ``approval_workflows`` preset feature (extended tier), mirroring
        ``PresetPolicyService.validate_transition_roles``.

        When the CR reaches ``approved`` / ``implemented`` the affected-item
        "after" snapshot is captured and the configuration baseline of record
        is linked (no-op when the workspace preset has no ``baselines``).

        Args:
            cr_id: UUID of the ChangeRequest.
            target_status: Target CCB state (draft/submitted/under_review/
                           approved/rejected/implemented).
            ctx: Resolved AuthContext.
            change_reason: Transition rationale (required for some transitions).

        Returns:
            Updated ChangeRequest ORM instance.

        Raises:
            NotFoundError: No such ChangeRequest in the caller's tenant.
            ValidationError: ``target_status`` is not a CCB state, or an
                extended-tier approval has no affected items recorded.
            PermissionDeniedError: Separation of duties violated (requestor ==
                approver, or a foreign user acting on an assigned CR).
            workflow.services.WorkflowDefinitionError: The ``ccb_approval``
                workflow definition is not provisioned for this workspace —
                a configuration error that is now surfaced instead of silently
                bypassing every CCB control.
            workflow.lifecycle_manager.WorkflowStateError: The CR has no
                WorkflowItemState (workflow init was skipped at create time).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cr = ChangeRequest.objects.filter(
            id=cr_id, tenant_id=ctx.tenant_id
        ).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")

        ChangeRequestValidator.validate_status(target_status)

        # CCB governance gates that the generic workflow engine cannot express
        # (they depend on ChangeRequest-specific columns).
        self._enforce_separation_of_duties(cr=cr, target_status=target_status, ctx=ctx)
        self._enforce_affected_items_recorded(cr=cr, target_status=target_status)

        # Delegate to WorkflowFacade (IF-AS-INT-003) with the ccb_approval
        # preset. The engine is the sole authority: role, change_reason and
        # signature gates are enforced there and every error — including
        # WorkflowDefinitionError ("definition not provisioned") and
        # WorkflowStateError ("item has no workflow state") — propagates and
        # aborts this atomic transaction.
        #
        # The previous implementation caught those two (plus ImportError),
        # logged at DEBUG and wrote ``cr.status`` directly. That silently
        # disabled ALL CCB control — role checks, change_reason enforcement and
        # the state machine — for any workspace whose ccb_approval definition
        # was missing, and surfaced nothing to the caller. ``ccb_approval`` is
        # provisioned for EVERY workspace on EVERY rigor tier (see
        # application.workspace_provisioning.WORKFLOW_ENTITY_TYPES), so a
        # missing definition is a genuine configuration error, not a tier
        # difference.
        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=cr_id,
            item_type="ChangeRequest",
            target_state=target_status,
            workspace_id=cr.workspace_id,
            ctx=ctx,
            change_reason=change_reason,
        )

        # Datenmodell-Konsolidierung Phase 1: WorkflowItemState is the seam
        # this service reads through (see ChangeRequestDTO.from_orm), so
        # "status" is dropped from the refresh below. The engine still writes
        # its own denormalized ``status`` mirror column on the row
        # (StateLifecycleManager._sync_status_mirror, ChangeRequest remains a
        # registered mirror model) — a ``cr.save()`` would clobber that with
        # the stale in-memory status, which is why this uses a queryset
        # ``.update()`` instead.
        update_fields: Dict[str, Any] = {"version": F("version") + 1}
        if change_reason is not None:
            update_fields["change_reason"] = change_reason
        ChangeRequest.objects.filter(id=cr.id).update(**update_fields)
        cr.refresh_from_db(fields=["version", "change_reason"])

        if target_status in CCB_CLOSING_STATES:
            self._capture_affected_items_after(cr=cr, tenant_id=ctx.tenant_id)
            self._link_baseline_if_enabled(cr=cr, ctx=ctx)

        self._audit(
            ctx=ctx,
            operation="transition",
            entity_type="ChangeRequest",
            entity_id=cr_id,
            change_reason=change_reason,
            details={"target_status": target_status},
        )
        return cr

    # ---------- CCB governance gates (separation of duties) ----------

    @staticmethod
    def _enforce_separation_of_duties(
        cr: ChangeRequest, target_status: str, ctx
    ) -> None:
        """Reject a CCB decision taken by the requestor or a foreign reviewer.

        ISO 15288 §6.4.3: the board deciding a change must not be the party
        requesting it. Two rules, both only on ``approved`` / ``rejected``:

        1. ``ctx.user_id == cr.requestor_id`` -> denied (self-approval).
        2. ``cr.assigned_reviewer_id`` set and the actor is neither that
           reviewer nor an ``admin`` -> denied. The admin override mirrors the
           ``ccb_approval`` preset itself, where every transition lists
           ``admin`` alongside the functional role.

        Rigor gating: enforced only when the workspace preset enables
        ``approval_workflows`` (extended tier). This mirrors
        ``PresetPolicyService.validate_transition_roles``, which gates its
        approver-role check on exactly the same feature — on minimal/standard a
        CCB is intentionally lightweight (frequently a single user), so
        enforcing SoD there would make the workflow unusable rather than safer.

        Args:
            cr: The ChangeRequest being transitioned.
            target_status: Requested CCB state.
            ctx: Resolved AuthContext of the acting user.

        Raises:
            PermissionDeniedError: A separation-of-duties rule was violated.
        """
        if target_status not in CCB_DECISION_STATES:
            return
        policy = get_preset_policy_service()
        if not policy.is_feature_enabled(
            str(cr.workspace_id), FEATURE_APPROVAL_WORKFLOWS
        ):
            return

        actor_id = getattr(ctx, "user_id", None)
        if actor_id is None:
            return

        requestor_id = getattr(cr, "requestor_id", None)
        if requestor_id is not None and str(actor_id) == str(requestor_id):
            raise PermissionDeniedError(
                "Separation of duties: the requestor of a change request must "
                f"not decide it (target status '{target_status}'). A different "
                "CCB member with the 'approver' role has to act."
            )

        reviewer_id = getattr(cr, "assigned_reviewer_id", None)
        if reviewer_id is not None and str(actor_id) != str(reviewer_id):
            roles = tuple(getattr(ctx, "active_roles", ()) or ())
            if not any(str(role).lower() == "admin" for role in roles):
                raise PermissionDeniedError(
                    f"Change request is assigned to reviewer {reviewer_id}; "
                    "only that reviewer or a user with the 'admin' role may "
                    f"set it to '{target_status}'."
                )

    @staticmethod
    def _enforce_affected_items_recorded(cr: ChangeRequest, target_status: str) -> None:
        """Require at least one affected item before an extended-tier approval.

        ISO 15288 §6.4.9: an approved change must state *what* it changes.
        Gated on the ``approval_workflows`` feature (extended tier only) —
        minimal/standard keep the CCB lightweight and never require this.

        Args:
            cr: The ChangeRequest being transitioned.
            target_status: Requested CCB state.

        Raises:
            ValidationError: Extended tier, target ``approved``, no items.
        """
        if target_status != ChangeRequest.Status.APPROVED:
            return
        policy = get_preset_policy_service()
        if not policy.is_feature_enabled(
            str(cr.workspace_id), FEATURE_APPROVAL_WORKFLOWS
        ):
            return
        if not ChangeRequestAffectedItem.objects.filter(change_request_id=cr.id).exists():
            raise ValidationError(
                "Change request cannot be approved without recorded affected "
                "items: the workspace runs the 'extended' rigor preset, which "
                "requires the configuration impact of a change to be explicit."
            )

    # ---------- Affected items (ISO 15288 §6.4.3/§6.4.9) ----------

    @transaction.atomic
    def set_affected_items(
        self,
        cr_id: UUID,
        item_ids: Sequence[UUID | str],
        ctx,
    ) -> List[ChangeRequestAffectedItem]:
        """Replace the affected-item set of a ChangeRequest.

        Each id must be an Artifact of the CR's workspace and the caller's
        tenant. The "before" state snapshot is captured immediately using
        ``baseline.state_capture`` — the same curated per-artifact-type field
        set the baseline snapshots use.

        Available on every rigor tier: recording impact is plain data and never
        an error, only its *enforcement* varies by tier (see
        :meth:`_enforce_affected_items_recorded`).

        Args:
            cr_id: UUID of the ChangeRequest.
            item_ids: Artifact UUIDs. An empty sequence clears the set.
            ctx: Resolved AuthContext.

        Returns:
            The persisted ChangeRequestAffectedItem rows.

        Raises:
            NotFoundError: No such ChangeRequest in the caller's tenant.
            ValidationError: An id is not a UUID, or names an artifact outside
                the CR's workspace/tenant.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cr = ChangeRequest.objects.filter(id=cr_id, tenant_id=ctx.tenant_id).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")

        rows = self._replace_affected_items(
            cr=cr, item_ids=item_ids, tenant_id=ctx.tenant_id
        )

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="ChangeRequest",
            entity_id=cr_id,
            details={"affected_item_count": len(rows)},
        )
        return rows

    def list_affected_items(self, cr_id: UUID, ctx) -> List[ChangeRequestAffectedItem]:
        """Return the affected items of a ChangeRequest (tenant-scoped).

        Args:
            cr_id: UUID of the ChangeRequest.
            ctx: Resolved AuthContext.

        Returns:
            List of ChangeRequestAffectedItem rows ordered by creation time.

        Raises:
            NotFoundError: No such ChangeRequest in the caller's tenant.
        """
        self._set_tenant_context(ctx)
        cr = ChangeRequest.objects.filter(id=cr_id, tenant_id=ctx.tenant_id).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")
        return list(
            ChangeRequestAffectedItem.objects.filter(
                change_request_id=cr.id, tenant_id=ctx.tenant_id
            ).order_by("created_at")
        )

    def _replace_affected_items(
        self,
        cr: ChangeRequest,
        item_ids: Sequence[UUID | str],
        tenant_id: UUID,
    ) -> List[ChangeRequestAffectedItem]:
        """Validate *item_ids*, then rewrite the CR's affected-item rows."""
        normalized = self._validate_affected_items(
            item_ids=item_ids, workspace_id=cr.workspace_id, tenant_id=tenant_id
        )

        ChangeRequestAffectedItem.objects.filter(change_request_id=cr.id).delete()
        if not normalized:
            return []

        states = self._capture_states(normalized, tenant_id)
        rows = [
            ChangeRequestAffectedItem(
                change_request_id=cr.id,
                tenant_id=tenant_id,
                item_id=item_id,
                entity_type="item",
                version_before=(states.get(item_id) or {}).get("version"),
                state_before=states.get(item_id),
            )
            for item_id in normalized
        ]
        ChangeRequestAffectedItem.objects.bulk_create(rows)
        return rows

    @staticmethod
    def _validate_affected_items(
        item_ids: Sequence[UUID | str],
        workspace_id: UUID,
        tenant_id: UUID,
    ) -> List[str]:
        """Return de-duplicated artifact id strings, all verified to exist.

        Row-level isolation: the lookup filters on ``tenant_id`` explicitly
        (``unscoped`` manager, mirroring ``baseline.state_capture``) *and* on
        the CR's ``workspace_id``, so a CR can never reference an artifact of
        another tenant or another workspace.
        """
        normalized: List[str] = []
        for raw in item_ids or ():
            try:
                normalized_id = str(uuid_module.UUID(str(raw)))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValidationError(
                    f"Affected item id '{raw}' is not a valid UUID"
                ) from exc
            if normalized_id not in normalized:
                normalized.append(normalized_id)

        if not normalized:
            return []

        from persistence.models import Artifact

        found = {
            str(artifact_id)
            for artifact_id in Artifact.unscoped.filter(
                id__in=normalized,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            ).values_list("id", flat=True)
        }
        missing = [item_id for item_id in normalized if item_id not in found]
        if missing:
            raise ValidationError(
                "Affected items not found in workspace "
                f"{workspace_id}: {sorted(missing)}"
            )
        return normalized

    @staticmethod
    def _capture_states(
        item_ids: Sequence[str], tenant_id: UUID
    ) -> Dict[str, Dict[str, Any]]:
        """Capture curated per-artifact-type state via ``baseline.state_capture``.

        Reuses the baseline snapshot helper instead of duplicating a field-set
        per artifact type; a new artifact type added there is picked up here
        automatically. Failures are non-fatal — the impact record is still
        worth having without a state snapshot (mirrors BaselineDeltaIndexEntry,
        whose ``state`` is nullable for exactly that reason).
        """
        try:
            from baseline.state_capture import capture_states
            from baseline.types import DeltaIndexTuple

            return capture_states(
                [
                    DeltaIndexTuple(item_id=item_id, version=0, entity_type="item")
                    for item_id in item_ids
                ],
                tenant_id,
            )
        except Exception:
            logger.warning(
                "ChangeRequestService: affected-item state capture failed for "
                "tenant=%s — persisting the impact record without a snapshot",
                tenant_id,
                exc_info=True,
            )
            return {}

    def _capture_affected_items_after(
        self, cr: ChangeRequest, tenant_id: UUID
    ) -> None:
        """Fill ``state_after`` / ``version_after`` on every affected item."""
        rows = list(
            ChangeRequestAffectedItem.objects.filter(change_request_id=cr.id)
        )
        if not rows:
            return
        states = self._capture_states([row.item_id for row in rows], tenant_id)
        for row in rows:
            state = states.get(row.item_id)
            row.state_after = state
            row.version_after = (state or {}).get("version")
        # ``updated_at`` is deliberately omitted: bulk_update does not run
        # auto_now pre_save hooks, so listing it would rewrite the stale value.
        ChangeRequestAffectedItem.objects.bulk_update(
            rows, ["state_after", "version_after"]
        )

    # ---------- Baseline linkage (ISO 15288 §6.4.9) ----------

    @transaction.atomic
    def link_baseline(
        self,
        cr_id: UUID,
        ctx,
        baseline_id: Optional[UUID] = None,
    ) -> ChangeRequest:
        """Link a ChangeRequest to its configuration baseline of record.

        Rigor gating: a no-op (returns the CR unchanged) when the workspace
        preset does not enable ``baselines`` — the ``minimal`` tier has no
        baselines at all, so linkage there must not be an error. This reuses
        the existing per-tier feature flags rather than adding a gate.

        Args:
            cr_id: UUID of the ChangeRequest.
            ctx: Resolved AuthContext.
            baseline_id: Baseline to link. When omitted, the most recent
                baseline of the CR's workspace is used (if any exists).

        Returns:
            The ChangeRequest (with ``baseline`` set, when a baseline applies).

        Raises:
            NotFoundError: No such ChangeRequest, or ``baseline_id`` names a
                baseline outside the CR's workspace/tenant.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cr = ChangeRequest.objects.filter(id=cr_id, tenant_id=ctx.tenant_id).first()
        if cr is None:
            raise NotFoundError(f"ChangeRequest {cr_id} not found")

        linked = self._link_baseline_if_enabled(
            cr=cr, ctx=ctx, baseline_id=baseline_id, override=True
        )
        if linked:
            self._audit(
                ctx=ctx,
                operation="update",
                entity_type="ChangeRequest",
                entity_id=cr_id,
                details={"baseline_id": str(cr.baseline_id)},
            )
        return cr

    def _link_baseline_if_enabled(
        self,
        cr: ChangeRequest,
        ctx,
        baseline_id: Optional[UUID] = None,
        override: bool = False,
    ) -> bool:
        """Attach the baseline of record; return True when the CR was changed.

        Which baseline? The one the change is evaluated / implemented
        *against* — i.e. an already existing snapshot, chosen explicitly or
        defaulting to the workspace's most recent one. Deliberately NOT a
        baseline created by this service: no call site in this codebase creates
        a baseline in response to a CR (``BaselineFacade.create_baseline`` is
        only ever invoked from the REST/MCP baseline endpoints), so minting one
        here would introduce an unrequested side effect with a name-uniqueness
        constraint. A caller that *does* create a baseline for the change may
        record it via :meth:`link_baseline` with an explicit ``baseline_id``.
        """
        if not override and getattr(cr, "baseline_id", None) is not None:
            return False

        policy = get_preset_policy_service()
        if not policy.is_feature_enabled(str(cr.workspace_id), FEATURE_BASELINES):
            logger.debug(
                "ChangeRequestService: baselines disabled by preset for ws=%s "
                "— baseline linkage skipped for cr=%s",
                cr.workspace_id,
                cr.id,
            )
            return False

        from baseline.models import BaselineSnapshot

        qs = BaselineSnapshot.unscoped.filter(
            workspace_id=cr.workspace_id, tenant_id=ctx.tenant_id
        )
        if baseline_id is not None:
            snapshot = qs.filter(id=baseline_id).first()
            if snapshot is None:
                raise NotFoundError(
                    f"Baseline {baseline_id} not found in workspace "
                    f"{cr.workspace_id}"
                )
        else:
            snapshot = qs.order_by("-created_at").first()
            if snapshot is None:
                logger.debug(
                    "ChangeRequestService: no baseline exists in ws=%s — "
                    "nothing to link for cr=%s",
                    cr.workspace_id,
                    cr.id,
                )
                return False

        ChangeRequest.objects.filter(id=cr.id).update(baseline_id=snapshot.id)
        cr.baseline_id = snapshot.id
        return True


__all__ = [
    "ChangeRequestService",
    "ChangeRequestDTO",
    "ChangeRequestValidator",
    "CCB_DECISION_STATES",
    "CCB_CLOSING_STATES",
]
