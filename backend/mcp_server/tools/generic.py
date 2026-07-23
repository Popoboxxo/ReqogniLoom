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


class GenericCrudToolGroup(BaseToolGroup):
    """Generic tool group for standard CRUD operations."""

    def __init__(self, prefix: str, service_class: Any):
        self.prefix = prefix
        self._service = service_class()
        # Resolved once so the handlers below don't need per-entity branching.
        self._read_method = _resolve_method(self._service, prefix, "get")
        self._create_method = _resolve_method(self._service, prefix, "create")
        self._update_method = _resolve_method(self._service, prefix, "update")
        self._delete_method = _resolve_method(self._service, prefix, "delete")
        self._read_id_param = _resolve_id_param(self._read_method)
        self._update_id_param = _resolve_id_param(self._update_method)
        self._delete_id_param = _resolve_id_param(self._delete_method)
        # Dynamically define the TOOL_MAP for this instance
        self._TOOL_MAP = {
            f"{prefix}.read": "_handle_read",
            f"{prefix}.create": "_handle_create",
            f"{prefix}.update": "_handle_update",
            f"{prefix}.delete": "_handle_delete",
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
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_update(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        kwargs = {k: v for k, v in params.items() if k != "id"}
        try:
            obj = self._update_method(ctx=auth_context, **{self._update_id_param: obj_id}, **kwargs)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_delete(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        try:
            self._delete_method(ctx=auth_context, **{self._delete_id_param: obj_id})
            return ToolResult.ok({"status": "deleted"})
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
