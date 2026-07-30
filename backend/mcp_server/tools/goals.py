"""MCP tool groups for Goal and MainGoal.

leaf_id : (Task 7 of feat/ziele-hauptziel-design)
req_id  : REQ-L2-TE-020

Bespoke (not ``GenericCrudToolGroup``) because Goal/MainGoal versioning uses
``create_version``/``generate``/``approve`` instead of plain update — see
``mcp_server/tools/generic.py`` for the shared CRUD pattern this deviates
from. Mirrors that module's not-found-handling (``NotFoundError`` ->
``ToolResult.error("NOT_FOUND", ...)``) and validation-error handling
(``ValidationError`` -> ``ToolResult.error("VALIDATION_ERROR", ...)``)
conventions, plus ``baseline.py``'s ``PermissionDeniedError`` ->
``ToolResult.error("PERMISSION_DENIED", ...)`` convention on all write
handlers.
"""
from __future__ import annotations

from typing import Any, Dict

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.goal_service import GoalService
from application.main_goal_service import MainGoalService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_uuid


class GoalToolGroup(BaseToolGroup):
    """MCP tool group for the ``goal.*`` namespace (lineage-versioned Goals)."""

    _TOOL_MAP = {
        "goal.read": "_handle_read",
        "goal.create": "_handle_create",
        "goal.create_version": "_handle_create_version",
        "goal.list_versions": "_handle_list_versions",
        "goal.transition": "_handle_transition",
    }
    _TOOL_SCHEMAS = [
        {
            "name": "goal.read",
            "description": "Read a single Goal version by id.",
            "inputSchema": {
                "type": "object",
                "properties": {"goal_id": {"type": "string"}},
                "required": ["goal_id"],
            },
        },
        {
            "name": "goal.create",
            "description": "Create a new Goal (starts a new lineage, sequence 1).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["workspace_id", "title"],
            },
        },
        {
            "name": "goal.create_version",
            "description": "Create a new version within an existing Goal lineage.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "lineage_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["workspace_id", "lineage_id", "title"],
            },
        },
        {
            "name": "goal.list_versions",
            "description": "List all versions in a Goal lineage, oldest first.",
            "inputSchema": {
                "type": "object",
                "properties": {"lineage_id": {"type": "string"}},
                "required": ["lineage_id"],
            },
        },
        {
            "name": "goal.transition",
            "description": (
                "Transition a Goal version's workflow state (e.g. Entwurf -> "
                "Freigegeben). Only Freigegeben versions feed MainGoal "
                "aggregation."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string"},
                    "target_state": {"type": "string"},
                    "change_reason": {"type": "string"},
                    "credential": {"type": "string"},
                },
                "required": ["goal_id", "target_state"],
            },
        },
    ]

    def _handle_read(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        goal_id = require_uuid(params, "goal_id")
        try:
            goal = GoalService().get(goal_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(
            {
                "id": str(goal.id),
                "lineage_id": str(goal.lineage_id),
                "sequence_number": goal.sequence_number,
                "title": goal.title,
                "description": goal.description,
                "status": goal.status,
            }
        )

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        try:
            result = GoalService().create_version(
                workspace_id=workspace_id,
                title=params.get("title", ""),
                description=params.get("description", ""),
                lineage_id=None,
                ctx=auth_context,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(result)

    def _handle_create_version(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        lineage_id = require_uuid(params, "lineage_id")
        try:
            result = GoalService().create_version(
                workspace_id=workspace_id,
                title=params.get("title", ""),
                description=params.get("description", ""),
                lineage_id=lineage_id,
                ctx=auth_context,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(result)

    def _handle_list_versions(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        lineage_id = require_uuid(params, "lineage_id")
        versions = GoalService().list_versions(lineage_id, auth_context)
        return ToolResult.ok({"versions": versions})

    def _handle_transition(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Transition a Goal version through the generic WorkflowEngine.

        Delegates to ``GoalService.transition_status``, i.e. the exact same
        ``WorkflowFacade`` path ``POST /api/v1/goals/{id}/transitions/`` uses,
        so role / change_reason / signature gates behave identically across
        REST and MCP.
        """
        goal_id = require_uuid(params, "goal_id")
        target_state = params.get("target_state") or params.get("to_status")
        if not target_state:
            return ToolResult.error(
                "VALIDATION_ERROR", "Required parameter 'target_state' is missing."
            )
        try:
            goal = GoalService().transition_status(
                goal_id,
                str(target_state),
                auth_context,
                change_reason=params.get("change_reason"),
                credential=params.get("credential"),
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        return ToolResult.ok(
            {
                "id": str(goal.id),
                "lineage_id": str(goal.lineage_id),
                "sequence_number": goal.sequence_number,
                "status": goal.status,
            }
        )


class MainGoalToolGroup(BaseToolGroup):
    """MCP tool group for the ``main_goal.*`` namespace (single version chain)."""

    _TOOL_MAP = {
        "main_goal.read": "_handle_read",
        "main_goal.generate": "_handle_generate",
        "main_goal.create_manual": "_handle_create_manual",
        "main_goal.approve": "_handle_approve",
        "main_goal.list_versions": "_handle_list_versions",
    }
    _TOOL_SCHEMAS = [
        {
            "name": "main_goal.read",
            "description": "Read the currently valid (Freigegeben) MainGoal for a workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}},
                "required": ["workspace_id"],
            },
        },
        {
            "name": "main_goal.generate",
            "description": "Generate a new MainGoal draft via LLM aggregation of current Goals.",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}},
                "required": ["workspace_id"],
            },
        },
        {
            "name": "main_goal.create_manual",
            "description": "Manually create a new MainGoal draft.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["workspace_id", "content"],
            },
        },
        {
            "name": "main_goal.approve",
            "description": "Approve a MainGoal draft, making it the currently valid version.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "main_goal_id": {"type": "string"},
                    "change_reason": {"type": "string"},
                },
                "required": ["main_goal_id"],
            },
        },
        {
            "name": "main_goal.list_versions",
            "description": "List all MainGoal versions for a workspace, oldest first.",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}},
                "required": ["workspace_id"],
            },
        },
    ]

    def _handle_read(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        main_goal = MainGoalService().get_current(workspace_id, auth_context)
        if main_goal is None:
            return ToolResult.ok({"main_goal": None})
        return ToolResult.ok(
            {
                "id": str(main_goal.id),
                "sequence_number": main_goal.sequence_number,
                "content": main_goal.content,
                "source": main_goal.source,
                "status": main_goal.status,
            }
        )

    def _handle_generate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        try:
            result = MainGoalService().generate_ai(
                workspace_id=workspace_id, ctx=auth_context
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(result)

    def _handle_create_manual(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        try:
            result = MainGoalService().create_manual(
                workspace_id=workspace_id,
                content=params.get("content", ""),
                ctx=auth_context,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok(result)

    def _handle_approve(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        main_goal_id = require_uuid(params, "main_goal_id")
        change_reason = params.get("change_reason")
        try:
            result = MainGoalService().approve(
                main_goal_id, auth_context, change_reason=change_reason
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        return ToolResult.ok(result)

    def _handle_list_versions(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        versions = MainGoalService().list_versions(workspace_id, auth_context)
        return ToolResult.ok({"versions": versions})


__all__ = ["GoalToolGroup", "MainGoalToolGroup"]
