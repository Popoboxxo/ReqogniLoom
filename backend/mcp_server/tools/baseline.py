"""
COMP-MC-003-style BaselineToolGroup — Baseline MCP tool group (issue #114).

leaf_id : COMP-AS-006 (BaselineFacade, wrapped via application.baseline_facade)
req_id  : REQ-L1-018, REQ-L2-AS-006, REQ-L2-AS-007, REQ-L2-MC-012 (MCP audit trail)

Tools implemented:
  baseline.create   — create an immutable baseline snapshot (write, audited)
  baseline.list     — list baseline summaries for a workspace
  baseline.get      — fetch full baseline detail (including delta entries)
  baseline.compare  — structural diff between two baselines
  baseline.set_tags — replace the tag set of one baseline (F4.2, write, audited)
  baseline.rollback_preview — what an additive rollback would change (F4.4, read)
  baseline.rollback_request — open the CCB change request (F4.4, write, audited)
  baseline.rollback_apply   — execute an approved rollback (F4.4, write, humans only)

The ``BaselineFacade`` (application/baseline_facade.py) already exists and is
reachable via REST/UI (rest_api/views.py's BaselineViewSet) — this tool group
is the missing MCP-side wrapper so an MCP agent can complete the
"need -> requirements -> links -> architecture/test -> baseline" workflow
without dropping to the REST API for the last step.

Unlike ``DiagramToolGroup`` (which wraps plain module-level functions),
``BaselineFacade`` is a ``ServiceBase`` subclass — same shape as
``RequirementService``/``ArchitectureService`` — so this tool group follows
the ``needs.py``/``architecture.py`` pattern: instantiate the facade, call it
directly with ``ctx=auth_context``, and translate its typed exceptions
(``PermissionDeniedError``, ``ValidationError``, ``NotFoundError``) into
``ToolResult`` errors. ``BaselineFacade.create_baseline`` already calls
``ServiceBase._assert_write_permission`` internally, so no separate
defense-in-depth check is needed here (unlike ``diagram.py``).
"""
from __future__ import annotations

import logging
from typing import Any

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.baseline_facade import BaselineFacade
from application.baseline_rollback_service import (
    BaselineRollbackService,
    RollbackEmptyError,
    RollbackError,
    RollbackForbiddenError,
    RollbackTooLargeError,
)
from application.change_request_service import ChangeRequestDTO, ChangeRequestService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    mcp_audit_handoff,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)


def _baseline_summary_to_dict(summary: Any) -> dict[str, Any]:
    """Serialise a ``baseline.types.BaselineSummary`` for MCP responses."""
    return {
        "baseline_id": str(summary.baseline_id),
        "workspace_id": str(summary.workspace_id),
        "scope": summary.scope,
        "name": summary.name,
        "description": summary.description,
        "created_at": summary.created_at.isoformat() if summary.created_at else None,
        "created_by": summary.created_by,
        "tags": list(getattr(summary, "tags", []) or []),
    }


def _baseline_detail_to_dict(detail: Any) -> dict[str, Any]:
    """Serialise a ``baseline.types.BaselineDetail`` for MCP responses."""
    payload = _baseline_summary_to_dict(detail)
    payload["entries"] = [
        {
            "item_id": entry.item_id,
            "version": entry.version,
            "entity_type": entry.entity_type,
        }
        for entry in detail.entries
    ]
    return payload


class BaselineToolGroup(BaseToolGroup):
    """Baseline tool group (8 tools) — wraps ``application.baseline_facade.BaselineFacade``.

    The three ``rollback_*`` tools wrap ``application.baseline_rollback_service``
    (Plan F F4.4, ADR-025): the facade owns baselines, the rollback service owns
    the additive restore. Both are called directly with ``auth_context`` and
    their typed exceptions are translated into ``ToolResult`` errors here.
    """

    _TOOL_MAP = {
        "baseline.create": "_handle_create",
        "baseline.list": "_handle_list",
        "baseline.get": "_handle_get",
        "baseline.compare": "_handle_compare",
        "baseline.set_tags": "_handle_set_tags",
        "baseline.rollback_preview": "_handle_rollback_preview",
        "baseline.rollback_request": "_handle_rollback_request",
        "baseline.rollback_apply": "_handle_rollback_apply",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "baseline.create",
            "description": "Create an immutable Baseline snapshot for a workspace (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the target workspace."},
                    "scope": {
                        "type": "string",
                        "description": "One of 'document' | 'project' | 'global'.",
                    },
                    "name": {"type": "string", "description": "Human-readable baseline name (unique per workspace)."},
                    "description": {"type": "string", "description": "Optional description."},
                    "document_id": {
                        "type": "string",
                        "description": "Document Artifact UUID — required when scope='document'.",
                    },
                    "override_reason": {
                        "type": "string",
                        "description": (
                            "Written justification for creating the baseline "
                            "although the SE-Auditor reports blocking findings "
                            "(GH-513). Requires the 'admin' or 'approver' role; "
                            "recorded in the audit log and on the baseline. "
                            "Omit it to keep the default fail-closed behaviour."
                        ),
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional labels for the new baseline (F4.2). Max "
                            "20, 1-64 characters, case-insensitive duplicates "
                            "are merged; returned sorted."
                        ),
                    },
                    "waived_findings": {
                        "type": "array",
                        "description": (
                            "Per-finding waivers (GH-821): accept individual "
                            "blocking findings instead of the whole verdict. "
                            "Each entry is waived with its own mandatory reason, "
                            "requires the 'admin' or 'approver' role, and is "
                            "persisted so later baseline builds do not have to "
                            "re-state it. Findings that remain unwaived still "
                            "block the baseline."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "rule_id": {
                                    "type": "string",
                                    "description": "SE-Auditor rule being waived, e.g. 'TRACE-P1'.",
                                },
                                "artifact_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Artifacts the finding concerns, as "
                                        "returned by the SE-Auditor report "
                                        "(empty for graph-level findings)."
                                    ),
                                },
                                "reason": {
                                    "type": "string",
                                    "description": (
                                        "Mandatory justification for accepting "
                                        "this single deviation."
                                    ),
                                },
                            },
                            "required": ["rule_id", "reason"],
                        },
                    },
                },
                "required": ["workspace_id", "scope", "name"],
            },
        },
        {
            "name": "baseline.list",
            "description": "List Baseline summaries for a workspace, optionally filtered by scope.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "scope": {
                        "type": "string",
                        "description": "Optional scope filter: 'document' | 'project' | 'global'.",
                    },
                    "tag": {
                        "type": "string",
                        "description": (
                            "Optional case-insensitive tag filter (F4.2). Only "
                            "matches baselines of this workspace that carry the "
                            "label in any spelling."
                        ),
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "baseline.get",
            "description": "Fetch full Baseline detail, including its delta-index entries.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the baseline."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "baseline.compare",
            "description": "Compute the structural diff between two baselines (added/removed/changed items).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "baseline_a_id": {"type": "string", "description": "Reference (older) baseline UUID."},
                    "baseline_b_id": {"type": "string", "description": "Target (newer) baseline UUID."},
                },
                "required": ["baseline_a_id", "baseline_b_id"],
            },
        },
        {
            "name": "baseline.set_tags",
            "description": (
                "Replace the tag set of one baseline (write, audited). Tags are "
                "metadata and never modify the immutable snapshot. Omit 'tags' "
                "to clear the set."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the baseline."},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 64},
                        "description": (
                            "Complete replacement set (max 20 labels, 1-64 "
                            "characters, case-insensitive duplicates merged). "
                            "Returned sorted case-insensitively."
                        ),
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "baseline.rollback_preview",
            "description": (
                "Compute what an ADDITIVE rollback to a baseline would change "
                "(read-only, Plan F F4.4). Restores content through new "
                "versions; never writes the immutable baseline tables. Open to "
                "every workspace member, agents included."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the baseline."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "baseline.rollback_request",
            "description": (
                "Open the CCB change request a rollback has to pass through "
                "(write, audited, Plan F F4.4). The plan is bound to the "
                "request's affected-item set; the CR starts in 'draft' and is "
                "executable only after approval."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the baseline."},
                    "change_reason": {
                        "type": "string",
                        "description": (
                            "Mandatory justification for the rollback; recorded "
                            "on the change request."
                        ),
                        "maxLength": 2000,
                    },
                    "title": {
                        "type": "string",
                        "description": (
                            "Optional change-request title; defaults to a "
                            "generated 'Rollback to baseline ...'."
                        ),
                        "maxLength": 255,
                    },
                },
                "required": ["id", "change_reason"],
            },
        },
        {
            "name": "baseline.rollback_apply",
            "description": (
                "Execute an approved rollback in one transaction (write, "
                "audited, Plan F F4.4). Humans only — an agent principal is "
                "refused with PERMISSION_DENIED. The plan is re-derived and "
                "must match the change request's affected set exactly."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the baseline."},
                    "change_request_id": {
                        "type": "string",
                        "description": (
                            "UUID of the approved change request opened via "
                            "baseline.rollback_request."
                        ),
                    },
                },
                "required": ["id", "change_request_id"],
            },
        },
    ]

    def __init__(self, facade: BaselineFacade | None = None) -> None:
        self._facade = facade or BaselineFacade()

    # ------------------------------------------------------------------
    # baseline.create
    # ------------------------------------------------------------------

    def _handle_create(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.create — create an immutable baseline snapshot (write, audited)."""
        workspace_id = require_uuid(params, "workspace_id")
        scope = require_param(params, "scope")
        name = require_param(params, "name")
        description = params.get("description")
        document_id = optional_uuid(params, "document_id")
        override_reason = params.get("override_reason")
        # GH-821: forwarded verbatim; ``BaselineFacade._coerce_waiver_requests``
        # is the single normalisation point for both surfaces, so a malformed
        # entry surfaces as a clean ValidationError below instead of an
        # AttributeError/TypeError leaking out of the tool as a 500.
        waived_findings = params.get("waived_findings") or None
        # F4.2: forwarded verbatim; the facade is the single validation point.
        tags = params.get("tags") or None

        try:
            # Codeberg #313: suppress create_baseline's single internal
            # _audit() call (operation="baseline.create", same entity) —
            # write_mcp_audit below is the sole entry.
            with mcp_audit_handoff():
                baseline_id = self._facade.create_baseline(
                    scope=str(scope),
                    workspace_id=workspace_id,
                    name=str(name),
                    ctx=auth_context,
                    description=description,
                    document_id=document_id,
                    override_reason=(
                        str(override_reason) if override_reason else None
                    ),
                    waived_findings=waived_findings,
                    tags=tags,
                )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="Baseline",
            entity_id=baseline_id,
            tool_name="baseline.create",
            api_key=api_key,
        )
        return ToolResult.ok({"baseline_id": str(baseline_id)})

    # ------------------------------------------------------------------
    # baseline.list
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.list — list baseline summaries for a workspace."""
        workspace_id = require_uuid(params, "workspace_id")
        scope = params.get("scope")
        tag = params.get("tag") or None

        try:
            summaries = self._facade.list_baselines(
                workspace_id=workspace_id, ctx=auth_context, scope=scope, tag=tag
            )
        except ValidationError as exc:
            # F4.2 review B2: the ``tag`` filter is validated centrally in the
            # facade (shared with REST). Without this branch the exception
            # escaped to the dispatcher's catch-all and became ``-32603``
            # (internal error) for what is a malformed parameter.
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        return ToolResult.ok(
            {
                "baselines": [_baseline_summary_to_dict(s) for s in summaries],
                "count": len(summaries),
            }
        )

    # ------------------------------------------------------------------
    # baseline.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.get — fetch full baseline detail including delta entries."""
        baseline_id = require_uuid(params, "id")

        try:
            detail = self._facade.get_baseline(baseline_id=baseline_id, ctx=auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        return ToolResult.ok({"baseline": _baseline_detail_to_dict(detail)})

    # ------------------------------------------------------------------
    # baseline.compare
    # ------------------------------------------------------------------

    def _handle_compare(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.compare — structural diff between two baselines."""
        baseline_a_id = require_uuid(params, "baseline_a_id")
        baseline_b_id = require_uuid(params, "baseline_b_id")

        try:
            diff = self._facade.diff_baselines(
                baseline_a_id=baseline_a_id,
                baseline_b_id=baseline_b_id,
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        return ToolResult.ok({"diff": diff.to_dict()})

    # ------------------------------------------------------------------
    # baseline.set_tags
    # ------------------------------------------------------------------

    def _handle_set_tags(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.set_tags — replace the tag set of one baseline (F4.2)."""
        baseline_id = require_uuid(params, "id")
        tags = params.get("tags")
        if tags is None:
            tags = []

        try:
            # Keep exactly one audit entry for this MCP write: suppress the
            # facade's own ``operation="update"`` row and record the enriched
            # MCP audit below.
            with mcp_audit_handoff():
                labels = self._facade.set_tags(
                    baseline_id=baseline_id, labels=tags, ctx=auth_context
                )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="Baseline",
            entity_id=baseline_id,
            tool_name="baseline.set_tags",
            api_key=api_key,
        )
        return ToolResult.ok({"id": str(baseline_id), "tags": labels})

    # ------------------------------------------------------------------
    # Plan F F4.4 — additive rollback (ADR-025)
    # ------------------------------------------------------------------

    def _handle_rollback_preview(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.rollback_preview — the rollback plan, read-only (R4/R7)."""
        baseline_id = require_uuid(params, "id")

        try:
            plan = BaselineRollbackService().preview(baseline_id, auth_context)
        except Exception as exc:  # noqa: BLE001 — every domain error is mapped
            return _rollback_error_result(exc)

        return ToolResult.ok(_rollback_plan_to_dict(plan))

    def _handle_rollback_request(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.rollback_request — open the CCB change request (R2/R9)."""
        baseline_id = require_uuid(params, "id")
        change_reason = require_param(params, "change_reason")
        title = params.get("title") or None

        try:
            with mcp_audit_handoff():
                cr = BaselineRollbackService().request(
                    baseline_id,
                    auth_context,
                    title=title,
                    change_reason=str(change_reason),
                )
                affected = ChangeRequestService().list_affected_items(
                    cr.id, auth_context
                )
        except Exception as exc:  # noqa: BLE001 — every domain error is mapped
            return _rollback_error_result(exc, params)

        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="ChangeRequest",
            entity_id=cr.id,
            tool_name="baseline.rollback_request",
            api_key=api_key,
        )
        return ToolResult.ok(
            {
                "baseline_id": str(baseline_id),
                "change_request_id": str(cr.id),
                "status": ChangeRequestDTO.from_orm(cr).status,
                "affected_items": len(affected),
            }
        )

    def _handle_rollback_apply(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """baseline.rollback_apply — execute an approved rollback (R1-R9)."""
        baseline_id = require_uuid(params, "id")
        change_request_id = require_uuid(params, "change_request_id")

        try:
            result = BaselineRollbackService().apply(
                baseline_id, change_request_id, auth_context
            )
        except Exception as exc:  # noqa: BLE001 — every domain error is mapped
            # SEC-RB-08: the service already refused an agent principal before
            # any database work; this branch only translates that refusal (and
            # every other rollback failure) into the MCP wire error.
            return _rollback_error_result(exc, params)

        # Deliberately NO ``write_mcp_audit`` here, unlike the other write
        # tools in this group: ADR-025 R6 requires exactly ONE rollback-level
        # audit entry, and the service already writes it inside the same
        # transaction — carrying the change-request id and the restored /
        # reactivated / recreated counts. A second, generic MCP row would
        # either duplicate that act or (with ``mcp_audit_handoff``) replace the
        # informative entry with a poorer one. The transport call is still
        # attributable: the R6 row records the acting user and the CR.
        return ToolResult.ok(
            {
                **_rollback_result_to_dict(result),
                "baseline_id": str(baseline_id),
                "change_request_id": str(change_request_id),
            }
        )


def _rollback_plan_to_dict(plan: Any) -> dict[str, Any]:
    """Serialise a ``RollbackPlan`` for MCP responses (ADR-025 R4/R7)."""
    return {
        "baseline_id": str(plan.baseline_id),
        "summary": plan.summary,
        "items": [
            {
                "item_id": item.item_id,
                "artifact_type": item.artifact_type,
                "action": item.action,
                "field_changes": item.field_changes,
                "unrestorable_fields": list(item.unrestorable_fields),
                "current_version": item.current_version,
            }
            for item in plan.items
        ],
        "links_to_recreate": list(plan.links_to_recreate),
        "skipped_links": list(plan.skipped_links),
    }


def _rollback_result_to_dict(result: Any) -> dict[str, Any]:
    """Serialise a ``RollbackResult`` for MCP responses."""
    return {
        "restored": result.restored,
        "reactivated": result.reactivated,
        "links_recreated": result.links_recreated,
        "change_request_status": result.change_request_status,
        "skipped": list(result.skipped),
    }


#: Domain refusal -> the JSON-RPC code this group answers with. The MCP
#: taxonomy has no per-domain codes and adding five for one feature would be a
#: wire-contract change; the SQL-state-free domain code travels in
#: ``details["code"]`` instead, mirroring the REST envelope's own code.
_PERMISSION_LIKE = (RollbackForbiddenError, PermissionDeniedError)


def _rollback_error_result(
    exc: Exception, params: dict[str, Any] | None = None
) -> ToolResult:
    """Translate any rollback failure into a ``ToolResult`` error.

    Order matters: ``RollbackForbiddenError`` is also a ``PermissionDeniedError``
    and the two 400-shaped rollback errors are also ``ValidationError``s, so the
    most specific branch is tested first. Anything else that is a plain
    ``RollbackError`` is a state conflict (plan stale, not approved, already
    applied, concurrent CCB decision).
    """
    if isinstance(exc, _PERMISSION_LIKE):
        code = "PERMISSION_DENIED"
    elif isinstance(exc, NotFoundError):
        code = "NOT_FOUND"
    elif isinstance(exc, (RollbackEmptyError, RollbackTooLargeError, ValidationError)):
        code = "VALIDATION_ERROR"
    elif isinstance(exc, RollbackError):
        code = "CONFLICT"
    else:
        # Not a rollback failure at all — do not disguise a defect as a domain
        # answer. The dispatcher's catch-all turns this into -32603.
        raise exc

    details: dict[str, Any] = {
        "code": getattr(exc, "code", None) or code,
    }
    service_details = getattr(exc, "details", None)
    if service_details:
        details["details"] = service_details
    if params is not None:
        details["baseline_id"] = str(params.get("id", ""))
    return ToolResult.error(code, str(exc), details)


__all__ = ["BaselineToolGroup"]
