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
    """Baseline tool group (5 tools) — wraps ``application.baseline_facade.BaselineFacade``."""

    _TOOL_MAP = {
        "baseline.create": "_handle_create",
        "baseline.list": "_handle_list",
        "baseline.get": "_handle_get",
        "baseline.compare": "_handle_compare",
        "baseline.set_tags": "_handle_set_tags",
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


__all__ = ["BaselineToolGroup"]
