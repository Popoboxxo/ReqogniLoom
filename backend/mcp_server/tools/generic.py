"""Generic MCP Tool Group for standard CRUD entities."""
import inspect
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict

from application.base import NotFoundError
from auth_tenancy.context import AuthContext
from mcp_server.tools.base import BaseToolGroup, ToolResult, require_uuid


def _resolve_method(service: Any, prefix: str, action: str) -> Callable[..., Any]:
    """Resolve a service's create/update/delete method.

    Services expose either an entity-specific method (AdrService.create_adr,
    IssueService.delete_issue, ...) or a generic one (GlossaryService.create).
    """
    method = getattr(service, f"{action}_{prefix}", None) or getattr(service, action, None)
    if method is None:
        raise AttributeError(
            f"{service.__class__.__name__} exposes neither '{action}_{prefix}' nor '{action}'"
        )
    return method


def _resolve_id_param(method: Callable[..., Any]) -> str:
    """Find the required, non-``ctx`` parameter an update/delete method
    expects for the entity ID (e.g. ``adr_id``, ``term_id``)."""
    for name, param in inspect.signature(method).parameters.items():
        if name in ("self", "ctx") or param.default is not inspect.Parameter.empty:
            continue
        return name
    raise TypeError(f"Could not resolve ID parameter for {method!r}")


def _resolve_list_method(service: Any, prefix: str) -> Callable[..., Any]:
    """Resolve a service's list method for ``{prefix}.query``.

    Services expose the entity list under differing names: plural
    entity-specific (``list_adrs``, ``list_risks``, ``list_issues``),
    workspace-scoped generic (``GlossaryService.list_by_workspace``), or a
    bare generic ``list``. Tried in that order.
    """
    for candidate in (f"list_{prefix}s", f"list_{prefix}", "list_by_workspace", "list"):
        method = getattr(service, candidate, None)
        if method is not None:
            return method
    raise AttributeError(
        f"{service.__class__.__name__} exposes no recognizable list method for prefix '{prefix}'"
    )


class GenericCrudToolGroup(BaseToolGroup):
    """Generic tool group for standard CRUD operations."""

    def __init__(self, prefix: str, service_class: Any, item_type: str | None = None):
        self.prefix = prefix
        self._service = service_class()
        # Workflow item_type string (e.g. "Adr", "GlossaryTerm") passed to
        # workflow.services.outdate()/reactivate() — PascalCase, distinct
        # from the lowercase `prefix` used for tool-name routing. Defaults
        # to prefix.capitalize() (works for adr/risk/issue); entities whose
        # workflow item_type doesn't match their prefix 1:1 (e.g. glossary
        # -> "GlossaryTerm") must pass it explicitly at registration.
        self._item_type = item_type or prefix.capitalize()
        # Resolved once so the handlers below don't need per-entity branching.
        self._read_method = _resolve_method(self._service, prefix, "get")
        self._create_method = _resolve_method(self._service, prefix, "create")
        self._update_method = _resolve_method(self._service, prefix, "update")
        self._delete_method = _resolve_method(self._service, prefix, "delete")
        self._list_method = _resolve_list_method(self._service, prefix)
        self._read_id_param = _resolve_id_param(self._read_method)
        self._update_id_param = _resolve_id_param(self._update_method)
        self._delete_id_param = _resolve_id_param(self._delete_method)
        # Dynamically define the TOOL_MAP for this instance
        self._TOOL_MAP = {
            f"{prefix}.read": "_handle_read",
            f"{prefix}.create": "_handle_create",
            f"{prefix}.update": "_handle_update",
            f"{prefix}.delete": "_handle_delete",
            f"{prefix}.outdate": "_handle_outdate",
            f"{prefix}.reactivate": "_handle_reactivate",
            f"{prefix}.query": "_handle_query",
        }
        # Instance-level JSON schemas (prefix is only known at construction).
        self._TOOL_SCHEMAS = [
            {
                "name": f"{prefix}.read",
                "description": f"Fetch a single {prefix} entity by ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.create",
                "description": f"Create a new {prefix} entity (write). Additional fields are forwarded to the service.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {
                            "type": "string",
                            "description": "UUID of the target workspace.",
                        },
                    },
                    "required": ["workspace_id"],
                    "additionalProperties": True,
                },
            },
            {
                "name": f"{prefix}.update",
                "description": f"Update a {prefix} entity (write). Additional fields are forwarded to the service.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                    },
                    "required": ["id"],
                    "additionalProperties": True,
                },
            },
            {
                "name": f"{prefix}.delete",
                "description": f"Delete a {prefix} entity (write).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.outdate",
                "description": f"Soft-delete a {prefix} entity via the workflow engine's outdate escape hatch (write).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                        "reason": {"type": "string", "description": "Optional audit reason."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.reactivate",
                "description": f"Restore an outdated {prefix} entity to its previous state (write).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.query",
                "description": f"List {prefix} entities in a workspace (read-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {
                            "type": "string",
                            "description": "UUID of the target workspace.",
                        },
                        "include_outdated": {
                            "type": "boolean",
                            "description": "If true, include outdated (soft-deleted) entities. Defaults to false.",
                        },
                    },
                    "required": ["workspace_id"],
                },
            },
        ]
    
    @staticmethod
    def _jsonify(value: Any) -> Any:
        """Coerce a single value into a JSON-serializable form.

        UUID/datetime/date/Decimal are not JSON-serializable by ``json.dumps``
        and would crash the MCP response encoder (e.g. ``Issue.due_date``).
        """
        if isinstance(value, uuid.UUID):
            return str(value)
        # datetime is a subclass of date; check it first for full ISO precision.
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return value

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert object to dict dynamically."""
        if hasattr(obj, "__dict__"):
            data = {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
            # Coerce non-JSON-serializable values (UUID/datetime/date/Decimal).
            return {k: self._jsonify(v) for k, v in data.items()}
        return {"id": str(getattr(obj, "id", ""))}

    def _handle_read(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        try:
            obj = self._read_method(ctx=auth_context, **{self._read_id_param: obj_id})
            return ToolResult.ok({"data": self._to_dict(obj)})
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

    def _handle_create(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        kwargs = {k: v for k, v in params.items() if k != "workspace_id"}
        try:
            obj = self._create_method(ctx=auth_context, workspace_id=workspace_id, **kwargs)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except TypeError as exc:
            # #268: a required field missing from `params` (e.g. `description`
            # for Adr, `probability`/`impact` for Risk) surfaces here as a
            # Python TypeError from the service call's missing positional
            # argument. Left uncaught, that used to fall through to the bare
            # `except Exception` below as an opaque INTERNAL_ERROR (HTTP 500)
            # instead of an actionable client-facing validation error —
            # mirrors the TypeError handling in `_handle_update` (#83 Bug 1).
            return ToolResult.error(
                "VALIDATION_ERROR", f"Missing or invalid field for {self.prefix}.create: {exc}"
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_update(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        kwargs = {k: v for k, v in params.items() if k != "id"}
        # #83 Bug 2: `status` is a workflow-managed field for every entity
        # this generic group serves (Adr, Risk, Issue, GlossaryTerm, ...) —
        # it can only move through `{prefix}.outdate` / `{prefix}.reactivate`
        # (soft-delete/restore) or the REST workflow `transitions/` endpoint
        # (WorkflowEngine-gated), mirroring the REST PATCH rejection in
        # WorkflowTransitionsMixin._validate_patch_payload (QA-123). Unlike the
        # REST guard — which since #263 tolerates an unchanged status echo
        # because the UI resends the whole form — this one rejects `status`
        # outright: MCP callers pass explicit kwargs, so there is no
        # whole-object echo to accommodate here. Forwarding
        # it here used to hit the update method's missing parameter and
        # surface as an opaque "INTERNAL_ERROR: ...got an unexpected keyword
        # argument 'status'" instead of an actionable message.
        if "status" in kwargs:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"'status' cannot be changed via {self.prefix}.update; use "
                f"{self.prefix}.outdate / {self.prefix}.reactivate for "
                "lifecycle changes, or the REST workflow transitions "
                "endpoint (POST /api/v1/<entity>/{id}/transitions/) for a "
                "state-machine-gated status change.",
            )
        try:
            obj = self._update_method(ctx=auth_context, **{self._update_id_param: obj_id}, **kwargs)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except TypeError as exc:
            # Any other unexpected/misnamed field: surface a clear, actionable
            # message instead of letting it fall through to a bare
            # INTERNAL_ERROR (#83 Bug 1 root cause pattern).
            return ToolResult.error(
                "VALIDATION_ERROR", f"Invalid field for {self.prefix}.update: {exc}"
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_delete(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        try:
            self._delete_method(ctx=auth_context, **{self._delete_id_param: obj_id})
            return ToolResult.ok({"status": "deleted"})
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _resolve_workspace_id(self, *, obj_id: uuid.UUID, auth_context: AuthContext) -> uuid.UUID:
        """Fetch the entity and read its ``workspace_id`` — the same
        resolution the entity services use internally before calling
        ``workflow.services.outdate()`` (e.g. ``AdrService.delete_adr``).
        """
        obj = self._read_method(ctx=auth_context, **{self._read_id_param: obj_id})
        return obj.workspace_id

    def _handle_outdate(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        reason = params.get("reason", "")
        from workflow.services import outdate

        try:
            workspace_id = self._resolve_workspace_id(obj_id=obj_id, auth_context=auth_context)
            outdate(
                item_id=obj_id,
                item_type=self._item_type,
                workspace_id=workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        return ToolResult.ok({"id": str(obj_id), "status": "outdated"})

    def _handle_reactivate(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        from workflow.services import reactivate

        try:
            workspace_id = self._resolve_workspace_id(obj_id=obj_id, auth_context=auth_context)
            result = reactivate(
                item_id=obj_id,
                item_type=self._item_type,
                workspace_id=workspace_id,
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValueError as exc:
            return ToolResult.error("INVALID_STATE", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        return ToolResult.ok({"id": str(obj_id), "status": result.new_state})

    def _handle_query(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        include_outdated = params.get("include_outdated", False)
        try:
            results = self._list_method(
                workspace_id=workspace_id, ctx=auth_context, include_deleted=include_outdated
            )
            return ToolResult.ok({"items": [self._to_dict(r) for r in results]})
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
