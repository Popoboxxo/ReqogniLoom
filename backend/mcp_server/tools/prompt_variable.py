"""MCP tool group for the prompt variable catalog (spec §3.1).

leaf_id : COMP-MC-PV
req_id  : REQ-L2-PT-001 (tenant-scoped editable prompt configuration),
          REQ-L2-MC-012 (MCP audit trail for write tools)

Exposes four tools, all admin-gated (mirroring the ``prompt_template`` group's
``_check_admin``: without it any valid API key could rewrite the numeric caps
that bound every AI derivation, a prompt-injection-adjacent vector):

  prompt_variable.list(workspace_id?) -> {variables, count}
  prompt_variable.get(name, workspace_id?) -> {variable}
  prompt_variable.set(name, value, workspace_id?, var_type?, description?)
  prompt_variable.clear(name, workspace_id?) -> {variable}

``.set`` on a ``kind="data"`` name is refused with VALIDATION_ERROR — those
values are computed from artifact data by the code that builds the render
call, so there is nothing an agent could meaningfully store. ``.set`` on an
unknown name creates a new ``config`` variable, which is the point of the
catalog: a prompt body can reference ``{new_name}`` immediately afterwards
with no code change.

All reads are admin-gated too (not just writes): the catalog carries free-text
descriptions of a tenant's AI configuration.
"""
from __future__ import annotations

from typing import Any, Dict

from application.base import NotFoundError, ValidationError
from application.prompt_variable_service import PromptVariableService
from auth_tenancy.context import AuthContext

from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    optional_uuid,
    require_param,
    write_mcp_audit,
)


class PromptVariableToolGroup(BaseToolGroup):
    """Prompt variable catalog tool group (read + write, tenant-scoped)."""

    _TOOL_MAP = {
        "prompt_variable.list": "_handle_list",
        "prompt_variable.get": "_handle_get",
        "prompt_variable.set": "_handle_set",
        "prompt_variable.clear": "_handle_clear",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "prompt_variable.list",
            "description": (
                "List every prompt variable in the catalog with its factory, "
                "tenant and workspace value plus the resolved effective value "
                "and its origin. kind='config' entries are editable; "
                "kind='data' entries are code-bound documentation."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope whose overrides to resolve.",
                    },
                },
            },
        },
        {
            "name": "prompt_variable.get",
            "description": (
                "Return one prompt variable's per-scope state and resolved "
                "effective value. NOT_FOUND when the name is neither "
                "factory-registered nor stored for this tenant."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name."},
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope whose override to resolve.",
                    },
                },
                "required": ["name"],
            },
        },
        {
            "name": "prompt_variable.set",
            "description": (
                "Publish a new active version of a config prompt variable for "
                "a (tenant, workspace_id, name) scope. Omitting workspace_id "
                "writes the tenant-wide default. An unknown name creates a new "
                "config variable usable in any prompt body immediately. "
                "kind='data' names are rejected (write, audited, admin-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name."},
                    "value": {
                        "description": "New value; must match the variable's var_type.",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope. Omit for the tenant default.",
                    },
                    "var_type": {
                        "type": "string",
                        "description": (
                            "int | str | bool | json — only used when creating a "
                            "name that has no factory entry yet (default 'str')."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Documentation shown in the catalog UI.",
                    },
                },
                "required": ["name", "value"],
            },
        },
        {
            "name": "prompt_variable.clear",
            "description": (
                "Drop a prompt variable's active row at the given scope so it "
                "falls back to the next level (workspace -> tenant -> factory). "
                "Idempotent; returns the now-effective state "
                "(write, audited, admin-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name."},
                    "workspace_id": {
                        "type": "string",
                        "description": "Optional workspace scope whose override to drop.",
                    },
                },
                "required": ["name"],
            },
        },
    ]

    @staticmethod
    def _check_admin(auth_context: AuthContext) -> "ToolResult | None":
        """Return a ``PERMISSION_DENIED`` ToolResult if the caller is not admin."""
        if auth_context.has_role("admin"):
            return None
        return ToolResult.error(
            "PERMISSION_DENIED",
            f"Permission denied: role 'admin' required, "
            f"user has {auth_context.active_roles}",
        )

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        workspace_id = optional_uuid(params, "workspace_id")
        variables = PromptVariableService().list_variables(
            auth_context, workspace_id=workspace_id
        )
        return ToolResult.ok({"variables": variables, "count": len(variables)})

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        name = require_param(params, "name")
        workspace_id = optional_uuid(params, "workspace_id")
        try:
            variable = PromptVariableService().get_variable(
                auth_context, str(name), workspace_id=workspace_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"variable": variable})

    def _handle_set(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        name = require_param(params, "name")
        if "value" not in params:
            return ToolResult.error(
                "VALIDATION_ERROR", "Required parameter 'value' is missing."
            )
        workspace_id = optional_uuid(params, "workspace_id")
        try:
            variable = PromptVariableService().set_variable(
                auth_context,
                name=str(name),
                value=params["value"],
                workspace_id=workspace_id,
                var_type=params.get("var_type"),
                description=params.get("description"),
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="update",
            entity_type="PromptVariable",
            entity_id=auth_context.tenant_id,
            tool_name="prompt_variable.set",
            api_key=api_key,
            details={"name": str(name)},
        )
        return ToolResult.ok({"variable": variable})

    def _handle_clear(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        denied = self._check_admin(auth_context)
        if denied is not None:
            return denied
        name = require_param(params, "name")
        workspace_id = optional_uuid(params, "workspace_id")
        try:
            variable = PromptVariableService().clear_variable(
                auth_context, name=str(name), workspace_id=workspace_id
            )
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        write_mcp_audit(
            ctx=auth_context,
            operation="delete",
            entity_type="PromptVariable",
            entity_id=auth_context.tenant_id,
            tool_name="prompt_variable.clear",
            api_key=api_key,
            details={"name": str(name)},
        )
        return ToolResult.ok({"variable": variable})


__all__ = ["PromptVariableToolGroup"]
