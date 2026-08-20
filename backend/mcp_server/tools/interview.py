"""
MCP Tool Group for cross-host structured Interviews (Interview-Management-Engine spec §4).

Wraps InterviewService (Task 3) for interview.start / interview.get_state /
interview.answer / interview.list / interview.get /
interview.grounding_context (Task 5, structural + Task 6 AI-assisted
ranking) / interview.formalize (Task 7, Requirement only) /
interview.set_target (issue #540, confirms a grounding_context()
candidate as formalize()'s update target, Requirement only).
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
        "interview.grounding_context": "_handle_grounding_context",
        "interview.formalize": "_handle_formalize",
        "interview.set_target": "_handle_set_target",
        "interview.abandon": "_handle_abandon",
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
                    "seed_context": {
                        "type": "object",
                        "description": (
                            "Optional pre-known field values to seed the session's "
                            "collected_fields with, e.g. when the caller already "
                            "knows some answers before the interview starts."
                        ),
                    },
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
        {
            "name": "interview.grounding_context",
            "description": (
                "Structural (non-AI) grounding: find existing artifacts whose title "
                "overlaps the session's collected title, so the interview can flag "
                "possible duplicates before a new artifact is created. Only "
                "Requirement is wired up so far; other artifact types return no "
                "candidates for now. Refreshes and returns the session's "
                "grounding_snapshot."
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
            "name": "interview.formalize",
            "description": (
                "Turn the session's collected answers into a real artifact (write). "
                "Creates a new Requirement, or -- if grounding set a target -- "
                "updates the existing one instead, re-checking at write time that "
                "the target still exists. Marks the session completed and returns "
                "resulting_artifact_ids. Only artifact_type='Requirement' sessions "
                "are supported so far."
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
            "name": "interview.set_target",
            "description": (
                "Confirm a grounding_context() candidate (or any already-known "
                "artifact_id) as this session's formalize() target (write). "
                "Once set, formalize() updates that existing Requirement "
                "instead of creating a new one. Requirement sessions only -- "
                "formalize()'s update branch does not support the other 7 "
                "in-scope artifact types yet. Re-validates that artifact_id "
                "resolves to a real Requirement right now. Returns the "
                "session's refreshed state."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "UUID of the interview session."},
                    "artifact_id": {
                        "type": "string",
                        "description": "UUID of the existing Requirement artifact to target.",
                    },
                },
                "required": ["session_id", "artifact_id"],
            },
        },
        {
            "name": "interview.abandon",
            "description": (
                "User-initiated cancel of an in_progress interview (write). "
                "Before this tool existed, the only path to the 'abandoned' "
                "state was a 30-day inactivity sweep -- a session the caller "
                "actively wants to stop had no way to be marked as such and "
                "kept showing up in in_progress lists indefinitely."
            ),
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
        seed_context = params.get("seed_context")

        try:
            session = self._service.start(
                auth_context, artifact_type, workspace_id, seed_context=seed_context
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
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
        if "value" not in params:
            return ToolResult.error(
                "VALIDATION_ERROR", "Required parameter 'value' is missing."
            )
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

    def _handle_grounding_context(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            result = self._service.grounding_context(auth_context, session_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(result)

    def _handle_formalize(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            result = self._service.formalize(auth_context, session_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="InterviewSession",
            entity_id=session_id,
            tool_name="interview.formalize",
            api_key=api_key,
        )
        return ToolResult.ok(result)

    def _handle_abandon(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            result = self._service.abandon(auth_context, session_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="InterviewSession",
            entity_id=session_id,
            tool_name="interview.abandon",
            api_key=api_key,
        )
        return ToolResult.ok(result)

    def _handle_set_target(
        self, *, params: Dict[str, Any], auth_context, api_key: str
    ) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        artifact_id = require_uuid(params, "artifact_id")
        try:
            result = self._service.set_target(auth_context, session_id, artifact_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="InterviewSession",
            entity_id=session_id,
            tool_name="interview.set_target",
            api_key=api_key,
        )
        return ToolResult.ok(result)


__all__ = ["InterviewToolGroup"]
