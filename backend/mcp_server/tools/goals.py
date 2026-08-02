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
from workflow.definition_store import PRESET_SCHEMAS

# Issue #270 finding 5: ``target_state`` used to be an unconstrained string, so
# clients guessed English state names ("approved") that the German
# ``goal_default`` state machine rejects. The enum is derived from the preset
# schema (single source of truth, workflow/definition_store.py) rather than
# duplicated here. It is a client-side hint only — the server still validates
# against the workspace's *actual* definition, which an Extended-preset
# workspace may have customised beyond these defaults.
_GOAL_STATES: list[str] = list(PRESET_SCHEMAS["goal_default"]["states"])
_MAIN_GOAL_STATES: list[str] = list(PRESET_SCHEMAS["main_goal_default"]["states"])


def _main_goal_payload(main_goal: Any) -> Dict[str, Any]:
    """Serialize a MainGoal ORM row for the ``main_goal`` response envelope."""
    return {
        "id": str(main_goal.id),
        "workspace_id": str(main_goal.workspace_id),
        "sequence_number": main_goal.sequence_number,
        "content": main_goal.content,
        "source": main_goal.source,
        "status": main_goal.status,
    }


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
                    "target_state": {
                        "type": "string",
                        "enum": _GOAL_STATES,
                        "description": (
                            "Target workflow state. These are the "
                            "``goal_default`` preset's states; a workspace "
                            "with a customised Goal workflow may accept "
                            "further states."
                        ),
                    },
                    "change_reason": {
                        "type": "string",
                        "description": (
                            "Reason for the change. Required by the "
                            "Entwurf -> Freigegeben transition."
                        ),
                    },
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
    """MCP tool group for the ``main_goal.*`` namespace (single version chain).

    Response contract (issue #270 findings 2 + 3): every ``main_goal.*`` tool
    except ``list_versions`` answers with a ``{"main_goal": {...} | null}``
    envelope. Two reasons:

    * A MainGoal carries a ``content`` field. Returned at the *top* level it
      collided with the ``content`` key of the MCP result envelope
      (``{"content": [{"type": "text", ...}]}``) that ``ProtocolHandler``
      builds for ``tools/call``, so a client reading ``result["content"]``
      after a direct-method dispatch saw the bare MainGoal text — the
      "response is only an echo of the content string" symptom, and (with the
      literal ``"[]"`` content that #229 used to persist) the "read returns an
      empty array" symptom.
    * ``read`` used to answer with a flat object on a hit but with
      ``{"main_goal": None}`` on a miss, so no single client-side accessor
      worked for both cases.
    """

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
            "description": (
                "Read the currently valid (Freigegeben) MainGoal for a "
                "workspace. Returns {\"main_goal\": {...}}, or "
                "{\"main_goal\": null, \"reason\": ...} when no version has "
                "been approved yet."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}},
                "required": ["workspace_id"],
            },
        },
        {
            "name": "main_goal.generate",
            "description": (
                "Generate a new MainGoal draft via LLM aggregation of the "
                "workspace's approved Goals. Returns the persisted draft as "
                "{\"main_goal\": {id, sequence_number, content, source, "
                "status, ...}}."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}},
                "required": ["workspace_id"],
            },
        },
        {
            "name": "main_goal.create_manual",
            "description": (
                "Manually create a new MainGoal draft. Returns the persisted "
                "draft as {\"main_goal\": {id, sequence_number, content, "
                "source, status, ...}}."
            ),
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
            "description": (
                "Approve a MainGoal draft, making it the currently valid "
                "version. This is the only MainGoal transition exposed over "
                "MCP: it moves the row from '"
                + _MAIN_GOAL_STATES[0]
                + "' to '"
                + _MAIN_GOAL_STATES[1]
                + "'. Returns {\"main_goal\": {...}}."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "main_goal_id": {"type": "string"},
                    "change_reason": {
                        "type": "string",
                        "description": (
                            "Reason for the approval. Required by the "
                            "Entwurf -> Freigegeben transition; a default is "
                            "supplied when omitted."
                        ),
                    },
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
        """Return the currently valid MainGoal in a stable envelope.

        "Currently valid" is the newest ``Freigegeben`` row (design spec 2.3);
        a workspace whose only versions are drafts legitimately has none. That
        used to be indistinguishable from "workspace has no MainGoal at all",
        so the miss branch now reports how many versions exist.
        """
        workspace_id = require_uuid(params, "workspace_id")
        service = MainGoalService()
        main_goal = service.get_current(workspace_id, auth_context)
        if main_goal is None:
            version_count = len(service.list_versions(workspace_id, auth_context))
            return ToolResult.ok(
                {
                    "main_goal": None,
                    "reason": (
                        f"No MainGoal version in state 'Freigegeben'. "
                        f"{version_count} version(s) exist; approve one via "
                        f"main_goal.approve to make it the valid MainGoal."
                    ),
                }
            )
        return ToolResult.ok({"main_goal": _main_goal_payload(main_goal)})

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
        return ToolResult.ok({"main_goal": result})

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
        return ToolResult.ok({"main_goal": result})

    def _handle_approve(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Approve a draft and answer with the *full* approved MainGoal.

        ``MainGoalService.approve`` only reports ``{id, sequence_number,
        status}``. A client that renders the result straight away would show an
        empty MainGoal, so the row is re-read and serialized in full — the same
        lesson the REST ``MainGoalViewSet.approve`` action learned.
        """
        main_goal_id = require_uuid(params, "main_goal_id")
        change_reason = params.get("change_reason")
        service = MainGoalService()
        try:
            service.approve(main_goal_id, auth_context, change_reason=change_reason)
            result = _main_goal_payload(service.get(main_goal_id, auth_context))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        return ToolResult.ok({"main_goal": result})

    def _handle_list_versions(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        versions = MainGoalService().list_versions(workspace_id, auth_context)
        return ToolResult.ok({"versions": versions})


__all__ = ["GoalToolGroup", "MainGoalToolGroup"]
