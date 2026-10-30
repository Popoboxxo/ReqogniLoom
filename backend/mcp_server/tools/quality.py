"""MCP tool group ``quality`` — advisory quality assessment (B5-T3, #378).

Thin adapter over :class:`application.quality_service.QualityService` (ADR-01:
no domain logic here), the MCP twin of the REST ``.../quality/assess/`` and
``.../quality/<entity_type>/<entity_id>/`` routes — same service, same wire
payload, same workspace binding.

* ``quality.assess`` — write (editor+, AUTHOR tier), one paid LLM completion.
  An entity of another workspace of the same tenant is ``NOT_FOUND`` with no
  provider call and no row; a fenced key on a foreign workspace is denied
  (``-32001``) before the handler runs.
* ``quality.query`` — read (exempt via the ``.query`` suffix): the newest-first
  history of one entity plus its latest verdict.

Error mapping mirrors REST, including the cause-specific LLM codes carried by
``LlmResponseError.error_code`` (``LLM_OUTPUT_INVALID`` / ``LLM_TIMEOUT`` /
``LLM_UNAVAILABLE`` / ``LLM_TOKEN_LIMIT_EXCEEDED``, #1416).
"""
from __future__ import annotations

import logging
from typing import Any

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from auth_tenancy.context import AuthContext
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    ToolResult,
    mcp_audit_handoff,
    reject_unknown_params,
    require_param,
    require_uuid,
    write_mcp_audit,
)

logger = logging.getLogger(__name__)

_WORKSPACE_PARAM = {
    "type": "string",
    "description": "UUID of the workspace the assessed artifact must belong to.",
}
_TYPE_PARAM = {
    "type": "string",
    "enum": ["Requirement", "Adr", "TestCase", "Risk"],
    "description": "Artifact type of the entity being assessed/reviewed.",
}
_ENTITY_PARAM = {
    "type": "string",
    "description": "UUID of the entity itself (not its backing artifact id).",
}


class QualityToolGroup(BaseToolGroup):
    """``quality.*`` tool group (see the module docstring)."""

    _TOOL_MAP = {
        "quality.assess": "_handle_assess",
        "quality.query": "_handle_query",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "quality.assess",
            "description": (
                "Run the advisory quality assessment for ONE artifact "
                "(Requirement, Adr, TestCase or Risk) through the workspace's "
                "quality_* prompt slot and persist the verdict. Returns the "
                "new assessment, or the last verdict with cached=true when the "
                "content is unchanged (pass force=true to re-run). Costs one "
                "LLM call unless cached; the artifact must belong to the given "
                "workspace, otherwise NOT_FOUND is returned and nothing runs."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": _WORKSPACE_PARAM,
                    "entity_type": _TYPE_PARAM,
                    "entity_id": _ENTITY_PARAM,
                    "force": {
                        "type": "boolean",
                        "description": (
                            "Re-run even when the content hash is unchanged."
                        ),
                    },
                },
                "required": ["workspace_id", "entity_type", "entity_id"],
            },
        },
        {
            "name": "quality.query",
            "description": (
                "Read the assessment history of ONE artifact in a workspace: "
                "newest first, with the latest verdict under 'latest' (null "
                "when it was never assessed). Read-only."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": _WORKSPACE_PARAM,
                    "entity_type": _TYPE_PARAM,
                    "entity_id": _ENTITY_PARAM,
                    "limit": {
                        "type": "integer",
                        "description": "Page size, 1..100 (default 20).",
                    },
                },
                "required": ["workspace_id", "entity_type", "entity_id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # quality.assess
    # ------------------------------------------------------------------

    def _handle_assess(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from application.ai_derivation_service import LlmResponseError
        from application.quality_service import QualityService, assessment_payload

        reject_unknown_params(
            params,
            ["workspace_id", "entity_type", "entity_id", "force"],
            "quality.assess",
        )
        workspace_id = require_uuid(params, "workspace_id")
        entity_id = require_uuid(params, "entity_id")
        entity_type = str(require_param(params, "entity_type"))
        force = bool(params.get("force", False))

        try:
            with mcp_audit_handoff():
                assessment, cached = QualityService().assess(
                    auth_context,
                    workspace_id,
                    entity_type,
                    entity_id,
                    force=force,
                    trigger="mcp",
                )
        except LlmResponseError as exc:
            return ToolResult.error(exc.error_code, str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            auth_context,
            "create",
            "QualityAssessment",
            assessment.id,
            "quality.assess",
            api_key,
            details={"entity_type": entity_type, "cached": cached},
        )
        return ToolResult.ok(assessment_payload(assessment, cached=cached))

    # ------------------------------------------------------------------
    # quality.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        from application.quality_service import QualityService, assessment_payload

        reject_unknown_params(
            params,
            ["workspace_id", "entity_type", "entity_id", "limit"],
            "quality.query",
        )
        workspace_id = require_uuid(params, "workspace_id")
        entity_id = require_uuid(params, "entity_id")
        entity_type = str(require_param(params, "entity_type"))
        raw_limit = params.get("limit", 20)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            raise ParameterError(f"Parameter 'limit' is not an integer: {raw_limit!r}")

        try:
            rows = QualityService().history(
                auth_context, workspace_id, entity_type, entity_id, limit=limit
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        return ToolResult.ok(
            {
                "assessments": [assessment_payload(row) for row in rows],
                "count": len(rows),
                "latest": assessment_payload(rows[0]) if rows else None,
            }
        )
