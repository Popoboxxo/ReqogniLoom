"""
MCP Tool Group for review/approval endpoints (Phase 5, REQ-L2-RV-001).

A deliberately thin wrapper over WorkflowFacade / workflow.services — no new
state machine, no new state_meta flags. Reuses:
  - workflow.services.is_approval_gate (Phase 5 Task 2) for
    review.list_pending: a transition is a real human approval decision when
    its allowed_roles excludes "editor". The walk itself now lives in
    ``application.review_queue_service.ReviewQueueService`` (issue #1089), which
    the REST endpoints ``GET /api/v1/reviews/pending/`` and
    ``GET /api/v1/workspaces/{id}/reviews/pending/`` share — one service, two
    transports. That service additionally surfaces items in the ``"proposed"``
    state (AI proposals awaiting a human), which ``is_approval_gate``
    deliberately does not match because a proposal's own moves are
    editor-gated.
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
  - WorkflowFacade.resolve_item_type (#1356) for the caller-supplied
    item_type: the engine matches item types exactly ("Requirement"), while
    this tool's schema declares a free string, so the handlers resolve the
    caller's spelling against the workspace's own definition rows before any
    state/transition lookup. Without that step a lowercase "requirement"
    found no state at all and the refusal read "from 'None'" instead of
    naming the item's real state. No preset/gate semantics change here.
"""
from __future__ import annotations

import logging
from typing import Any

from application.base import (
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
)
from application.workflow_facade import WorkflowFacade
from auth_tenancy.context import AuthContext
from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    mcp_audit_handoff,
    require_param,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


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
                    "item_type": {
                        "type": "string",
                        "description": (
                            "Optional entity type filter, e.g. 'Requirement', "
                            "'Adr', 'TestCase'. Matched case-insensitively "
                            "against this workspace's workflow definitions."
                        ),
                    },
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
                    "item_type": {
                        "type": "string",
                        "description": (
                            "Workflow entity type, e.g. 'Requirement', 'Adr', "
                            "'TestCase'. Matched case-insensitively against "
                            "this workspace's workflow definitions."
                        ),
                    },
                    "workspace_id": {"type": "string"},
                    "change_reason": {"type": "string"},
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Optional last-seen workflow revision of the item. "
                            "When supplied and a concurrent transition has "
                            "already moved the item on, the call is rejected "
                            "with a version conflict instead of overwriting "
                            "the winner (CR-08)."
                        ),
                    },
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
                    "item_type": {
                        "type": "string",
                        "description": (
                            "Workflow entity type, e.g. 'Requirement', 'Adr', "
                            "'TestCase'. Matched case-insensitively against "
                            "this workspace's workflow definitions."
                        ),
                    },
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
                "the workflow history. MCP-ONLY (#1356 addendum, #1362d): "
                "there is no REST endpoint or UI action for this decision — "
                "the UI offers approve/reject only, so do not probe for a "
                "'request changes' REST route."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "item_type": {
                        "type": "string",
                        "description": (
                            "Workflow entity type, e.g. 'Requirement', 'Adr', "
                            "'TestCase'. Matched case-insensitively against "
                            "this workspace's workflow definitions."
                        ),
                    },
                    "workspace_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "expected_version": {
                        "type": "integer",
                        "description": (
                            "Optional last-seen workflow revision of the item "
                            "(CR-08) — a stale value is rejected with a "
                            "version conflict."
                        ),
                    },
                },
                "required": ["item_id", "item_type", "workspace_id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # review.list_pending
    # ------------------------------------------------------------------

    def _handle_list_pending(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from application.review_queue_service import ReviewQueueService

        workspace_id = require_uuid(params, "workspace_id")
        item_type = params.get("item_type")

        # #1356: the filter is a free string; resolve it to the workspace's
        # stored spelling first so "requirement" filters the same rows as
        # "Requirement" instead of silently matching none. An unresolvable
        # filter keeps the caller's value (matches nothing), preserving the
        # read tool's "unknown filter -> empty queue" behaviour.
        if item_type:
            resolved, _error = self._resolve_item_type(
                item_type, auth_context, workspace_id
            )
            if resolved is not None:
                item_type = resolved

        try:
            # Issue #1089: one source of truth for "what awaits a human". This
            # used to be an inline `list_item_states` + `get_available_
            # transitions` + `is_approval_gate` walk here; it now lives in
            # ``application.review_queue_service.ReviewQueueService``, which the
            # REST endpoints ``GET /api/v1/reviews/pending/`` and
            # ``GET /api/v1/workspaces/<id>/reviews/pending/`` call as well. Two
            # transports, one decision.
            pending = ReviewQueueService().list_pending(
                auth_context, workspace_id=workspace_id, item_type=item_type
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        # The three-key shape is the tool's published contract and stays exactly
        # as it was; the richer provenance (is_proposal / proposed_by /
        # approval_targets) is the REST projection's job, not a wire change here.
        return ToolResult.ok(
            {
                "items": [
                    {
                        "item_id": item.item_id,
                        "item_type": item.item_type,
                        "current_state": item.current_state,
                    }
                    for item in pending
                ],
                "count": len(pending),
            }
        )

    # ------------------------------------------------------------------
    # review.approve
    # ------------------------------------------------------------------

    def _handle_approve(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
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
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """review.reject -- soft-delete via the universal outdate() escape
        hatch (bypasses normal preset-transition validation, same as e.g.
        needs.outdate / requirement.outdate)."""
        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get("reason", "")

        item_type, type_error = self._resolve_item_type(
            item_type, auth_context, workspace_id
        )
        if type_error is not None:
            return type_error

        from workflow.services import WorkflowItemNotFoundError, outdate

        try:
            # #577: allow_lazy_init=False -- an item reachable via
            # review.reject was supposed to come from review.list_pending,
            # which only surfaces items that already have a registered
            # WorkflowItemState. Unlike every <type>.outdate MCP tool (which
            # keep the lazy-init default True for legitimate pre-workflow-
            # engine legacy items), a caller-supplied item_id with no
            # existing state here means "does not exist", not "predates
            # workflow tracking" -- silently creating one produced a ghost
            # 200 for any random UUID instead of 404.
            result = outdate(
                item_id=item_id,
                item_type=item_type,
                workspace_id=workspace_id,
                ctx=auth_context,
                reason=reason,
                allow_lazy_init=False,
            )
        except WorkflowItemNotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except Exception:
            # #697 (CWE-209): mask the unmapped cause, log it server-side.
            logger.exception("review.reject failed")
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

        write_mcp_audit(
            ctx=auth_context,
            # #626: reuse "delete", the REST pendant for a soft-delete (was
            # the undeclared "reject", silently rejected by full_clean()) --
            # the outdate() call above is the same escape hatch every
            # <type>.outdate MCP tool uses, already mapped to "delete".
            operation="delete", entity_type=item_type,
            entity_id=item_id, tool_name="review.reject", api_key=api_key,
            details={"reason": reason},
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})

    # ------------------------------------------------------------------
    # review.request_changes
    # ------------------------------------------------------------------

    def _handle_request_changes(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        item_id = require_uuid(params, "item_id")
        item_type = require_param(params, "item_type")
        workspace_id = require_uuid(params, "workspace_id")
        reason = params.get("reason", "")
        # CR-08: a caller that tracked the workflow revision may pin it; the
        # compare itself runs inside the engine's row-locked transaction.
        expected_version = params.get("expected_version")

        item_type, type_error = self._resolve_item_type(
            item_type, auth_context, workspace_id
        )
        if type_error is not None:
            return type_error

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
                    expected_version=expected_version,
                )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except OptimisticLockError as exc:
            # Same mapping as the generic *.update tools: a lost race is a
            # caller-retryable conflict, not an internal error.
            return ToolResult.error("VALIDATION_ERROR", f"Version conflict: {exc}")
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            # #626: reuse "transition" (was the undeclared "request_changes",
            # silently rejected by full_clean()) -- WorkflowFacade.transition()
            # was just called above, same convention as #573.
            operation="transition", entity_type=item_type,
            entity_id=item_id, tool_name="review.request_changes", api_key=api_key,
            details={"reason": reason},
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})

    # ------------------------------------------------------------------
    # Shared: caller-supplied item_type resolution (#1356)
    # ------------------------------------------------------------------

    def _resolve_item_type(
        self, item_type: str, auth_context: AuthContext, workspace_id
    ) -> tuple[str | None, ToolResult | None]:
        """Canonicalise a caller-supplied ``item_type`` (issue #1356).

        This tool's schema declares ``item_type`` as a free string and agents
        naturally send the lowercase entity name ("requirement"), but every
        workflow-engine lookup — item state, definition, raw workflow_json —
        matches the type exactly. The facade therefore resolved no state at
        all and the refusal read "from 'None'" although the item sat in
        "draft". Resolving through ``WorkflowFacade.resolve_item_type`` (the
        workspace's own definition rows, case-insensitive) before any engine
        call fixes the state resolution without touching the engine's exact-
        match semantics or any preset/gate rule.

        Returns:
            ``(canonical, None)`` on success; ``(None, error)`` when the
            workspace has no definition for the type. That second case fails
            closed with the actual reason — without a definition there is no
            state to resolve either way, and silently proceeding is what
            produced the original 'None' message.
        """
        canonical = WorkflowFacade().resolve_item_type(
            auth_context, item_type=item_type, workspace_id=workspace_id
        )
        if canonical is None:
            return None, ToolResult.error(
                "VALIDATION_ERROR",
                f"No workflow is configured for item_type {item_type!r} in "
                f"this workspace, so its workflow state cannot be resolved. "
                f"Pass a workflow-tracked entity type (e.g. 'Requirement', "
                f"'Adr', 'TestCase'; case is matched insensitively).",
            )
        return canonical, None

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
        # CR-08: see review.request_changes.
        expected_version = params.get("expected_version")

        item_type, type_error = self._resolve_item_type(
            item_type, auth_context, workspace_id
        )
        if type_error is not None:
            return type_error

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
            if available.current_state is None:
                # #1356: never print 'None' as if it were a state. With the
                # item_type resolved this is only reachable when no
                # WorkflowItemState could be read or lazily created at all.
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"No workflow state could be resolved for {item_type} "
                    f"{item_id} in this workspace.",
                )
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
                    expected_version=expected_version,
                )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except OptimisticLockError as exc:
            return ToolResult.error("VALIDATION_ERROR", f"Version conflict: {exc}")
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            # #626: reuse "transition" (was the undeclared "approve",
            # silently rejected by full_clean()) -- WorkflowFacade.transition()
            # was just called above, same as #573's outdate->delete/
            # reactivate->transition convention. `operation` (still "approve",
            # this method's only caller) stays as-is for tool_name below.
            operation="transition", entity_type=item_type,
            entity_id=item_id, tool_name=f"review.{operation}", api_key=api_key,
            details={reason_param: reason},
        )
        return ToolResult.ok({"item_id": str(item_id), "new_state": result.new_state})


__all__ = ["ReviewToolGroup"]
