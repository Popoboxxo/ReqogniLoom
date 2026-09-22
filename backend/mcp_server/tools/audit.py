"""
COMP-MC-010 AuditToolGroup — 3 admin-observability MCP tools (REQ-L1-046).

leaf_id : COMP-MC-010
req_id  : REQ-L1-046 (admin DR / observability),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-011 (structured error response),
          REQ-L2-MC-012 (MCP audit trail)

Tools implemented:

  audit.query        (read)  — query the audit log with filters (admin-only)
  audit.ai_review    (read)  — SysEng 2.0 N8: bundle SE-Auditor findings into
                                LLM-generated refactoring packages
  audit.se_audit     (read)  — raw SE-Auditor run (issue #410); AUTHOR tier
  audit.waive_finding(write) — grant a per-finding suppression (#569);
                                ADMIN tier via _GOVERNANCE_TOOL_NAMES
  audit.waivers      (read)  — list the workspace's suppressions (#569);
                                approval-authority gated (REST E12 parity)
  events.dlq_list    (read)  — list events in the dead-letter queue (admin-only)
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
  AiReviewResponseError /
  LlmResponseError        -> INTERNAL_ERROR (``audit.ai_review``; the provider
                             failure / daily token budget must never fall
                             through to the bare catch-all — issue #951)

  #569 suppression errors (``audit.waive_finding``, spec §3.4.2/§3.5) — listed
  before the generic ``ValidationError`` branch because all three are
  ``ValidationError`` subclasses:
  WaiverReasonPolicyViolation   -> WAIVER_REASON_REJECTED
  WaiverFindingNotBlockingError -> WAIVER_FINDING_NOT_BLOCKING
  SuppressionExpiredError       -> SUPPRESSION_EXPIRED
  These three codes are deliberately absent from
  ``protocol_handler._PROTOCOL_ERROR_CODES``: on ``tools/call`` they surface as
  a successful JSON-RPC result with ``result.isError == true`` and the string
  ``error_code`` (spec §3.5/R3-02), never as a numeric JSON-RPC code.

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

from application.ai_derivation_service import LlmResponseError
from application.ai_review_service import AiReviewResponseError, AiReviewService
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    SuppressionExpiredError,
    ValidationError,
    WaiverFindingNotBlockingError,
    WaiverReasonPolicyViolation,
)
from application.dlq_service import DlqService

from baseline.exceptions import GovernanceAuthorityError
from baseline.waivers import assert_gate_waiver_authority

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
    require_param,
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

# issue #410 (audit.se_audit): the three rigor presets the SE-Auditor engine
# resolves a rule set for (``traceability.audit.registry.RULE_PRESET_MAP``).
_VALID_SE_TIERS = frozenset({"minimal", "standard", "extended"})

# #569 (audit.waive_finding / audit.waivers) — mirrors rest_api/audit_views.py
# (kept local to avoid a REST -> MCP import, same rationale as
# ``_VALID_AI_REVIEW_SCOPES`` above).
_VALID_SUPPRESSION_SCOPES = frozenset({"document", "project", "global"})

#: Suppression lifecycle states accepted by ``audit.waivers`` ``state``
#: (#569/m2). ``active`` is the default; anything else is a 400.
_VALID_WAIVER_STATES = frozenset({"active", "expired", "all"})


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


def _parse_suppression_expires_at(raw: Any) -> Optional[datetime]:
    """Parse an optional ISO-8601 suppression expiry, preserving naivety.

    Unlike :func:`_parse_iso8601` this must NOT silently attach UTC to an
    offset-less timestamp: #569/E3/D2 requires a naive ``expires_at`` to be
    *rejected* (400), because an expiry the caller did not fully specify must
    not be reinterpreted behind its back. The parsed value (naive or aware) is
    handed to ``AuditService.suppress_finding``, whose defensive guard owns the
    decision — so this helper only answers "is it a parseable ISO-8601 string?".

    ``None``/absent -> ``None`` (unbounded). A malformed value raises
    :class:`ParameterError`, which the dispatcher maps to ``VALIDATION_ERROR``.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if not isinstance(raw, str):
        raise ParameterError(
            "Parameter 'expires_at' must be an ISO-8601 string or null."
        )
    text = raw.strip()
    # Python <3.11 does not natively accept "Z"; normalise to "+00:00".
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ParameterError(
            f"Parameter 'expires_at' is not a valid ISO-8601 timestamp: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# AuditToolGroup
# ---------------------------------------------------------------------------


class AuditToolGroup(BaseToolGroup):
    """COMP-MC-010 — Audit / DLQ MCP tool group (3 tools, admin-only)."""

    _TOOL_MAP = {
        "audit.query": "_handle_audit_query",
        "audit.ai_review": "_handle_ai_review",
        # issue #410: the raw SE-Auditor run (no LLM), for agents that need
        # the findings themselves rather than a refactoring bundle.
        "audit.se_audit": "_handle_se_audit",
        # #569: standalone per-finding suppression surface over the L2 facade
        # (AuditService.suppress_finding / list_suppressions).
        "audit.waive_finding": "_handle_waive_finding",
        "audit.waivers": "_handle_waivers",
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
            "name": "audit.se_audit",
            "description": (
                "Run the SE-Auditor for a workspace and return the findings "
                "directly (issue #410) — no LLM wrapping, unlike audit.ai_review. "
                "Rigor tier is resolved from the workspace preset unless "
                "``tier`` is given. Response: result.tier, result.counts "
                "{total, blockers, warnings}, result.truncated, "
                "result.total_findings_available, result.findings "
                "[{index, rule_id, severity, message, artifact_ids, remediation}]. "
                "Findings are capped at 500; use ``limit``+``offset`` to page."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace to audit.",
                    },
                    "tier": {
                        "type": "string",
                        "description": (
                            "Optional rigor tier override "
                            "(minimal|standard|extended). Defaults to the "
                            "workspace's active preset."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Optional page size (max 500) for walking past the cap.",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Optional start offset; only used together with limit.",
                    },
                    "include_suppressed": {
                        "type": "boolean",
                        "description": (
                            "#569: keep suppressed findings in the report "
                            "(default true — nothing is hidden; suppressed "
                            "findings are marked with suppressed/reason/expiry). "
                            "Set false to filter them out."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "audit.waive_finding",
            "description": (
                "#569: grant a per-finding suppression (waiver) for a reported "
                "BLOCKER SE-Auditor finding, with a mandatory written "
                "justification. Takes away the finding's gate-blocking effect "
                "but keeps it visible and audited (who, what, why, until when). "
                "Requires approval authority (Admin/Approver and, for API keys, "
                "the ADMIN tier). Response: the persisted suppression "
                "(waiver_id, finding_key, identity_key, scope, reason, "
                "granted_by, created_at, expires_at, state) plus 'created' "
                "(false on an idempotent replay of an identical active waiver)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the target workspace.",
                    },
                    "rule_id": {
                        "type": "string",
                        "description": "SE-Auditor rule being suppressed, e.g. 'TRACE-P1'.",
                    },
                    "artifact_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Artifacts the finding concerns, as returned by the "
                            "audit report (empty for graph-level findings)."
                        ),
                    },
                    "scope": {
                        "type": "string",
                        "description": (
                            "Optional baseline scope used only to locate the "
                            "finding for the existence check "
                            "(document|project|global). The persisted scope "
                            "always comes from the matched finding."
                        ),
                    },
                    "scope_artifact_id": {
                        "type": "string",
                        "description": "Document root; required when scope='document'.",
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "Mandatory justification for accepting this single "
                            "deviation; recorded on the waiver and in the audit "
                            "log. A placeholder is rejected with "
                            "WAIVER_REASON_REJECTED."
                        ),
                    },
                    "expires_at": {
                        "type": "string",
                        "description": (
                            "Optional expiry (ISO-8601, timezone-aware). "
                            "Omitted/null means unbounded; an already-past or "
                            "naive value is rejected with VALIDATION_ERROR."
                        ),
                    },
                },
                "required": ["workspace_id", "rule_id", "reason"],
            },
        },
        {
            "name": "audit.waivers",
            "description": (
                "#569: list the workspace's per-finding suppressions, filtered "
                "by lifecycle state (active|expired|all, default active). "
                "Requires the same approval authority as the REST twin "
                "GET .../audit/waivers/ (spec E12) — an Editor or an "
                "AUTHOR-tier API key gets PERMISSION_DENIED. Response: "
                "{waivers: [...], counts: {active, expired}}; counts describe "
                "the whole set so a filter never hides anything."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the target workspace.",
                    },
                    "state": {
                        "type": "string",
                        "description": (
                            "Optional lifecycle filter: active|expired|all "
                            "(default active)."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "events.dlq_list",
            "description": "List Domain-Event dead-letter-queue entries for one workspace (admin-only, read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace to list DLQ entries for. "
                            "Required — DomainEventDLQ has no tenant scoping of "
                            "its own, and narrows the admin-role check to this "
                            "workspace specifically."
                        ),
                    },
                    "event_type": {"type": "string", "description": "Optional event_type filter."},
                    "limit": {"type": "integer", "description": "Page size (1..1000, default 100)."},
                },
                "required": ["workspace_id"],
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
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "UUID of the workspace the event belongs to. "
                            "Required — see events.dlq_list's description."
                        ),
                    },
                },
                "required": ["event_id", "workspace_id"],
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
        except LlmResponseError as exc:
            # #951: the daily-token-budget failure (REQ-106) is raised by the
            # service *before* the provider is called and was the one
            # provider-adjacent failure this handler did not map. It therefore
            # fell through to the generic catch-all in
            # ``BaseToolGroup.execute_tool``, which replaces the documented,
            # actionable budget message with a bare
            # "An internal error occurred." — indistinguishable from a crash,
            # which is exactly what the issue reports. Mapped exactly like the
            # sibling LLM tool groups (``tools/ai_derivation.py``,
            # ``tools/requirement_bundle.py``).
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok(result.to_dict())

    # ------------------------------------------------------------------
    # audit.se_audit (read, issue #410)
    # ------------------------------------------------------------------

    def _handle_se_audit(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """audit.se_audit — run the SE-Auditor for a workspace (read-only).

        Required params:
            workspace_id : UUID of the target workspace.
        Optional params:
            tier               : rigor tier override (minimal|standard|extended).
            limit              : page size (max 500).
            offset             : start offset (only with limit).
            include_suppressed : #569 — keep suppressed findings in the report
                                 (default true; suppressed findings are marked).

        No admin gate (mirrors audit.ai_review): it is a workspace-scoped,
        read-only audit run any workspace member may call; the required
        ``workspace_id`` narrows the read-scoping RBAC gate to that workspace.
        """
        workspace_id = require_uuid(params, "workspace_id")

        tier = params.get("tier")
        if tier is not None and tier not in _VALID_SE_TIERS:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'tier' must be one of {sorted(_VALID_SE_TIERS)}.",
            )

        limit = params.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                return ToolResult.error(
                    "VALIDATION_ERROR", "Parameter 'limit' must be an integer."
                )
        offset = params.get("offset", 0)
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'offset' must be an integer."
            )

        # #569/m2: strict parse — only true/false (case-insensitive); absent
        # keeps the service default (True, O3). Only forwarded when the caller
        # named it, so the pre-#569 call shape is unchanged.
        include_suppressed: Optional[bool] = None
        raw_include_suppressed = params.get("include_suppressed")
        if raw_include_suppressed is not None:
            if isinstance(raw_include_suppressed, bool):
                include_suppressed = raw_include_suppressed
            else:
                lowered = str(raw_include_suppressed).strip().lower()
                if lowered == "true":
                    include_suppressed = True
                elif lowered == "false":
                    include_suppressed = False
                else:
                    return ToolResult.error(
                        "VALIDATION_ERROR",
                        "Parameter 'include_suppressed' must be 'true' or 'false'.",
                    )

        from application.audit_service import AuditService

        run_kwargs: Dict[str, Any] = {
            "tier": tier,
            "limit": limit,
            "offset": offset,
        }
        if include_suppressed is not None:
            run_kwargs["include_suppressed"] = include_suppressed

        try:
            report = AuditService().run_audit(
                workspace_id, auth_context, **run_kwargs
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok(report.to_dict())

    # ------------------------------------------------------------------
    # audit.waive_finding (write, governance-gated) — #569
    # ------------------------------------------------------------------

    def _handle_waive_finding(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """audit.waive_finding — grant a per-finding suppression (#569).

        Delegates exclusively to ``AuditService.suppress_finding`` (ADR-01);
        the handler adds no second, weaker waiver path. The service owns the
        authority choke point, the reason policy, the blocker-only existence
        check and the persisted row; this handler only shapes the params and
        translates the typed errors into MCP error codes.

        Required params:
            workspace_id : UUID of the target workspace.
            rule_id      : SE-Auditor rule being suppressed.
            reason       : mandatory justification (a placeholder is rejected
                           with ``WAIVER_REASON_REJECTED``).
        Optional params:
            artifact_ids      : artifacts the finding concerns (default []).
            scope             : document|project|global — used only for the
                                existence check; the persisted scope comes from
                                the matched finding.
            scope_artifact_id : document root; required when scope='document'.
            expires_at        : optional ISO-8601 expiry; null = unbounded.

        No admin gate inside the handler: the facade's shared SSOT choke point
        (``baseline.waivers.assert_gate_waiver_authority``) decides authority,
        and the registry additionally requires the ADMIN tier via
        ``_GOVERNANCE_TOOL_NAMES``.
        """
        workspace_id = require_uuid(params, "workspace_id")
        rule_id = require_param(params, "rule_id")

        raw_artifacts = params.get("artifact_ids") or []
        if not isinstance(raw_artifacts, (list, tuple)):
            raise ParameterError(
                "Parameter 'artifact_ids' must be an array of strings."
            )
        artifact_ids = [str(a) for a in raw_artifacts]

        scope = params.get("scope")
        if scope is not None and str(scope).strip():
            scope = str(scope).strip()
            if scope not in _VALID_SUPPRESSION_SCOPES:
                return ToolResult.error(
                    "VALIDATION_ERROR",
                    f"Parameter 'scope' must be one of "
                    f"{sorted(_VALID_SUPPRESSION_SCOPES)}.",
                )
        else:
            scope = None

        scope_artifact_id = params.get("scope_artifact_id")
        if scope_artifact_id is not None:
            scope_artifact_id = str(scope_artifact_id).strip() or None
        # scope='document' without a document root is rejected by the service
        # (400 VALIDATION_ERROR, never 422) — same rule as the REST twin.

        # Deliberately NOT require_param: a missing/blank justification is a
        # policy violation (WAIVER_REASON_REJECTED), not a shape error.
        reason = params.get("reason", "")

        try:
            expires_at = _parse_suppression_expires_at(params.get("expires_at"))
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        from application.audit_service import AuditService

        try:
            # Codeberg #313: suppress the facade's own baseline.waiver_create
            # entry for this entity — the write_mcp_audit call below (with the
            # agent identity, REQ-L2-MC-012) is the sole audit entry for a
            # newly created waiver.
            with mcp_audit_handoff():
                view, created = AuditService().suppress_finding(
                    workspace_id,
                    auth_context,
                    rule_id=rule_id,
                    artifact_ids=artifact_ids,
                    scope=scope,
                    scope_artifact_id=scope_artifact_id,
                    reason=reason,
                    expires_at=expires_at,
                )
        except WaiverReasonPolicyViolation as exc:
            return ToolResult.error("WAIVER_REASON_REJECTED", str(exc))
        except WaiverFindingNotBlockingError as exc:
            return ToolResult.error("WAIVER_FINDING_NOT_BLOCKING", str(exc))
        except SuppressionExpiredError as exc:
            return ToolResult.error("SUPPRESSION_EXPIRED", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except (ValidationError, ValueError) as exc:
            # Remaining shape/invariant failures (invalid scope, missing
            # document root, naive/past expiry). Deliberately 400 — never 422.
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if created:
            # #569/E2: one baseline.waiver_create entry per *newly created*
            # waiver — an idempotent replay writes nothing (AC-569-04 spirit).
            write_mcp_audit(
                ctx=auth_context,
                operation="baseline.waiver_create",
                entity_type="BaselineGateWaiver",
                entity_id=view.waiver_id,
                tool_name="audit.waive_finding",
                api_key=api_key,
                details={
                    "finding_key": view.finding_key,
                    "workspace_id": str(workspace_id),
                    "rule_id": view.rule_id,
                    "artifact_ids": list(view.artifact_ids),
                    "scope": view.scope,
                    "scope_artifact_id": view.scope_artifact_id,
                    "expires_at": (
                        view.expires_at.isoformat() if view.expires_at else None
                    ),
                    "granted_by": view.granted_by,
                    "reason": view.reason,
                },
            )

        payload = view.to_dict()
        payload["created"] = created
        return ToolResult.ok(payload)

    # ------------------------------------------------------------------
    # audit.waivers (read, authority-gated) — #569
    # ------------------------------------------------------------------

    def _handle_waivers(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """audit.waivers — list the workspace's suppressions (#569).

        Required params:
            workspace_id : UUID of the target workspace.
        Optional params:
            state : active|expired|all (default active).

        Deliberate transport-parity decision (spec §3.5 vs REST E12): the tool
        is a *read* at the scope gate (``_READ_ONLY_TOOL_NAMES``, so no ADMIN
        capability tier is required to reach the handler), but the handler
        evaluates the very same approval-authority choke point as the REST twin
        ``GET .../audit/waivers/`` and answers ``PERMISSION_DENIED`` for a
        caller without it. This is intentionally STRICTER than the plain READ
        tier the spec's tool table implies: suppression records are governance
        *management* metadata (who suppressed what and why), and reading them
        through a weaker door on MCP than on REST would be an asymmetry a
        caller could exploit by switching transport.
        """
        workspace_id = require_uuid(params, "workspace_id")

        state = params.get("state") or "active"
        if state not in _VALID_WAIVER_STATES:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Parameter 'state' must be one of "
                f"{sorted(_VALID_WAIVER_STATES)}.",
            )

        # REST E12 parity: the suppression list is the governance management
        # surface, so it needs the same approval authority as the grant path.
        try:
            assert_gate_waiver_authority(auth_context)
        except GovernanceAuthorityError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        from application.audit_service import AuditService

        try:
            all_views = AuditService().list_suppressions(
                workspace_id, auth_context, state="all"
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except (ValidationError, ValueError) as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        counts = {
            "active": sum(1 for v in all_views if v.state == "active"),
            "expired": sum(1 for v in all_views if v.state == "expired"),
        }
        waivers = [
            v.to_dict() for v in all_views if state == "all" or v.state == state
        ]
        return ToolResult.ok({"waivers": waivers, "counts": counts})

    # ------------------------------------------------------------------
    # events.dlq_list (read)
    # ------------------------------------------------------------------

    def _handle_dlq_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """events.dlq_list — list DLQ entries for one workspace (admin-only).

        Required params:
            workspace_id : UUID of the target workspace.
        Optional params:
            event_type : filter on ``DomainEventDLQ.event_type``.
            limit      : 1..1000, default 100.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        workspace_id = require_uuid(params, "workspace_id")

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
                auth_context, workspace_id=workspace_id, event_type=event_type, limit=limit
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
            event_id     : UUID of the original ``DomainEventDLQ.event_id``.
            workspace_id : UUID of the workspace the event belongs to.

        The event is re-inserted into the outbox with a fresh retry
        budget. The MCP wrapper writes an additional audit entry so the
        agent identity (and api-key hash) is recorded in the audit log
        in addition to the service-level audit entry.
        """
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied

        event_id = require_uuid(params, "event_id")
        workspace_id = require_uuid(params, "workspace_id")

        try:
            # Codeberg #313: suppress replay_dlq_event's single internal
            # _audit() call for the same entity — write_mcp_audit below is
            # the sole entry.
            with mcp_audit_handoff():
                snapshot = self._dlq_service.replay_dlq_event(
                    auth_context, event_id=event_id, workspace_id=workspace_id
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
            # #626: new "events.replay" choice -- DLQ replay has no REST
            # pendant to reuse (was the undeclared "replay", silently
            # rejected by full_clean()).
            operation="events.replay",
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
