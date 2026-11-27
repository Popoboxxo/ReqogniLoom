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

Role gate (issue #1362(b)): deciding a ``trace_link`` suggestion is
**human-only by design** — ``confirm_proposed_link``/``discard_proposed_link``
reject every agent principal (``ctx.actor_type == "agent"``, i.e. anything on
a ``reqlo_*`` API key) with ``PERMISSION_DENIED``. That is blanket, not just
"not your own proposal": the ban exists so an AI cannot self-confirm a link it
(or another agent) proposed. The tool descriptions say so, because an agent
that only sees "-32001 An AI agent may not confirm a proposed trace link."
otherwise reads a policy gate as a defect.

Error mapping (ADR-019 003-01, mirrored from the REST taxonomy):

* ``ProducerContextRequiredError`` -> ``PRODUCER_CONTEXT_REQUIRED`` (the REST
  code; 409 Conflict analogue): a production attempt outside an agent/API-key
  context fails closed.
* ``AgentSelfConfirmError`` -> ``PERMISSION_DENIED`` (the REST 403 analogue):
  NO agent principal may accept/reject ANY proposal (the class name is
  historical — the guard is a blanket agent ban, not a self-only check; see
  the role-gate note above).
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
        "suggestion.capture": "_handle_capture",
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
                "receipt accepted with a server-set decided_by/decided_at. "
                "Human-only by design (#1362b): deciding a suggestion is "
                "rejected with PERMISSION_DENIED for every agent principal "
                "(any reqlo_* API key) — an AI agent may not confirm a "
                "proposed trace link, neither its own nor another agent's. "
                "Fail-closed policy, not a defect: confirm from a human "
                "session (REST /api/v1/suggestions/{id}/accept/) instead."
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
                "rejected with a server-set decided_by/decided_at. Same "
                "human-only role gate as suggestion.accept (#1362b): an agent "
                "principal (reqlo_* API key) is rejected with "
                "PERMISSION_DENIED for a trace_link suggestion. Fail-closed "
                "policy; discard from a human session instead."
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
        {
            "name": "suggestion.capture",
            "description": (
                "Turn ONE user message into zero or more open suggestions — "
                "'text in, suggestions out' (ADR-032). The server redacts "
                "secrets, applies the rule filter, deduplicates (idempotency "
                "key, same message, recently rejected), runs ONE stateless LLM "
                "call and validates the answer through the same proposal gate "
                "as interview.formalize. Requires the workspace switch "
                "'capture.enabled' (default off) and an API key granted the "
                "'capture' right; plain text is never stored, only a redacted "
                "excerpt plus its hash. Returns "
                "{created, skipped:{duplicate,filtered,invalid,redacted}, "
                "request_id}. Nothing is created automatically — a human still "
                "accepts each suggestion."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the target workspace. Mandatory — the "
                            "server never guesses a workspace."
                        ),
                    },
                    "text": {
                        "type": "string",
                        "description": (
                            "The user message (max 8000 characters). Redacted "
                            "server-side before storage and before the model "
                            "call."
                        ),
                    },
                    "client": {
                        "type": "string",
                        "enum": [
                            "claude-code",
                            "codex",
                            "opencode",
                            "kimi-code",
                            "antigravity",
                            "hermes",
                            "other",
                        ],
                        "description": "Client that captured the message.",
                    },
                    "source_session": {
                        "type": "string",
                        "maxLength": 255,
                        "description": "Optional client-side session id (max 255).",
                    },
                    "message_id": {
                        "type": "string",
                        "maxLength": 255,
                        "description": (
                            "Optional client-side message id, when the client "
                            "has one (max 255)."
                        ),
                    },
                    "idempotency_key": {
                        "type": "string",
                        "maxLength": 128,
                        "description": (
                            "Optional dedup key; derived from the normalised "
                            "content when omitted."
                        ),
                    },
                },
                "required": ["workspace_id", "text", "client"],
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
    # suggestion.capture
    # ------------------------------------------------------------------

    def _handle_capture(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Turn one user message into suggestions (ADR-032, plan P2).

        All behaviour lives in ``CaptureService`` — this handler validates the
        declared arguments, maps the service's error taxonomy onto the contract
        codes and writes one MCP audit entry.
        """
        from application.ai_derivation_service import LlmProviderUnavailableError
        from application.capture_errors import (
            CaptureDisabledError,
            CaptureRateLimitedError,
            CaptureTextTooLongError,
            WorkspaceForbiddenError,
        )
        from application.capture_service import CaptureService
        from application.capture_update import CaptureConflictError

        allowed = [
            "workspace_id",
            "text",
            "client",
            "source_session",
            "message_id",
            "idempotency_key",
        ]
        reject_unknown_params(params, allowed, "suggestion.capture")

        workspace_id = require_uuid(params, "workspace_id")
        text = params.get("text")
        client = params.get("client")
        if not isinstance(text, str) or not text.strip():
            return ToolResult.error(
                "VALIDATION_ERROR", "'text' is required and must be a string."
            )
        if not isinstance(client, str) or not client.strip():
            return ToolResult.error(
                "VALIDATION_ERROR", "'client' is required and must be a string."
            )

        try:
            result = CaptureService().capture(
                auth_context,
                workspace_id=workspace_id,
                text=text,
                client=client,
                source_session=str(params.get("source_session") or ""),
                message_id=str(params.get("message_id") or ""),
                idempotency_key=str(params.get("idempotency_key") or ""),
            )
        except WorkspaceForbiddenError as exc:
            return ToolResult.error("WORKSPACE_FORBIDDEN", str(exc))
        except CaptureDisabledError as exc:
            return ToolResult.error("CAPTURE_DISABLED", str(exc))
        except CaptureTextTooLongError as exc:
            return ToolResult.error("TEXT_TOO_LONG", str(exc))
        except CaptureRateLimitedError as exc:
            return ToolResult.error("RATE_LIMITED", str(exc))
        except CaptureConflictError as exc:
            return ToolResult.error("CONFLICT", str(exc))
        except LlmProviderUnavailableError as exc:
            # The contract code for "no usable provider" (spec §4.3). Checked
            # before the generic branches because it is not a ValidationError.
            return ToolResult.error("LLM_UNAVAILABLE", str(exc))
        except ProducerContextRequiredError as exc:
            return ToolResult.error("PRODUCER_CONTEXT_REQUIRED", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="Suggestion",
            entity_id=(
                result["created"][0] if result.get("created") else workspace_id
            ),
            tool_name="suggestion.capture",
            api_key=api_key,
            details={
                "request_id": result.get("request_id"),
                "client": client,
                "created": result.get("created"),
                "skipped": result.get("skipped"),
            },
        )
        return ToolResult.ok(result)

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
        from application.capture_update import CaptureConflictError
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
        except CaptureConflictError as exc:
            # ADR-032: a stale ``base_version`` on an update proposal. Checked
            # BEFORE the generic ``ValidationError`` branch — the type is a
            # ``ValidationError`` subclass, so without this order MCP would
            # answer VALIDATION_ERROR where REST answers 409 CONFLICT and the
            # client could not tell "re-read and retry" from "bad request".
            return ToolResult.error("CONFLICT", str(exc))
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
