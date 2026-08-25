"""MemoryToolGroup — MCP tool group for AI Long-Term Memory (Spec 2026-08-24, Task 7).

Exposes ``memory.query`` / ``memory.list`` / ``memory.forget`` over the
``MemoryBackend`` abstraction (Task 3). ``memory.query`` and ``memory.list``
are read-only (registered in ``_READ_ONLY_TOOL_NAMES``); ``memory.forget`` is
a write and is RBAC-gated (``_WRITE_TOOL_PREFIXES``) in addition to its own
ownership/admin check below.

Tenant-context note: ``MemoryBackend.query()``/``.list_recent()``/``.forget()``
already activate tenant context internally per call (see
``memory.backends._tenant_context``), so the handlers below do not need to
arm it for those calls. ``_handle_forget`` additionally does direct ORM
lookups against ``UserTenantMemory``/``WorkspaceMemory`` BEFORE calling the
backend, to decide ownership -- those two RLS-gated tables DO require an
explicitly active tenant context around them (same bug class already fixed
in Tasks 3/5/6 of this branch), so this handler wraps them (and the
subsequent ``AuthorizationService.active_roles_for`` call, which reads the
also-RLS-gated ``UserRole`` table) in a single ``_tenant_context`` block
using the same ``persistence.middleware.set_request_tenant``/
``clear_request_tenant`` primitives ``memory/backends.py`` itself uses --
NOT ``TenantContext.set_tenant(...)`` alone, which only satisfies the
Django-ORM-level filter and leaves Postgres RLS's session variable unset.
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from auth_tenancy.context import AuthContext
from auth_tenancy.services.authorization import AuthorizationService
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, ParameterError, require_param
from memory.backends import _tenant_context, get_memory_backend
from memory.models import UserTenantMemory, WorkspaceMemory


class MemoryToolGroup(BaseToolGroup):
    """MCP tool group for consolidated AI long-term memory (query/list/forget)."""

    _TOOL_MAP = {
        "memory.query": "_handle_query",
        "memory.list": "_handle_list",
        "memory.forget": "_handle_forget",
    }
    _TOOL_SCHEMAS = [
        {
            "name": "memory.query",
            "description": "Semantic search over workspace or user-tenant-wide memory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["workspace", "user"]},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["scope", "query"],
            },
        },
        {
            "name": "memory.list",
            "description": "Chronological listing of recent memory entries, no similarity search.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["workspace", "user"]},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["scope"],
            },
        },
        {
            "name": "memory.forget",
            "description": (
                "Delete a memory entry. Requires ownership (own user memory) or "
                "workspace-admin (workspace memory)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"entry_id": {"type": "string", "format": "uuid"}},
                "required": ["entry_id"],
            },
        },
    ]

    def _resolve_scope_id(self, params: Dict[str, Any], auth_context: AuthContext) -> UUID:
        """Return the scope_id matching ``params["scope"]``.

        ``scope="workspace"`` -> the caller-supplied ``workspace_id``;
        ``scope="user"`` -> the caller's own ``user_id`` (a caller can only
        ever query/list their own user-tenant-wide memory, never another
        user's -- there is no ``user_id`` param on these tools by design).
        """
        scope = require_param(params, "scope")
        if scope not in ("workspace", "user"):
            raise ParameterError(f"Parameter 'scope' must be 'workspace' or 'user', got {scope!r}.")
        if scope == "workspace":
            return UUID(str(require_param(params, "workspace_id")))
        return auth_context.user_id

    def _handle_query(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        """Semantic search over memory entries (read-only)."""
        scope = params.get("scope")
        query_text = require_param(params, "query")
        scope_id = self._resolve_scope_id(params, auth_context)
        backend = get_memory_backend()
        entries = backend.query(
            auth_context.tenant_id, scope, scope_id, query_text, top_k=params.get("top_k", 5)
        )
        return ToolResult.ok({"entries": [{"id": str(e.entry_id), "content": e.content} for e in entries]})

    def _handle_list(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        """Chronological listing of recent memory entries (read-only)."""
        scope = params.get("scope")
        scope_id = self._resolve_scope_id(params, auth_context)
        backend = get_memory_backend()
        entries = backend.list_recent(auth_context.tenant_id, scope, scope_id, limit=params.get("limit", 20))
        return ToolResult.ok({"entries": [{"id": str(e.entry_id), "content": e.content} for e in entries]})

    def _handle_forget(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        """Delete a memory entry.

        Ownership check: the entry must be the caller's own ``UserTenantMemory``,
        OR a ``WorkspaceMemory`` row in a workspace where the caller holds the
        admin role.
        """
        entry_id = UUID(str(require_param(params, "entry_id")))
        with _tenant_context(auth_context.tenant_id):
            user_entry = UserTenantMemory.objects.filter(id=entry_id).first()
            if user_entry is not None:
                if user_entry.user_id != auth_context.user_id:
                    return ToolResult.error("PERMISSION_DENIED", "cannot forget another user's memory")
                get_memory_backend().forget(auth_context.tenant_id, entry_id)
                return ToolResult.ok({"deleted": True})

            ws_entry = WorkspaceMemory.objects.filter(id=entry_id).first()
            if ws_entry is None:
                return ToolResult.error("NOT_FOUND", "memory entry not found")

            roles = AuthorizationService().active_roles_for(
                user_id=auth_context.user_id, workspace_id=ws_entry.workspace_id
            )
            if "admin" not in roles:
                return ToolResult.error(
                    "PERMISSION_DENIED", "requires workspace-admin to forget workspace memory"
                )
            get_memory_backend().forget(auth_context.tenant_id, entry_id)
            return ToolResult.ok({"deleted": True})


__all__ = ["MemoryToolGroup"]
