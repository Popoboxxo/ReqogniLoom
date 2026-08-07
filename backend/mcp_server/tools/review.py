"""
MCP Tool Group for review/approval endpoints (Phase 5, REQ-L2-RV-001).

A deliberately thin wrapper over WorkflowFacade / workflow.services — no new
state machine, no new state_meta flags. Reuses:
  - workflow.services.is_approval_gate (Phase 5 Task 2) for
    review.list_pending: a transition is a real human approval decision when
    its allowed_roles excludes "editor".
  - WorkflowEngineDefinition's state_meta "auto_approve_target" (Phase 3) for
    review.approve's destination (falls back to the first approval-gated
    transition's target when no explicit auto_approve_target is configured).
  - the universal Phase-0 "outdated" escape hatch (workflow.services.outdate)
    for review.reject -- same idiom as every other <group>.outdate tool in
    this codebase (see mcp_server/tools/needs.py._handle_outdate). Note this
    bypasses normal preset-transition validation (COMP-WE-002) by design --
    "outdated" is not a state_meta-declared transition target for any preset,
    so WorkflowFacade.transition(target_state="outdated") would be rejected
    by the transition validator; the module-level outdate() escape hatch is
    the only correct way to reach it.
  - WorkflowDefinitionDTO.initial_state for review.request_changes.
"""
from __future__ import annotations

from typing import Any, Dict

from auth_tenancy.context import AuthContext

from application.base import PermissionDeniedError, ValidationError
from application.workflow_facade import WorkflowFacade

from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    mcp_audit_handoff,
    require_param,
    require_uuid,
    write_mcp_audit,
)


class ReviewToolGroup(BaseToolGroup):
    """review.* tool group (REQ-L2-RV-001)."""

    _TOOL_MAP = {
        "review.list_pending": "_handle_list_pending",
        "review.approve": "_handle_approve",
        "review.reject": "_handle_reject",
        "review.request_changes": "_handle_request_changes",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "review.list_pending",
            "description": (
                "List items in a workspace whose current workflow state is "
                "one hop away from a human approval gate (a transition whose "
                "allowed_roles excludes 'editor')."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "description": "Optional entity type filter."},
                    "workspace_id": {"type": "string", "description": "Workspace to scope the search to."},
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "review.approve",
            "description": (
                "Approve an item currently awaiting review: transitions it to "
                "its preset's auto_approve_target state (falls back to the "
                "first available approver/admin-gated transition's target -- "
                "excluding reject/outdated-equivalent states -- if no "
                "explicit auto_approve_target is configured)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "change_reason": {"type": "string"},
                },
                "required": ["item_id", "item_type", "workspace_id"],
            },
        },
        {
            "name": "review.reject",
            "description": (
                "Reject an item currently awaiting review: transitions it to "
                "the universal 'outdated' state (Phase 0), recording reason "
                "in the workflow history."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["item_id", "item_type", "workspace_id"],
            },
        },
        {
            "name": "review.request_changes",
            "description": (
                "Send an item currently awaiting review back to its "
                "workflow's initial state for rework, recording reason in "
                "the workflow history."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["item_id", "item_type", "workspace_id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # review.list_pending
    # ------------------------------------------------------------------

    def _handle_list_pending(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from workflow.services import is_approval_gate, list_item_states

        workspace_id = require_uuid(params, "workspace_id")
        item_type = params.get("item_type")

        facade = WorkflowFacade()
        # ADR-01 (#124): the tenant/workspace/item_type filtering moved into
        # workflow.services.list_item_states — same queryset, same laziness.
        qs = list_item_states(
            workspace_id,
            tenant_id=auth_context.tenant_id,
            item_type=item_type,
        )

        pending = []
        for state in qs:
            available = facade.get_available_transitions(
                state.item_id,
                auth_context,
                item_type=state.item_type,
                workspace_id=workspace_id,
            )
            if any(is_approval_gate(t) for t in available.transitions):
                pending.append(
                    {
                        "item_id": str(state.item_id),
                        "item_type": state.item_type,
                        "current_state": state.current_state,
                    }
                )
        return ToolResult.ok({"items": pending, "count": len(pending)})

    # ------------------------------------------------------------------
    # review.approve
    # ------------------------------------------------------------------

    def _handle_approve(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        return self._transition_to_gate_target(
            params=params,
            auth_context=auth_context,
            api_key=api_key,
            operation="approve",
            reason_param="change_reason",
        )

    # ------------------------------------------------------------------
    # review.reject
    # ------------------------------------------------------------------

    def _handle_reject(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """review.reject -- soft-delete via the universal outdate() escape
        hatch (bypasses normal preset-transition validation, same as e.g.
        needs.outdate / requirement.outdate)."""
        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get("reason", "")

        from workflow.services import outdate

        try:
            result = outdate(
                item_id=item_id,
                item_type=item_type,
                workspace_id=workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except Exception as exc:  # noqa: BLE001 -- surface as a structured error
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="reject", entity_type=item_type,
            entity_id=item_id, tool_name="review.reject", api_key=api_key,
            details={"reason": reason},
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})

    # ------------------------------------------------------------------
    # review.request_changes
    # ------------------------------------------------------------------

    def _handle_request_changes(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get("reason", "")

        facade = WorkflowFacade()
        definition = facade.get_definition(auth_context, item_type=item_type, workspace_id=workspace_id)
        if definition is None:
            return ToolResult.error(
                "VALIDATION_ERROR", f"No workflow configured for {item_type} in this workspace."
            )

        try:
            # Codeberg #313: suppress WorkflowFacade.transition's single
            # internal _audit() call (operation="transition", same entity) —
            # write_mcp_audit below is the sole entry.
            with mcp_audit_handoff():
                result = facade.transition(
                    item_id=item_id,
                    target_state=definition.initial_state,
                    change_reason=reason,
                    ctx=auth_context,
                    item_type=item_type,
                    workspace_id=workspace_id,
                )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="request_changes", entity_type=item_type,
            entity_id=item_id, tool_name="review.request_changes", api_key=api_key,
            details={"reason": reason},
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})

    # ------------------------------------------------------------------
    # Shared: transition to the item's approval-gate target
    # ------------------------------------------------------------------

    def _transition_to_gate_target(
        self, *, params, auth_context, api_key, operation, reason_param
    ) -> ToolResult:
        from workflow.definition_store import get_state_meta
        from workflow.services import get_workflow_json, is_approval_gate

        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get(reason_param, "")

        facade = WorkflowFacade()
        available = facade.get_available_transitions(
            item_id, auth_context, item_type=item_type, workspace_id=workspace_id
        )

        # ADR-01 (#124): raw-document read delegated to the workflow service;
        # it returns {} for an unconfigured workspace, matching the previous
        # ``definition_row.workflow_json if definition_row else {}``.
        workflow_json = get_workflow_json(workspace_id, item_type)

        # Prefer the preset's explicit auto_approve_target (Phase 3) among the
        # currently available transitions; fall back to the first genuine
        # approval-gated transition (allowed_roles excludes "editor") if none
        # is configured.
        target = next(
            (
                t.to_state
                for t in available.transitions
                if get_state_meta(workflow_json, t.to_state).get("auto_approve_target", False)
            ),
            None,
        )
        if target is None:
            # GH-370 hardening: never let the fallback implicitly "approve"
            # into a reject/outdated-equivalent state (e.g. Issue.Wontfix).
            # Such states are rejection endpoints, not approval endpoints --
            # picking them here would make review.approve() indistinguishable
            # from review.reject() for any preset that has no explicit
            # auto_approve_target configured.
            gate = next(
                (
                    t
                    for t in available.transitions
                    if is_approval_gate(t)
                    and not get_state_meta(workflow_json, t.to_state).get(
                        "is_outdated_equivalent", False
                    )
                ),
                None,
            )
            target = gate.to_state if gate is not None else None

        if target is None:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"No approval-shaped transition is available from '{available.current_state}' for {item_type}.",
            )

        try:
            # Codeberg #313: suppress WorkflowFacade.transition's single
            # internal _audit() call (operation="transition", same entity) —
            # write_mcp_audit below is the sole entry.
            with mcp_audit_handoff():
                result = facade.transition(
                    item_id=item_id,
                    target_state=target,
                    change_reason=reason,
                    ctx=auth_context,
                    item_type=item_type,
                    workspace_id=workspace_id,
                )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation=operation, entity_type=item_type,
            entity_id=item_id, tool_name=f"review.{operation}", api_key=api_key,
            details={reason_param: reason},
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})


__all__ = ["ReviewToolGroup"]
