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

from typing import Any, Dict, Optional
from uuid import UUID

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


def _goal_payload(goal: Any) -> Dict[str, Any]:
    """Serialize a Goal ORM row for the ``goal.read``/``goal.query`` responses."""
    return {
        "id": str(goal.id),
        "lineage_id": str(goal.lineage_id),
        "sequence_number": goal.sequence_number,
        "title": goal.title,
        "description": goal.description,
        "status": goal.status,
    }


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
        "goal.query": "_handle_query",
        "goal.create": "_handle_create",
        "goal.create_version": "_handle_create_version",
        "goal.update": "_handle_update",
        "goal.list_versions": "_handle_list_versions",
        "goal.transition": "_handle_transition",
        "goal.delete": "_handle_delete",
        "goal.outdate": "_handle_outdate",
        "goal.reactivate": "_handle_reactivate",
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
            "name": "goal.query",
            "description": (
                "List the current version of every Goal lineage in a "
                "workspace (read-only). By default omits lineages whose "
                "current version is 'Archiviert'; set include_archived to "
                "list those too."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "include_archived": {
                        "type": "boolean",
                        "description": (
                            "If true, include lineages whose current version "
                            "is 'Archiviert'. Defaults to false."
                        ),
                    },
                },
                "required": ["workspace_id"],
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
            "name": "goal.update",
            "description": (
                "Update a Goal (write). Goals are immutable, lineage-versioned "
                "rows, so this does NOT edit the addressed row: it appends a "
                "new version to the same lineage carrying the given fields, "
                "starting again at 'Entwurf'. Omitted fields are inherited "
                "from the addressed version (PATCH semantics). Identical in "
                "effect to goal.create_version, but addressed by goal_id "
                "instead of lineage_id. 'status' cannot be changed here — use "
                "goal.transition."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal_id": {
                        "type": "string",
                        "description": (
                            "UUID of the Goal version to base the new version "
                            "on (not the lineage_id)."
                        ),
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["goal_id"],
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
        {
            "name": "goal.delete",
            "description": (
                "SOFT-ARCHIVE a Goal version (write). This is NOT a hard "
                "delete: Goals are immutable, lineage-versioned rows, so the "
                "row is never removed — the version is moved to the "
                "'Archiviert' workflow state through the WorkflowEngine (the "
                "same gated path as goal.transition). The row stays readable "
                "via goal.read and goal.list_versions, and goal.query still "
                "returns it when include_archived=true. "
                "REACHABLE FROM: any state the workspace's Goal workflow "
                "defines a transition to 'Archiviert' from — with the stock "
                "'goal_default' preset that is 'Entwurf' and 'Freigegeben' "
                "(both approver/admin only). A workspace whose Goal workflow "
                "was customised, or that was provisioned before the "
                "'Entwurf -> Archiviert' edge existed, may only allow it from "
                "'Freigegeben'. "
                "ON AN INVALID STATE: returns VALIDATION_ERROR (JSON-RPC "
                "error, HTTP 400) naming the current state; call "
                "goal.transition with an unreachable target to get the list "
                "of states that ARE reachable in the error details. A caller "
                "lacking the approver/admin role gets PERMISSION_DENIED. "
                "REVERSIBLE via goal.reactivate (or goal.transition back to "
                "'Entwurf'). Alias: goal.outdate."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string"},
                    "change_reason": {
                        "type": "string",
                        "description": "Optional audit reason for archiving.",
                    },
                },
                "required": ["goal_id"],
            },
        },
        {
            "name": "goal.outdate",
            "description": (
                "Soft-delete a Goal version (write). Exact alias of "
                "goal.delete, named after the {entity}.outdate convention the "
                "other artifact namespaces use — for Goals the soft-delete "
                "state is the workflow's 'Archiviert', not the generic "
                "'outdated' escape hatch, because 'outdated' is foreign to "
                "the Goal state machine and would hide the row from the "
                "archive filters. See goal.delete for the reachable source "
                "states and error behaviour."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string"},
                    "id": {
                        "type": "string",
                        "description": "Alias of goal_id ({entity}.outdate convention).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional audit reason for archiving.",
                    },
                    "change_reason": {
                        "type": "string",
                        "description": "Alias of reason.",
                    },
                },
            },
        },
        {
            "name": "goal.reactivate",
            "description": (
                "Restore an archived Goal version (write). Transitions it "
                "back to the Goal workflow's initial state ('Entwurf' by "
                "default) through the same gated path as goal.transition. "
                "Deliberately does NOT restore the pre-archive state: only "
                "'Freigegeben' versions feed MainGoal aggregation, so a "
                "restored Goal returns as a draft and must be approved again. "
                "The stock preset gates 'Archiviert -> Entwurf' on "
                "approver/admin and requires a reason (defaulted to "
                "'reactivated' when none is given)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string"},
                    "id": {
                        "type": "string",
                        "description": "Alias of goal_id ({entity}.reactivate convention).",
                    },
                    "change_reason": {
                        "type": "string",
                        "description": "Audit reason; defaults to 'reactivated'.",
                    },
                },
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
        return ToolResult.ok(_goal_payload(goal))

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        include_archived = bool(params.get("include_archived", False))
        goals = GoalService().list_current(
            workspace_id, auth_context, include_archived=include_archived
        )
        return ToolResult.ok({"goals": [_goal_payload(g) for g in goals]})

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

    @staticmethod
    def _require_goal_id(params: Dict[str, Any]) -> UUID:
        """Read the Goal id from ``goal_id`` or its ``id`` alias.

        ``goal.*`` has always used ``goal_id``; the ``{entity}.outdate`` /
        ``{entity}.reactivate`` tools generated by ``GenericCrudToolGroup`` use
        ``id``. Both are accepted on those two tools so a client that learned
        the generic convention is not tripped up by this bespoke group.
        """
        if params.get("goal_id") is None and params.get("id") is not None:
            return require_uuid(params, "id")
        return require_uuid(params, "goal_id")

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Append a new lineage version carrying the updated fields.

        Goals have no in-place update (immutable rows) — see the tool
        description. ``status`` is rejected outright, mirroring
        ``GenericCrudToolGroup._handle_update`` (#83 Bug 2): the workflow
        engine is the only authority over the status field.
        """
        goal_id = require_uuid(params, "goal_id")
        if "status" in params:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "'status' cannot be changed via goal.update; use "
                "goal.transition for a state-machine-gated status change, or "
                "goal.delete / goal.reactivate for the archive lifecycle.",
            )
        try:
            result = GoalService().update(
                goal_id,
                auth_context,
                title=params.get("title"),
                description=params.get("description"),
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

        Issue #346 finding 3: a rejected target state used to answer with a
        bare 400 that named the offending state but not the acceptable ones,
        leaving the caller to guess. The error now carries the states actually
        reachable from the version's current state, resolved through
        ``GoalService.get_available_transitions`` (the same WorkflowFacade
        lookup that backs ``GET /api/v1/goals/{id}/transitions/``) rather than
        a second, drifting copy of the state machine.
        """
        service = GoalService()
        goal_id = require_uuid(params, "goal_id")
        target_state = params.get("target_state") or params.get("to_status")
        if not target_state:
            return self._invalid_target_state_error(
                service,
                goal_id,
                auth_context,
                "Required parameter 'target_state' is missing.",
            )
        try:
            goal = service.transition_status(
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
            return self._invalid_target_state_error(
                service, goal_id, auth_context, str(exc)
            )
        return ToolResult.ok(
            {
                "id": str(goal.id),
                "lineage_id": str(goal.lineage_id),
                "sequence_number": goal.sequence_number,
                "status": goal.status,
            }
        )

    @staticmethod
    def _invalid_target_state_error(
        service: GoalService,
        goal_id: UUID,
        auth_context: AuthContext,
        message: str,
    ) -> ToolResult:
        """Build the VALIDATION_ERROR for a rejected/missing ``target_state``.

        Appends the states reachable from the Goal's current state to both the
        human-readable message and the structured ``details`` payload
        (``ErrorFormatter`` forwards ``details`` into the JSON-RPC error body),
        so an MCP client can recover without a second round-trip. The lookup is
        best-effort: it must never turn a 400 into a 500, so any failure to
        resolve the transitions falls back to the bare message.
        """
        try:
            current_state, targets = service.get_available_transitions(
                goal_id, auth_context
            )
        except Exception:  # noqa: BLE001 — error path must not raise
            return ToolResult.error("VALIDATION_ERROR", message)

        if targets:
            hint = (
                f" Valid target states from '{current_state}': "
                f"{', '.join(targets)}."
            )
        else:
            hint = (
                f" No target state is reachable from '{current_state}' for "
                "this workspace's Goal workflow."
            )
        return ToolResult.error(
            "VALIDATION_ERROR",
            f"{message}{hint}",
            details={
                "current_state": current_state,
                "valid_target_states": targets,
            },
        )

    def _archive(
        self,
        *,
        goal_id: UUID,
        auth_context: AuthContext,
        change_reason: Optional[str],
    ) -> ToolResult:
        """Shared implementation of ``goal.delete`` / ``goal.outdate``.

        Goals are immutable, lineage-versioned rows (see module docstring) —
        an outright DELETE would silently break lineage history and MainGoal
        aggregation. Consistent with the rest of the system's soft-delete
        convention, this instead transitions the version into the state the
        workspace's Goal workflow flags as ``is_outdated_equivalent``
        ('Archiviert' in the stock preset) through the exact same
        ``GoalService.transition_status`` / ``WorkflowFacade`` path
        ``goal.transition`` uses, so role / change_reason gates apply
        identically (no parallel delete logic).
        """
        service = GoalService()
        try:
            goal = service.archive(
                goal_id, auth_context, change_reason=change_reason
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return self._invalid_target_state_error(
                service, goal_id, auth_context, str(exc)
            )
        return ToolResult.ok(_goal_payload(goal))

    def _handle_delete(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Soft-archive a Goal version (see the tool description for details)."""
        return self._archive(
            goal_id=require_uuid(params, "goal_id"),
            auth_context=auth_context,
            change_reason=params.get("change_reason"),
        )

    def _handle_outdate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """``{entity}.outdate``-named alias of ``goal.delete``.

        Deliberately NOT routed through ``workflow.services.outdate()`` like
        the ``GenericCrudToolGroup`` entities: that escape hatch force-writes
        the state ``"outdated"``, which is foreign to the Goal state machine
        and — because ``Goal`` is registered in
        ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS`` — would be
        mirrored into ``Goal.status``, making the row slip past the
        ``Archiviert`` filters in ``GoalService.list_current`` and reappear in
        ``goal.query``.
        """
        return self._archive(
            goal_id=self._require_goal_id(params),
            auth_context=auth_context,
            change_reason=params.get("reason") or params.get("change_reason"),
        )

    def _handle_reactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Restore an archived Goal version to the workflow's initial state.

        Mirrors ``{entity}.reactivate`` for the other namespaces, but through
        the gated ``GoalService.restore`` rather than the forced
        ``workflow.services.reactivate()`` — see ``_handle_outdate`` for why,
        and ``GoalService.restore`` for why the pre-archive state is
        deliberately not restored.
        """
        goal_id = self._require_goal_id(params)
        service = GoalService()
        try:
            goal = service.restore(
                goal_id, auth_context, change_reason=params.get("change_reason")
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return self._invalid_target_state_error(
                service, goal_id, auth_context, str(exc)
            )
        return ToolResult.ok(_goal_payload(goal))


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
