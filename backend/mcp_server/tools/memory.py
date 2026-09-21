"""MemoryToolGroup — MCP tool group for AI Long-Term Memory (Spec 2026-08-24, RFC #1002 PR B).

Exposes ``memory.write`` / ``memory.get`` / ``memory.query`` / ``memory.list``
/ ``memory.forget`` over the ``MemoryEntryService`` façade (ADR-01: the tools
perform no ORM access of their own). ``memory.query``/``memory.list``/
``memory.get`` are read-only (registered in ``_READ_ONLY_TOOL_NAMES``);
``memory.write``/``memory.forget`` are writes and are RBAC-gated
(``_WRITE_TOOL_PREFIXES``) in addition to the ``MemoryPolicy`` check the service
performs.

Scopes: ``user`` (own only), ``workspace`` (any active role to read, Editor+ to
write), ``artifact`` (role in the artifact's workspace). The service resolves
the artifact's workspace and applies the matrix; these handlers only translate
parameters and errors.

Every response carries ``backend`` and ``degraded`` (F9): a read that returns no
rows while the backend is unhealthy answers ``degraded=true``, so an agent can
tell "nothing remembered" apart from "backend down".

Note on the write gate: the dispatcher's fail-closed RBAC gate requires
``Operation.WRITE`` for ``memory.write``, so a Viewer-scoped key cannot reach it
even for its own user-scoped memory. That is the same narrowing every MCP write
tool applies, and it is deliberate — the REST matrix's "any authenticated user
writes own" is enforced by ``MemoryPolicy`` there.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    optional_uuid,
    require_param,
)
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.memory_entry_service import MemoryEntryService
from memory.health import envelope
from memory.ratelimit import MemoryWriteRateLimitExceeded


class MemoryToolGroup(BaseToolGroup):
    """MCP tool group for consolidated AI long-term memory."""

    _TOOL_MAP = {
        "memory.write": "_handle_write",
        "memory.get": "_handle_get",
        "memory.query": "_handle_query",
        "memory.list": "_handle_list",
        "memory.forget": "_handle_forget",
    }
    _TOOL_SCHEMAS = [
        {
            "name": "memory.write",
            "description": (
                "Persist a memory fact. scope=user writes for the caller, "
                "workspace/artifact require Editor+ in the owning workspace."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "scope": {"type": "string", "enum": ["workspace", "user", "artifact"]},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "artifact_id": {"type": "string", "format": "uuid"},
                    "confidence": {"type": "number", "default": 1.0},
                    "change_reason": {"type": "string"},
                },
                "required": ["content", "scope"],
            },
        },
        {
            "name": "memory.get",
            "description": "Fetch one memory entry with its full provenance.",
            "inputSchema": {
                "type": "object",
                "properties": {"entry_id": {"type": "string"}},
                "required": ["entry_id"],
            },
        },
        {
            "name": "memory.query",
            "description": (
                "Semantic search over one or more memory scopes "
                "(workspace, user, artifact)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["workspace", "user", "artifact"]},
                    "scopes": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["workspace", "user", "artifact"]},
                    },
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "artifact_id": {"type": "string", "format": "uuid"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "memory.list",
            "description": "Chronological listing of recent memory entries, no similarity search.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["workspace", "user", "artifact"]},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "artifact_id": {"type": "string", "format": "uuid"},
                    "limit": {"type": "integer", "default": 20},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 25},
                    "contributor_user_id": {"type": "string", "format": "uuid"},
                },
                "required": [],
            },
        },
        {
            "name": "memory.forget",
            "description": (
                "Delete a memory entry. Requires ownership (own user memory) or "
                "workspace-admin (workspace/artifact memory)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entry_id": {"type": "string"},
                    "change_reason": {"type": "string"},
                },
                "required": ["entry_id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_write(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Persist a memory fact (write)."""
        content = require_param(params, "content")
        scope = require_param(params, "scope")
        workspace_id = optional_uuid(params, "workspace_id")
        artifact_id = optional_uuid(params, "artifact_id")
        confidence = params.get("confidence", 1.0)
        return self._service_call(
            lambda: MemoryEntryService().write(
                auth_context,
                content=content,
                scope=scope,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                confidence=confidence,
                change_reason=params.get("change_reason"),
            )
        )

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Return one entry's full view (read-only)."""
        entry_id = require_param(params, "entry_id")
        return self._service_call(
            lambda: MemoryEntryService().get(auth_context, entry_id=entry_id)
        )

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Semantic search over one or more scopes (read-only)."""
        query_text = require_param(params, "query")
        scopes = params.get("scopes") or params.get("scope")
        workspace_id = optional_uuid(params, "workspace_id")
        artifact_id = optional_uuid(params, "artifact_id")
        top_k = params.get("top_k", 5)
        return self._service_call(
            lambda: MemoryEntryService().search(
                auth_context,
                query=query_text,
                scopes=scopes,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                top_k=top_k,
            ),
            entries_key=True,
        )

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Chronological listing of recent entries (read-only)."""
        scope = params.get("scope")
        workspace_id = optional_uuid(params, "workspace_id")
        artifact_id = optional_uuid(params, "artifact_id")
        contributor_user_id = optional_uuid(params, "contributor_user_id")
        page_size = params.get("page_size") or params.get("limit") or 20
        return self._service_call(
            lambda: MemoryEntryService().list(
                auth_context,
                workspace_id=workspace_id,
                scope=scope,
                artifact_id=artifact_id,
                contributor_user_id=contributor_user_id,
                page=params.get("page", 1),
                page_size=page_size,
            ),
            entries_key=True,
        )

    def _handle_forget(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Delete a memory entry (write).

        ``entry_id`` is a plain String — an external backend id (e.g. a honcho
        nanoid carried in ``backend_ref``) is a legitimate value and must not be
        coerced to a UUID. Ownership/permission is decided by ``MemoryPolicy``
        inside the service.
        """
        entry_id = require_param(params, "entry_id")
        return self._service_call(
            lambda: MemoryEntryService().forget(
                auth_context, entry_id=entry_id, change_reason=params.get("change_reason")
            ),
            success={"deleted": True, **envelope()},
        )

    # ------------------------------------------------------------------
    # Error translation
    # ------------------------------------------------------------------

    def _service_call(
        self,
        call: Callable[[], Any],
        *,
        entries_key: bool = False,
        success: Any = None,
    ) -> ToolResult:
        """Run one ``MemoryEntryService`` call, translating its exceptions.

        Returns the service payload (or *success* when given) as a successful
        ``ToolResult``. ``MemoryWriteRateLimitExceeded`` maps to the dedicated
        ``RATE_LIMITED`` JSON-RPC error code with the limit/retry-after details;
        ``ParameterError`` propagates so ``execute_tool`` answers
        ``VALIDATION_ERROR``.
        """
        try:
            data = call()
        except ParameterError:
            raise
        except MemoryWriteRateLimitExceeded as exc:
            return ToolResult.error(
                "RATE_LIMITED",
                str(exc),
                details={"limit": exc.limit, "retry_after": exc.retry_after},
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        if success is not None:
            return ToolResult.ok(success)
        if entries_key and isinstance(data, dict) and "items" in data:
            payload = dict(data)
            payload["entries"] = payload.pop("items")
            return ToolResult.ok(payload)
        if isinstance(data, dict):
            return ToolResult.ok(data)
        return ToolResult.ok({"result": data})


__all__ = ["MemoryToolGroup"]
