"""
COMP-MC-010 AuditToolGroup — 3 admin-observability MCP tools (REQ-L1-046).

leaf_id : COMP-MC-010
req_id  : REQ-L1-046 (admin DR / observability),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-011 (structured error response),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented (admin-only):

  audit.query        (read)  — query the audit log with filters
  audit.ai_review    (read)  — SysEng 2.0 N8: bundle SE-Auditor findings into
                                LLM-generated refactoring packages
  events.dlq_list    (read)  — list events in the dead-letter queue
  events.dlq_replay  (write) — replay a single DLQ event back into the outbox

Architecture
------------
* The ``audit.*`` and ``events.*`` namespaces are both owned by this group
  (no other group handles them). The prefix-based router
  (ADR-L3-MC002-03) routes any ``audit.<x>`` and ``events.<x>`` tool to
  this group via the ``"audit"`` and ``"events"`` prefixes registered in
  ``tool_registry._ensure_groups()``.

* All three handlers delegate to the existing service layer and never
  duplicate the business logic:

  - ``audit.query``      -> ``audit.services.query`` (COMP-AL-002)
  - ``audit.ai_review``  -> ``application.ai_review_service.AiReviewService``
    (SysEng 2.0 N8, UMSETZUNGSPLAN_SYSENG_2.0.md §4 Phase 4b) — itself a thin
    wrapper over ``AuditService.run_audit`` (Phase 3) + the LLM adapter; this
    handler duplicates none of that grouping logic.
  - ``events.dlq_list``  -> ``application.dlq_service.DlqService.list_dlq``
  - ``events.dlq_replay``-> ``application.dlq_service.DlqService.replay_dlq_event``

* Admin role enforcement: each handler checks
  ``auth_context.has_role("admin")`` at the very top. The underlying
  ``audit.services.query`` does not enforce admin role (it only sets the
  tenant context), and the DLQ service does check admin role itself as
  defence in depth. The MCP-level check guarantees a clean
  ``PERMISSION_DENIED`` response with no DB roundtrip.
  ``audit.ai_review`` is the one exception: it is a workspace-scoped SE
  copilot, not an admin-observability tool (unlike ``audit.query`` /
  ``events.*``), so it intentionally does NOT gate on the admin role —
  mirroring ``WorkspaceAuditView`` (Phase 3 REST), which any authenticated
  workspace member may call.

* ``events.dlq_replay`` is registered in ``_WRITE_TOOL_PREFIXES`` so the
  RBAC layer (REQ-L2-MC-007) requires at least editor role; the admin
  check is the stricter gate.

* ``events.dlq_replay`` is additionally audited via
  ``write_mcp_audit`` so the agent identity is recorded in the audit log
  (REQ-L2-MC-012). ``audit.query`` and ``events.dlq_list`` are read tools
  and intentionally do NOT write audit entries.

Error mapping (REQ-L2-MC-011):
  NotFoundError           -> NOT_FOUND
  PermissionDeniedError   -> PERMISSION_DENIED
  ValidationError /
  ValueError /
  ParameterError          -> VALIDATION_ERROR

Parameters accepted by ``audit.query`` (all optional):
    actor         : user_id / agent_id string to filter on.
    operation     : ``"create" | "update" | "delete" | "transition"``.
    workspace_id  : accepted for forward-compat. NOTE: ``AuditEntry`` is
                    tenant-scoped (not workspace-scoped), so this filter
                    is not yet applied at the ORM level. A non-empty
                    value is validated as a UUID and ignored.
    start_time    : ISO-8601 timestamp (inclusive lower bound on
                    ``timestamp``).
    end_time      : ISO-8601 timestamp (inclusive upper bound on
                    ``timestamp``).
    limit         : page size, 1..200, default 100.

Parameters accepted by ``events.dlq_list`` (all optional):
    event_type    : filter on ``DomainEventDLQ.event_type``.
    limit         : 1..1000, default 100.

Parameters accepted by ``events.dlq_replay``:
    event_id      : UUID of the original ``DomainEventDLQ.event_id``
                    (required).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from auth_tenancy.context import AuthContext

from application.ai_review_service import AiReviewResponseError, AiReviewService
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from application.dlq_service import DlqService

from audit.models import AuditEntry
from audit.query import AuditQueryFilters
from audit.services import query as audit_query

from persistence.tenancy import TenantContext
from traceability.audit import AuditScope

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    mcp_audit_handoff,
    optional_uuid,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (mirror of audit.query / DlqService limits)
# ---------------------------------------------------------------------------

_AUDIT_MAX_LIMIT: int = 200
_AUDIT_DEFAULT_LIMIT: int = 100
_DLQ_MAX_LIMIT: int = 1000
_DLQ_DEFAULT_LIMIT: int = 100

_VALID_OPERATIONS = frozenset(
    choice for choice, _label in AuditEntry.OP_CHOICES
)

# SysEng 2.0 N8 (audit.ai_review) — mirrors WorkspaceAuditView's
# ``_VALID_SCOPES`` in rest_api/audit_views.py (kept local here to avoid a
# REST -> MCP import).
_VALID_AI_REVIEW_SCOPES = frozenset({"document", "project", "global"})


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _audit_entry_to_dict(entry: AuditEntry) -> Dict[str, Any]:
    """Serialise an AuditEntry ORM object to a JSON-safe dict."""
    return {
        "id": str(entry.id),
        "actor": entry.actor,
        "actor_type": entry.actor_type,
        "operation": entry.op,
        "entity_type": entry.entity_type,
        "entity_id": str(entry.entity_id),
        "entity_version": (
            entry.entity_version
            if getattr(entry, "entity_version", None) is not None
            else None
        ),
        "change_reason": entry.change_reason or "",
        "source": entry.source,
        "client_name": entry.client_name or "",
        "timestamp": (
            entry.timestamp.isoformat()
            if getattr(entry, "timestamp", None) is not None
            else None
        ),
    }


def _dlq_row_to_dict(row: Any) -> Dict[str, Any]:
    """Serialise a DomainEventDLQ row (or _DlqSnapshot) to a dict."""
    return {
        "id": str(row.id) if getattr(row, "id", None) else None,
        "event_id": str(row.event_id),
        "event_type": row.event_type,
        "workspace_id": str(row.workspace_id),
        "entity_id": str(row.entity_id),
        "payload": dict(getattr(row, "payload", {}) or {}),
        "error_message": row.error_message or "",
        "retry_count": int(getattr(row, "retry_count", 0) or 0),
        "moved_at": (
            row.moved_at.isoformat()
            if getattr(row, "moved_at", None) is not None
            else None
        ),
    }


def _parse_iso8601(raw: Any, field_name: str) -> datetime:
    """Parse an ISO-8601 string into a ``datetime``.

    Accepts both ``...Z`` (Zulu) and ``...+00:00`` (offset) suffixes.
    Naive datetimes are interpreted as UTC.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ParameterError(
            f"Parameter '{field_name}' must be a non-empty ISO-8601 string."
        )
    text = raw.strip()
    # Python <3.11 does not natively accept "Z"; normalise to "+00:00".
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ParameterError(
            f"Parameter '{field_name}' is not a valid ISO-8601 timestamp: {exc}"
        ) from exc
    if parsed.tzinfo is None:
        # Treat naive timestamps as UTC.
        parsed = parsed.replace(tzinfo=__import__("datetime").timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# AuditToolGroup
# ---------------------------------------------------------------------------


class AuditToolGroup(BaseToolGroup):
    """COMP-MC-010 — Audit / DLQ MCP tool group (3 tools, admin-only)."""

    _TOOL_MAP = {
        "audit.query": "_handle_audit_query",
        "audit.ai_review": "_handle_ai_review",
        "events.dlq_list": "_handle_dlq_list",
        "events.dlq_replay": "_handle_dlq_replay",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "audit.query",
            "description": "Query the audit log with filters (admin-only, read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "actor": {"type": "string", "description": "Actor user/agent id filter."},
                    "operation": {
                        "type": "string",
                        "description": "Operation filter (create|update|delete|transition).",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Reserved forward-compat UUID (validated, not applied).",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "ISO-8601 inclusive lower bound on timestamp.",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "ISO-8601 inclusive upper bound on timestamp.",
                    },
                    "limit": {"type": "integer", "description": "Page size (1..200, default 100)."},
                },
            },
        },
        {
            "name": "audit.ai_review",
            "description": (
                "SysEng 2.0 N8: run the SE-Auditor for a workspace and bundle "
                "its findings into strategic refactoring packages via the LLM "
                "adapter (mock by default). Read-only/advisory — nothing is "
                "persisted; every returned finding reference is a real finding "
                "from this audit run."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the target workspace.",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Optional baseline scope (document|project|global).",
                    },
                    "scope_artifact_id": {
                        "type": "string",
                        "description": "Required when scope=document (subtree root).",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "events.dlq_list",
            "description": "List Domain-Event dead-letter-queue entries (admin-only, read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "event_type": {"type": "string", "description": "Optional event_type filter."},
                    "limit": {"type": "integer", "description": "Page size (1..1000, default 100)."},
                },
            },
        },
        {
            "name": "events.dlq_replay",
            "description": "Replay a single DLQ event back into the outbox (admin-only, write, audited).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the original DomainEventDLQ.event_id.",
                    },
                },
                "required": ["event_id"],
            },
        },
    ]

    def __init__(
        self,
        dlq_service: Optional[DlqService] = None,
        ai_review_service: Optional[AiReviewService] = None,
    ) -> None:
        # No constructor injection for the audit query — we always go
        # through the module-level ``audit.services.query`` facade so
        # that the tenant-context setup is the same as the REST adapter.
        self._dlq_service = dlq_service or DlqService()
        self._ai_review_service = ai_review_service or AiReviewService()

    # ------------------------------------------------------------------
    # Common admin gate
    # ------------------------------------------------------------------

    @staticmethod
    def _check_admin(auth_context: AuthContext) -> Optional[ToolResult]:
        """Return a ``PERMISSION_DENIED`` ToolResult if the caller is not admin.

        Returns ``None`` when the caller has the admin role (i.e. the
        gate is open). The result is intentionally a ``ToolResult`` (not
        an exception) because the ``BaseToolGroup.execute_tool``
        dispatcher only maps ``ParameterError`` -> ``VALIDATION_ERROR``;
        anything else falls through to ``INTERNAL_ERROR``. Returning a
        ``ToolResult`` keeps the MCP response clean.
        """
        if auth_context.has_role("admin"):
            return None
        return ToolResult.error(
            "PERMISSION_DENIED",
            f"Permission denied: role 'admin' required, "
            f"user has {auth_context.active_roles}",
        )

    # ------------------------------------------------------------------
    # audit.query (read)
    # ------------------------------------------------------------------

    def _handle_audit_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """audit.query — query the audit log with filters (admin-only).

        Optional params (all named in the tool schema):
            actor        : actor user/agent id.
            operation    : ``"create" | "update" | "delete" | "transition"``.
            workspace_id : reserved (AuditEntry is tenant-scoped).
            start_time   : ISO-8601 inclusive lower bound on ``timestamp``.
            end_time     : ISO-8601 inclusive upper bound on ``timestamp``.
            limit        : page size, 1..200, default 100.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        # Validate operation
        operation = params.get("operation")
        if operation is not None and operation != "":
            if operation not in _VALID_OPERATIONS:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Parameter 'operation' must be one of "
                    f"{sorted(_VALID_OPERATIONS)}.",
                )
        else:
            operation = None

        # Validate actor
        actor_raw = params.get("actor")
        if actor_raw is not None and actor_raw != "":
            if not isinstance(actor_raw, str):
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Parameter 'actor' must be a string.",
                )
            actor = actor_raw.strip() or None
        else:
            actor = None

        # workspace_id is reserved / forward-compat: validate the type but
        # do not apply (AuditEntry is tenant-scoped, not workspace-scoped).
        workspace_id_raw = params.get("workspace_id")
        if workspace_id_raw is not None and workspace_id_raw != "":
            # Will raise ParameterError (mapped to VALIDATION_ERROR) if malformed.
            _ = optional_uuid({"workspace_id": workspace_id_raw}, "workspace_id")

        # Time-range params
        try:
            start_time = (
                _parse_iso8601(params["start_time"], "start_time")
                if params.get("start_time") not in (None, "")
                else None
            )
            end_time = (
                _parse_iso8601(params["end_time"], "end_time")
                if params.get("end_time") not in (None, "")
                else None
            )
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if start_time is not None and end_time is not None:
            if start_time > end_time:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Parameter 'start_time' must be <= 'end_time'.",
                )

        # limit
        limit_raw = params.get("limit", _AUDIT_DEFAULT_LIMIT)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'limit' must be an integer.",
            )
        if limit < 1 or limit > _AUDIT_MAX_LIMIT:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'limit' must be in 1..{_AUDIT_MAX_LIMIT}.",
            )

        filters = AuditQueryFilters(
            actor=actor,
            operation=operation,
            timestamp_from=start_time,
            timestamp_to=end_time,
        )

        # Set tenant context so AuditLogQuery's manager-level filter works.
        TenantContext.set_tenant(auth_context.tenant_id)

        try:
            result = audit_query(
                filters=filters,
                page=1,
                page_size=limit,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        entries: List[Dict[str, Any]] = [
            _audit_entry_to_dict(e) for e in result.entries
        ]
        return ToolResult.ok(
            {
                "entries": entries,
                "total": result.total,
                "page": result.page,
                "page_size": result.page_size,
            }
        )

    # ------------------------------------------------------------------
    # audit.ai_review (read) — SysEng 2.0 N8
    # ------------------------------------------------------------------

    def _handle_ai_review(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """audit.ai_review — bundle SE-Auditor findings into refactoring packages.

        Required params:
            workspace_id : UUID of the target workspace.
        Optional params:
            scope             : ``"document" | "project" | "global"``.
            scope_artifact_id : required when ``scope == "document"``.

        No admin gate (see module docstring) — any authenticated caller with
        access to the workspace may run it, mirroring the Phase-3 REST
        endpoint this tool sits next to.
        """
        workspace_id = require_uuid(params, "workspace_id")

        scope = params.get("scope")
        scopes = None
        if scope:
            if scope not in _VALID_AI_REVIEW_SCOPES:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Parameter 'scope' must be one of "
                    f"{sorted(_VALID_AI_REVIEW_SCOPES)}.",
                )
            scope_artifact_id = params.get("scope_artifact_id") or None
            if scope == "document" and not scope_artifact_id:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Parameter 'scope_artifact_id' is required when scope=document.",
                )
            scopes = [AuditScope(scope, artifact_id=scope_artifact_id)]

        try:
            result = self._ai_review_service.review(
                workspace_id, auth_context, scopes=scopes
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AiReviewResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok(result.to_dict())

    # ------------------------------------------------------------------
    # events.dlq_list (read)
    # ------------------------------------------------------------------

    def _handle_dlq_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """events.dlq_list — list DLQ entries (admin-only).

        Optional params:
            event_type : filter on ``DomainEventDLQ.event_type``.
            limit      : 1..1000, default 100.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        event_type = params.get("event_type")
        if event_type is not None and event_type != "":
            if not isinstance(event_type, str):
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    "Parameter 'event_type' must be a string.",
                )
            event_type = event_type.strip() or None
        else:
            event_type = None

        limit_raw = params.get("limit", _DLQ_DEFAULT_LIMIT)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'limit' must be an integer.",
            )
        if limit < 1 or limit > _DLQ_MAX_LIMIT:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'limit' must be in 1..{_DLQ_MAX_LIMIT}.",
            )

        try:
            rows = self._dlq_service.list_dlq(
                auth_context, event_type=event_type, limit=limit
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok(
            {
                "events": [_dlq_row_to_dict(r) for r in rows],
                "count": len(rows),
            }
        )

    # ------------------------------------------------------------------
    # events.dlq_replay (write, audited)
    # ------------------------------------------------------------------

    def _handle_dlq_replay(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """events.dlq_replay — replay a single DLQ event (admin-only, write).

        Required params:
            event_id : UUID of the original ``DomainEventDLQ.event_id``.

        The event is re-inserted into the outbox with a fresh retry
        budget. The MCP wrapper writes an additional audit entry so the
        agent identity (and api-key hash) is recorded in the audit log
        in addition to the service-level audit entry.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        event_id = require_uuid(params, "event_id")

        try:
            # Codeberg #313: suppress replay_dlq_event's single internal
            # _audit() call for the same entity — write_mcp_audit below is
            # the sole entry.
            with mcp_audit_handoff():
                snapshot = self._dlq_service.replay_dlq_event(
                    auth_context, event_id=event_id
                )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        # MCP-level audit (REQ-L2-MC-012): record the agent identity.
        write_mcp_audit(
            ctx=auth_context,
            operation="replay",
            entity_type="DomainEventDLQ",
            entity_id=event_id,
            tool_name="events.dlq_replay",
            api_key=api_key,
            details={
                "event_type": snapshot.event_type,
                "workspace_id": str(snapshot.workspace_id),
                "entity_id": str(snapshot.entity_id),
                "previous_retry_count": snapshot.retry_count,
            },
        )

        return ToolResult.ok(
            {
                "replayed": True,
                "event": _dlq_row_to_dict(snapshot),
            }
        )


__all__ = ["AuditToolGroup"]
