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
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from audit.services import mcp_audit_handoff
from mcp_server.protocol_handler import ToolResult
from persistence.tenancy import TenantContextNotSetError
from workflow import state_reader

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


def reject_unknown_params(
    params: Dict[str, Any], allowed: List[str], tool_name: str
) -> None:
    """Raise ParameterError if *params* contains a key not in *allowed*.

    Issue #459 (finding 1): opt-in, per-tool guard against unrecognised
    parameters that would otherwise be silently ignored (e.g. a client
    sending ``test_case_id`` instead of the documented ``test_case_ids``
    array — the run is created but the typo'd parameter has no effect).

    Deliberately NOT wired into ``BaseToolGroup.execute_tool`` as a global
    dispatcher-level check: across 40+ tools, a blanket "reject unknown
    params" rule risks breaking existing clients that rely on extra keys
    being tolerated/ignored, without a coordinated audit of every tool's
    ``inputSchema``. Call this explicitly from handlers that want strict
    validation instead.
    """
    unknown = sorted(k for k in params if k not in allowed)
    if unknown:
        raise ParameterError(
            f"Unknown parameter(s) for tool '{tool_name}': {', '.join(unknown)}. "
            f"Allowed parameters: {', '.join(sorted(allowed))}."
        )


# ---------------------------------------------------------------------------
# Workflow-engine status seam (Datenmodell-Konsolidierung Phase 1)
# ---------------------------------------------------------------------------


def resolve_engine_status(
    item_type: str,
    item_id: Any,
    fallback: Optional[str] = None,
    *,
    status_map: Optional[Dict[str, str]] = None,
) -> str:
    """Resolve an entity's ``status`` wire value from the workflow engine.

    Every MCP payload builder that used to read an entity's own (still
    present, Phase 0 mirror) ``status`` column now goes through this seam
    instead -- ``WorkflowItemState.current_state`` is the single source of
    truth (D-1); the wire key name and value vocabulary are unchanged.

    Pass a pre-batched *status_map* (:func:`resolve_status_map`) for
    list-shaped responses so a page of N items costs one engine query
    instead of N -- mirrors
    ``rest_api.mixins.workflow_state.WorkflowStateSerializerMixin``'s
    batching. Omit it to resolve a single item inline via
    ``workflow.state_reader.current_state``.

    Falls back to *fallback* when given (mainly for tests exercising the
    fallback path with a literal), else to *item_type*'s preset initial state
    (``workflow.state_reader.initial_state``) when the engine has no
    ``WorkflowItemState`` row for the item (e.g. Goal/MainGoal, which have no
    state backfill, or any item created in a definition-less workspace), so
    an untracked item never silently regresses to an empty string. Also
    falls back when no ``TenantContext`` is active: production dispatch
    (``ToolRegistry.dispatch_request``) always activates it before a handler
    runs, so this only matters for tests that call ``execute_tool`` directly
    against a mocked service with no live tenant/DB.

    Datenmodell-Konsolidierung Task 12: the entity's own ``status`` column is
    dropped, so production callers no longer have a column value to pass as
    *fallback* -- they call this with *fallback* omitted and rely on the
    preset-initial-state default (documented, reviewed data-loss tradeoff,
    see Task 12 report Finding 2).
    """
    if status_map is not None:
        engine_state = status_map.get(str(item_id))
    else:
        try:
            engine_state = state_reader.current_state(item_type, item_id)
        except TenantContextNotSetError:
            engine_state = None
    if engine_state is not None:
        return engine_state
    return fallback or state_reader.initial_state(item_type)


def resolve_status_map(item_type: str, item_ids: Iterable[Any]) -> Dict[str, str]:
    """Batch-resolve workflow-engine states for many items in one query.

    Thin, defensive wrapper over ``workflow.state_reader.current_states`` for
    list-shaped MCP responses -- pass the result as :func:`resolve_engine_status`'s
    *status_map* so a page of N items costs one engine query, not N. Returns
    an empty mapping (every item then falls back to its own column) when no
    ``TenantContext`` is active, instead of propagating
    ``TenantContextNotSetError`` -- see :func:`resolve_engine_status` for why
    that is safe.
    """
    try:
        return state_reader.current_states(item_type, item_ids)
    except TenantContextNotSetError:
        return {}


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

    def schema_param_names(self, tool_name: str) -> List[str]:
        """Return the declared ``inputSchema`` property names of *tool_name*.

        Single source of truth for handlers that call
        :func:`reject_unknown_params`: deriving the allow-list from the
        published schema keeps the two from drifting apart, so adding a
        property to the schema cannot turn a documented call into a
        validation error.

        Returns an empty list for an unknown tool name or a group that has no
        explicit ``_TOOL_SCHEMAS`` — callers should treat that as "no strict
        validation possible" rather than "nothing is allowed".
        """
        for schema in self.get_tool_schemas():
            if schema.get("name") == tool_name:
                properties = schema.get("inputSchema", {}).get("properties", {})
                return list(properties.keys())
        return []

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
    "reject_unknown_params",
    "resolve_engine_status",
    "resolve_status_map",
    "write_mcp_audit",
    "mcp_audit_handoff",
]
