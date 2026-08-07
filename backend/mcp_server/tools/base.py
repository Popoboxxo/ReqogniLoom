"""
MCP Tool Groups — shared base class and utilities.

leaf_id : COMP-MC-003..006
req_id  : REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail),
          REQ-L2-MC-011 (structured error response)

Provides:
- BaseToolGroup: common execute_tool dispatcher and audit helper.
- Parameter validation helpers.
"""
from __future__ import annotations

import logging
from abc import ABC
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from audit.services import mcp_audit_handoff
from mcp_server.protocol_handler import ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared parameter validation
# ---------------------------------------------------------------------------


class ParameterError(ValueError):
    """Raised when required parameters are missing or invalid."""


def require_param(params: Dict[str, Any], name: str) -> Any:
    """Return params[name] or raise ParameterError."""
    val = params.get(name)
    if val is None or (isinstance(val, str) and not val.strip()):
        raise ParameterError(f"Required parameter '{name}' is missing or empty.")
    return val


def optional_uuid(params: Dict[str, Any], name: str) -> Optional[UUID]:
    """Return UUID from params[name] or None."""
    val = params.get(name)
    if val is None:
        return None
    try:
        return UUID(str(val))
    except (ValueError, AttributeError):
        raise ParameterError(f"Parameter '{name}' is not a valid UUID: '{val}'")


def require_uuid(params: Dict[str, Any], name: str) -> UUID:
    """Return UUID from params[name] or raise ParameterError."""
    val = params.get(name)
    if val is None:
        raise ParameterError(f"Required parameter '{name}' is missing.")
    try:
        return UUID(str(val))
    except (ValueError, AttributeError):
        raise ParameterError(f"Parameter '{name}' is not a valid UUID: '{val}'")


# ---------------------------------------------------------------------------
# MCP Audit helper (REQ-L2-MC-012)
# ---------------------------------------------------------------------------


def write_mcp_audit(
    ctx: AuthContext,
    operation: str,
    entity_type: str,
    entity_id: UUID,
    tool_name: str,
    api_key: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Write an MCP-specific audit log entry synchronously.

    REQ-L2-MC-012: Audit entry must be written before the response is sent.
    The api_key is passed as the raw secret to ``audit.services.log_write``;
    the SHA-256 hashing (with ``"sha256:"`` prefix) is performed by
    ``audit.writer.ContextEnricher`` — the raw key is never stored.

    Codeberg #313: for handlers whose sole underlying ApplicationService
    call would otherwise write its own, redundant internal entry for this
    same entity, wrap that one call in :func:`mcp_audit_handoff` (re-exported
    here from ``audit.services``) immediately before calling this function —
    this call then becomes the single audit entry for the operation.
    """
    try:
        from audit.services import log_write

        log_write(
            actor=str(ctx.user_id),
            actor_type="agent",
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            ctx={
                "source": "mcp",
                "client_name": tool_name,
                "api_key": api_key,
            },
            details=details,
        )
    except Exception:
        logger.exception(
            "MCP audit write failed for tool=%s entity=%s", tool_name, entity_id
        )


# ---------------------------------------------------------------------------
# Base tool group
# ---------------------------------------------------------------------------


class BaseToolGroup(ABC):
    """Common base for all MCP tool groups.

    Subclasses implement ``_TOOL_MAP`` mapping tool names → handler methods.
    """

    # Subclasses must define: {"tool.name": "_method_name"}
    _TOOL_MAP: Dict[str, str] = {}
    
    # Subclasses can define schema mapping: {"tool.name": {...schema dict...}}
    _TOOL_SCHEMAS: List[Dict[str, Any]] = []

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return the MCP JSON schemas for all tools in this group."""
        if self._TOOL_SCHEMAS:
            return self._TOOL_SCHEMAS
        
        # Fallback for groups without explicit schemas
        return [
            {
                "name": name,
                "description": f"Execute {name}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "kwargs": {
                            "type": "object",
                            "description": "Additional parameters for the tool."
                        }
                    }
                }
            }
            for name in self._TOOL_MAP.keys()
        ]

    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        auth_context: AuthContext,
        api_key: str,
    ) -> ToolResult:
        """Dispatch *tool_name* to the registered handler method.

        Args:
            tool_name: MCP tool identifier.
            params: Caller parameters (api_key already stripped).
            auth_context: Validated and role-resolved AuthContext.
            api_key: Raw API key (for audit hash — never logged plaintext).

        Returns:
            ToolResult from the handler, or UNKNOWN_TOOL error.
        """
        method_name = self._TOOL_MAP.get(tool_name)
        if not method_name:
            return ToolResult.error(
                "UNKNOWN_TOOL", f"Tool '{tool_name}' not found in {type(self).__name__}."
            )
        handler = getattr(self, method_name, None)
        if handler is None:
            return ToolResult.error("INTERNAL_ERROR", f"Handler '{method_name}' not implemented.")
        try:
            return handler(params=params, auth_context=auth_context, api_key=api_key)
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except Exception as exc:
            # fix #108: str(exc) on an unmapped exception (IntegrityError,
            # ProgrammingError, KeyError, ...) can contain SQL fragments,
            # table/column names, or constraint names. Log the real detail,
            # return only a static message to the caller.
            logger.exception("Error in %s.%s for tool=%s", type(self).__name__, method_name, tool_name)
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")


__all__ = [
    "BaseToolGroup",
    "ParameterError",
    "require_param",
    "optional_uuid",
    "require_uuid",
    "write_mcp_audit",
    "mcp_audit_handoff",
]
