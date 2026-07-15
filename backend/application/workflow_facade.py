"""
COMP-AS-007 WorkflowFacade — Workflow state transition orchestrator.

leaf_id : COMP-AS-007
req_id  : REQ-L1-009, REQ-L2-AS-009, REQ-L2-AS-010

Orchestrates workflow transitions for all artifact types. Delegates the actual
state machine execution to workflow.services (IF-WE-EXT-IN-001/002). Ensures
audit logging via _audit and preset-role validation via PresetPolicyService.

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: transition, initialize_workflow_states
  IF-AS-INT-007     — outbound: PresetPolicyService.validate_transition_roles()

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-007_WorkflowFacade/
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db import transaction

# Backward-compat alias used by tests that patch 'application.workflow_facade.TenantContext'
TenantContext = AuthContext

from application.base import (
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.preset_policy_service import get_preset_policy_service

logger = logging.getLogger(__name__)


class WorkflowFacade(ServiceBase):
    """Single entry point for workflow state transitions.

    COMP-AS-007 (IF-AS-EXT-IN-001, IF-AS-INT-007).

    REQ-L3-WF-006: All engine calls + audit writes run inside transaction.atomic().

    Usage::

        facade = WorkflowFacade()
        result = facade.transition(
            item_id=req_uuid,
            target_state="In Review",
            change_reason="ready for review",
            ctx=auth_ctx,
            item_type="Requirement",
            workspace_id=ws_uuid,
        )
    """

    # ---------- Public API ----------

    def transition(
        self,
        item_id: UUID | str,
        target_state: str,
        change_reason: str,
        ctx: AuthContext,
        *,
        credential: str = "",
        item_type: str = "Requirement",
        workspace_id: UUID | str,
    ):
        """Execute a workflow transition for an artifact.

        REQ-L3-WF-001 (validation), REQ-L3-WF-002 (delegation),
        REQ-L3-WF-003 (audit), REQ-L3-WF-004 (change_reason check),
        REQ-L3-WF-005/006 (atomic + rollback on error).

        Args:
            item_id: UUID of the item to transition.
            target_state: Requested new state name.
            change_reason: Required when preset mandates it.
            ctx: Fully resolved AuthContext.
            credential: Optional TOTP/password for SignatureGate transitions.
            item_type: Entity type (default "Requirement").
            workspace_id: Workspace UUID.

        Returns:
            workflow.services.TransitionResult

        Raises:
            PermissionDeniedError: Preset-level role gate blocked transition.
            ValidationError: change_reason missing or transition not allowed.
        """
        self._set_tenant_context(ctx)

        item_uuid = UUID(str(item_id))
        ws_uuid = UUID(str(workspace_id))

        # REQ-L3-WF-004: change_reason check via PresetPolicyService (IF-AS-INT-008)
        self._check_change_reason(str(ws_uuid), change_reason)

        # REQ-L3-WF-001: preset-level role gate (IF-AS-INT-007)
        self._check_transition_roles(ctx, target_state)

        # REQ-L3-WF-002 + REQ-L3-WF-006: atomic wrap
        with transaction.atomic():
            from workflow.services import transition as wf_transition

            try:
                result = wf_transition(
                    item_id=item_uuid,
                    target_state=target_state,
                    change_reason=change_reason,
                    ctx=ctx,
                    credential=credential,
                    item_type=item_type,
                    workspace_id=ws_uuid,
                )
            except Exception as exc:
                _remap_workflow_exc(exc)

            # REQ-L3-WF-003: audit inside same transaction
            self._audit(
                ctx=ctx,
                operation="workflow.transition",
                entity_type=item_type,
                entity_id=item_uuid,
                change_reason=change_reason,
                details={
                    "previous_state": result.previous_state,
                    "new_state": result.new_state,
                    "workspace_id": str(ws_uuid),
                },
            )

            # Domain event (WorkflowTransitioned)
            self._emit_event(
                self._make_event(
                    event_type="WorkflowTransitioned",
                    entity_id=item_uuid,
                    workspace_id=ws_uuid,
                    payload={
                        "item_type": item_type,
                        "previous_state": result.previous_state,
                        "new_state": result.new_state,
                    },
                )
            )

        return result

    def initialize_workflow_states(
        self,
        item_ids: List[UUID | str],
        item_type: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
    ) -> list:
        """Create initial workflow states for a batch of items.

        IF-WE-EXT-IN-002. REQ-L2-WE-005.

        Args:
            item_ids: List of item UUIDs.
            item_type: Entity type (e.g. "Requirement").
            workspace_id: Workspace UUID.
            ctx: AuthContext for tenant propagation.

        Returns:
            List of WorkflowItemState instances.
        """
        self._set_tenant_context(ctx)

        from workflow.services import initialize_workflow_states as wf_init

        try:
            return wf_init(
                item_ids=item_ids,
                item_type=item_type,
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception as exc:
            _remap_workflow_exc(exc)

    def get_available_transitions(
        self,
        item_id: UUID | str,
        ctx: AuthContext,
        *,
        item_type: str = "Requirement",
        workspace_id: UUID | str,
    ):
        """Return current state + allowed next transitions for an item (REQ-143).

        Read-only. Sets the tenant context and delegates to
        ``workflow.services.get_available_transitions``. Returns an
        ``AvailableTransitions`` DTO (never raises for "not configured").
        """
        self._set_tenant_context(ctx)

        from workflow.services import (
            get_available_transitions as wf_available_transitions,
        )

        return wf_available_transitions(
            item_id=item_id,
            item_type=item_type,
            workspace_id=workspace_id,
        )

    def get_history(
        self,
        item_id: UUID | str,
        ctx: AuthContext,
        *,
        item_type: str = "Requirement",
        workspace_id: UUID | str,
    ) -> list:
        """Return the workflow transition history for an item (REQ-144).

        Read-only. Sets the tenant context and delegates to
        ``workflow.services.get_history``. Returns a chronological list of
        ``WorkflowHistoryEntry`` ORM instances (never raises for "no history").
        """
        self._set_tenant_context(ctx)

        from workflow.services import get_history as wf_get_history

        return wf_get_history(
            item_id=item_id,
            item_type=item_type,
            workspace_id=workspace_id,
        )

    # ---------- Private helpers ----------

    @staticmethod
    def _check_change_reason(workspace_id: str, change_reason: str) -> None:
        """Raise ValidationError if change_reason is required but absent.

        REQ-L3-WF-004. Delegates to IF-AS-INT-008.
        """
        # get_preset_policy_service is imported at module level to allow test mocking.
        policy = get_preset_policy_service()
        if policy.is_change_reason_required(workspace_id):
            if not change_reason or not change_reason.strip():
                raise ValidationError(
                    "change_reason is required by the workspace preset for state transitions."
                )
            if len(change_reason) > 500:
                raise ValidationError(
                    "change_reason must not exceed 500 characters."
                )

    @staticmethod
    def _check_transition_roles(ctx: AuthContext, target_state: str) -> None:
        """Raise PermissionDeniedError if preset blocks this role for target_state.

        REQ-L3-WF-001. Delegates to IF-AS-INT-007.
        """
        # get_preset_policy_service is imported at module level to allow test mocking.
        policy = get_preset_policy_service()
        allowed, error_msg = policy.validate_transition_roles(ctx, target_state)
        if not allowed:
            raise PermissionDeniedError(error_msg or "Transition denied by preset policy.")


# ---------- Exception remapping ----------

def _remap_workflow_exc(exc: Exception) -> None:
    """Re-raise workflow-domain exceptions as application-layer exceptions."""
    from workflow.services import WorkflowTransitionError

    from application.base import ValidationError, PermissionDeniedError

    if isinstance(exc, WorkflowTransitionError):
        if exc.error_code in ("EC_ROLE_NOT_ALLOWED",):
            raise PermissionDeniedError(exc.error_message) from exc
        raise ValidationError(exc.error_message) from exc
    raise exc


__all__ = ["WorkflowFacade"]
