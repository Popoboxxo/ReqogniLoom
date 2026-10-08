"""
MCP Tool Group for the ADR-019 generic suggestion lifecycle (WP3).

leaf_id : ADR-019 WP3 (MCP tool group ``suggestion``: list/accept/reject)
req_id  : REQ-L2-RV-001 (review surface), REQ-L2-MC-009, REQ-L2-MC-012,
          ADR-019

A deliberately thin wrapper over
:class:`application.suggestion_service.SuggestionService` (ADR-01: no domain
logic in the adapter). It exposes the durable proposal inbox to agents:

* ``suggestion.list``   — read-only; lists the ``open`` suggestions of a
  workspace. RBAC read gate (``viewer``), tenant/RLS scoped. Deliberately
  listed in ``tool_registry._READ_ONLY_TOOL_NAMES`` so it is not WRITE-gated.
* ``suggestion.accept`` — write; delegates to the per-kind adapter (for
  ``trace_link`` this runs the existing M2 ``confirm_proposed_link``) and
  stamps the receipt ``accepted``.
* ``suggestion.reject`` — write; delegates to the discard path and stamps the
  receipt ``rejected`` (never destroying the target artifact, ADR-019 7(e)).

Error mapping (ADR-019 003-01, mirrored from the REST taxonomy):

* ``ProducerContextRequiredError`` -> ``PRODUCER_CONTEXT_REQUIRED`` (the REST
  code; 409 Conflict analogue): a production attempt outside an agent/API-key
  context fails closed.
* ``AgentSelfConfirmError`` -> ``PERMISSION_DENIED`` (the REST 403 analogue):
  an agent may not accept/reject its own proposal.
* ``PermissionDeniedError`` -> ``PERMISSION_DENIED``; ``NotFoundError`` ->
  ``NOT_FOUND``; any other ``ValidationError`` -> ``VALIDATION_ERROR``.
"""
from __future__ import annotations

import logging
from typing import Any

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ProducerContextRequiredError,
    ValidationError,
)
from application.trace_link_service import AgentSelfConfirmError
from auth_tenancy.context import AuthContext
from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    mcp_audit_handoff,
    reject_unknown_params,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


class SuggestionToolGroup(BaseToolGroup):
    """``suggestion.*`` tool group — the ADR-019 proposal inbox (WP3)."""

    _TOOL_MAP = {
        "suggestion.list": "_handle_list",
        "suggestion.accept": "_handle_accept",
        "suggestion.reject": "_handle_reject",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "suggestion.list",
            "description": (
                "List the open suggestions (ADR-019 durable proposal inbox) of "
                "a workspace, tenant-scoped. Each entry carries the producer, "
                "the server-set provenance (proposed_by/proposed_at) and the "
                "full payload. Read-only: suggestions whose kind is "
                "'trace_link' point at a real, still-unconfirmed M2 proposal "
                "TraceLink that 'suggestion.accept' confirms."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace whose inbox is read.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "suggestion.accept",
            "description": (
                "Accept an open suggestion: delegates to the existing per-kind "
                "domain path (for 'trace_link' the M2 confirm), then stamps the "
                "receipt accepted with a server-set decided_by/decided_at. An "
                "agent may not accept its own proposal (PERMISSION_DENIED)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "UUID of the suggestion to accept.",
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "suggestion.reject",
            "description": (
                "Reject an open suggestion: delegates to the per-kind discard "
                "path (for 'trace_link' the M2 discard removes the proposal "
                "link, never the linked artifacts), then stamps the receipt "
                "rejected with a server-set decided_by/decided_at."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "UUID of the suggestion to reject.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional human-readable rejection reason.",
                    },
                },
                "required": ["id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # suggestion.list
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from application.suggestion_service import SuggestionService

        workspace_id = require_uuid(params, "workspace_id")
        try:
            suggestions = SuggestionService().list_open(workspace_id, auth_context)
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ProducerContextRequiredError as exc:
            # Not expected on a read, but mapped consistently with the write
            # tools so the error taxonomy is uniform with REST (ADR-019
            # 003-01; REST code PRODUCER_CONTEXT_REQUIRED).
            return ToolResult.error("PRODUCER_CONTEXT_REQUIRED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok({"suggestions": suggestions, "count": len(suggestions)})

    # ------------------------------------------------------------------
    # suggestion.accept
    # ------------------------------------------------------------------

    def _handle_accept(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        return self._decide(
            params=params,
            auth_context=auth_context,
            api_key=api_key,
            decision="accept",
        )

    # ------------------------------------------------------------------
    # suggestion.reject
    # ------------------------------------------------------------------

    def _handle_reject(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        return self._decide(
            params=params,
            auth_context=auth_context,
            api_key=api_key,
            decision="reject",
        )

    # ------------------------------------------------------------------
    # Shared: accept/reject
    # ------------------------------------------------------------------

    def _decide(
        self,
        *,
        params: dict[str, Any],
        auth_context: AuthContext,
        api_key: str,
        decision: str,
    ) -> ToolResult:
        """Accept or reject *id* and write the MCP audit entry.

        The ``mcp_audit_handoff()`` suppresses the Layer-2 service's own audit
        entries for this call so the single MCP entry below is the only one
        (Codeberg #313 / #626 convention).
        """
        from application.suggestion_service import SuggestionService

        # B-01 closure (mirrors comment.resolve): reject an explicit
        # ``workspace_id`` (or any undeclared key). The dispatch gate
        # short-circuits to the caller-supplied workspace when that param is
        # present and never resolves the object's real workspace, so accepting
        # it here would let a caller with WRITE in A decide a suggestion in B.
        # Only the declared schema args are allowed, forcing object-derived
        # workspace resolution in the gate.
        allowed = ["id"] if decision == "accept" else ["id", "reason"]
        reject_unknown_params(params, allowed, f"suggestion.{decision}")

        suggestion_id = require_uuid(params, "id")
        reason = str(params.get("reason") or "").strip()
        service = SuggestionService()

        try:
            with mcp_audit_handoff():
                if decision == "accept":
                    result = service.accept(suggestion_id, auth_context)
                else:
                    result = service.reject(
                        suggestion_id, auth_context, reason=reason
                    )
        except AgentSelfConfirmError as exc:
            # ADR-019 7(c), 003-01: an agent accepting/rejecting its own
            # proposal is a policy denial (REST analogue: 403).
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ProducerContextRequiredError as exc:
            # ADR-019 7(f), 003-01: fail-closed producer context. The code
            # mirrors REST (409 PRODUCER_CONTEXT_REQUIRED), not the generic
            # CONFLICT used for other 409s (#1155 review B-04).
            return ToolResult.error("PRODUCER_CONTEXT_REQUIRED", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            # A suggestion receipt transitions open -> accepted/rejected; there
            # is no CRUD delete of a business entity here (the per-kind adapter
            # owns the real domain write), so "update" is the honest resting op.
            operation="update",
            entity_type="Suggestion",
            entity_id=suggestion_id,
            tool_name=f"suggestion.{decision}",
            api_key=api_key,
            details={
                "decision": result.get("status"),
                "kind": result.get("kind"),
                "reason": reason or None,
            },
        )
        return ToolResult.ok(result)


__all__ = ["SuggestionToolGroup"]
