"""Generic MCP Tool Group for standard CRUD entities."""
from typing import Any, Dict

from application.base import NotFoundError
from auth_tenancy.context import AuthContext
from mcp_server.tools.base import BaseToolGroup, ToolResult, require_uuid

class GenericCrudToolGroup(BaseToolGroup):
    """Generic tool group for standard CRUD operations."""
    
    def __init__(self, prefix: str, service_class: Any):
        self.prefix = prefix
        self._service = service_class()
        # Dynamically define the TOOL_MAP for this instance
        self._TOOL_MAP = {
            f"{prefix}.read": "_handle_read",
            f"{prefix}.create": "_handle_create",
            f"{prefix}.update": "_handle_update",
            f"{prefix}.delete": "_handle_delete",
        }
    
    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert object to dict dynamically."""
        if hasattr(obj, "__dict__"):
            data = {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
            # Stringify UUIDs
            for k, v in data.items():
                import uuid
                if isinstance(v, uuid.UUID):
                    data[k] = str(v)
            return data
        return {"id": str(getattr(obj, "id", ""))}

    def _handle_read(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        try:
            obj = self._service.get(auth_context, obj_id)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

    def _handle_create(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        kwargs = {k: v for k, v in params.items() if k != "workspace_id"}
        try:
            # Most services have create(ctx, workspace_id, ...)
            obj = self._service.create(ctx=auth_context, workspace_id=workspace_id, **kwargs)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_update(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        kwargs = {k: v for k, v in params.items() if k != "id"}
        try:
            # Using basic update contract
            obj = self._service.update(ctx=auth_context, **{f"{self.prefix}_id": obj_id}, **kwargs)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except Exception:
            # Fallback for services using generic ID
            try:
                obj = self._service.update(ctx=auth_context, id=obj_id, **kwargs)
                return ToolResult.ok({"data": self._to_dict(obj)})
            except Exception as e2:
                return ToolResult.error("INTERNAL_ERROR", str(e2))

    def _handle_delete(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        try:
            # Using basic delete contract
            self._service.delete(ctx=auth_context, **{f"{self.prefix}_id": obj_id})
            return ToolResult.ok({"status": "deleted"})
        except Exception:
            try:
                self._service.delete(ctx=auth_context, id=obj_id)
                return ToolResult.ok({"status": "deleted"})
            except Exception as e2:
                return ToolResult.error("INTERNAL_ERROR", str(e2))
