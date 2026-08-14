"""
MCP Tool Group for cross-host structured Interviews (Interview-Management-Engine spec §4).

Wraps InterviewService (Task 3) for interview.start / interview.get_state /
interview.answer / interview.list / interview.get. Grounding
(interview.ground_*) and interview.formalize land in later tasks (6-7) — do
not add them here.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from application.base import NotFoundError, ValidationError
from application.interview_service import InterviewService
from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    require_param,
    require_uuid,
    write_mcp_audit,
)


def _session_to_dict(session: Any) -> dict:
    return {
        "id": str(session.id),
        "workspace_id": str(session.workspace_id),
        "artifact_type": session.artifact_type,
        "status": session.status,
    }


class InterviewToolGroup(BaseToolGroup):
    """interview.* tool group (start/get_state/answer/list/get)."""

    _TOOL_MAP = {
        "interview.start": "_handle_start",
        "interview.get_state": "_handle_get_state",
        "interview.answer": "_handle_answer",
        "interview.list": "_handle_list",
        "interview.get": "_handle_get",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "interview.start",
            "description": (
                "Start a new structured interview for one artifact type in a "
                "workspace (write). Returns the new session_id plus its "
                "current interview state (phase, collected_fields, "
                "missing_fields) so the caller can immediately render the "
                "first question."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_type": {
                        "type": "string",
                        "description": "Target artifact type, e.g. 'Requirement', 'Risk', 'TestCase'.",
                    },
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                },
                "required": ["artifact_type", "workspace_id"],
            },
        },
        {
            "name": "interview.get_state",
            "description": (
                "Fetch the current progress of an interview session: phase, "
                "collected_fields, missing_fields and grounding_snapshot. "
                "Any host can call this to resume a session started elsewhere."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "UUID of the interview session."},
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "interview.answer",
            "description": "Record an answer for one field of the current phase (write).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "UUID of the interview session."},
                    "field": {"type": "string", "description": "Field name being answered."},
                    "value": {"description": "Answer value (type depends on the field's declared type)."},
                },
                "required": ["session_id", "field", "value"],
            },
        },
        {
            "name": "interview.list",
            "description": "List interview sessions in a workspace, optionally filtered by status.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "UUID of the workspace."},
                    "status": {
                        "type": "string",
                        "description": "Optional status filter: in_progress, completed, or abandoned.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "interview.get",
            "description": "Fetch one interview session's summary (id, workspace, artifact_type, status) by id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "UUID of the interview session."},
                },
                "required": ["session_id"],
            },
        },
    ]

    def __init__(self, service: Optional[InterviewService] = None) -> None:
        self._service = service or InterviewService()

    def _handle_start(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        artifact_type = require_param(params, "artifact_type")
        workspace_id = require_uuid(params, "workspace_id")

        try:
            session = self._service.start(auth_context, artifact_type, workspace_id)
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        # AuditLog.op is a fixed vocabulary (audit/models.py OP_CHOICES) --
        # "start"/"answer" are not members. A session is a newly created
        # row, so this maps to the "create" operation (interview.answer
        # below maps to "update").
        write_mcp_audit(
            ctx=auth_context,
            operation="create",
            entity_type="InterviewSession",
            entity_id=session.id,
            tool_name="interview.start",
            api_key=api_key,
        )
        state = self._service.get_state(auth_context, session.id)
        return ToolResult.ok({**_session_to_dict(session), **state})

    def _handle_get_state(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            state = self._service.get_state(auth_context, session_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(state)

    def _handle_answer(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        field = require_param(params, "field")
        value = params.get("value")

        try:
            session = self._service.answer(auth_context, session_id, field, value)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="InterviewSession",
            entity_id=session.id,
            tool_name="interview.answer",
            api_key=api_key,
        )
        return ToolResult.ok(self._service.get_state(auth_context, session.id))

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        status = params.get("status")
        sessions = list(self._service.list_sessions(auth_context, workspace_id, status=status))
        return ToolResult.ok({
            "sessions": [_session_to_dict(s) for s in sessions],
            "count": len(sessions),
        })

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            session = self._service.get(auth_context, session_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(_session_to_dict(session))


__all__ = ["InterviewToolGroup"]
