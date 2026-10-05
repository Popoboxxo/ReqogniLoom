"""MemoryToolGroup — MCP tool group for AI Long-Term Memory (Spec 2026-08-24, RFC #1002 PR B).

Exposes ``memory.write`` / ``memory.get`` / ``memory.query`` / ``memory.list``
/ ``memory.forget`` / ``memory.digest`` / ``memory.ask`` over the
``MemoryEntryService`` façade (ADR-01: the tools perform no ORM access of their
own). ``memory.query``/``memory.list``/``memory.get``/``memory.digest`` are
read-only (registered in ``_READ_ONLY_TOOL_NAMES``);
``memory.write``/``memory.forget``/``memory.ask`` are writes and are RBAC-gated
(``_WRITE_TOOL_PREFIXES``) in addition to the ``MemoryPolicy`` check the service
performs. ``memory.ask`` is write-gated even though it is a read semantically:
it invokes a generative LLM call (``peer.chat`` on Honcho), so a read_only/
Viewer key must not be able to drive LLM spend -- the same rule as
``interview.grounding_context``.

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
from memory.backends import VALID_REASONING_LEVELS
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
        "memory.digest": "_handle_digest",
        "memory.ask": "_handle_ask",
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
            "name": "memory.digest",
            "description": (
                "Consolidated digest of one memory scope: the active backend's "
                "prompt-ready summary of what a workspace (or one artifact in "
                "it) remembers right now."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "artifact_id": {"type": "string", "format": "uuid"},
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "memory.ask",
            "description": (
                "Answer a natural-language question from one memory scope "
                "(the backend's dialectic surface; workspace, or one artifact "
                "in it). Degrades on backends without a generative engine."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 10000},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "artifact_id": {"type": "string", "format": "uuid"},
                    "reasoning_level": {
                        "type": "string",
                        # Derived from the backend contract so the MCP surface
                        # and VALID_REASONING_LEVELS cannot drift apart.
                        "enum": list(VALID_REASONING_LEVELS),
                    },
                },
                "required": ["query", "workspace_id"],
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

    def _handle_digest(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Return the active backend's digest for one scope (read-only).

        ``workspace_id`` is required because it is also the scope id when no
        ``artifact_id`` is given; with an ``artifact_id`` the service resolves
        the artifact's owning workspace itself. The response is the digest's
        own fields — ``generated_at`` is serialised to ISO-8601 because the
        service returns a ``datetime``.
        """
        workspace_id = require_param(params, "workspace_id")
        artifact_id = optional_uuid(params, "artifact_id")

        def _call() -> Dict[str, Any]:
            digest = MemoryEntryService().digest(
                auth_context, workspace_id=workspace_id, artifact_id=artifact_id
            )
            return {
                "digest": digest.text,
                "generated_at": digest.generated_at.isoformat(),
                "backend": digest.backend,
                "degraded": digest.degraded,
            }

        return self._service_call(_call)

    def _handle_ask(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Answer a natural-language question from one scope (LLM-invoking write).

        Mirrors :meth:`_handle_digest`'s scope handling: ``workspace_id`` is
        required (it is also the scope id when no ``artifact_id`` is given;
        with one, the service resolves the artifact's owning workspace).
        Honcho's dialectic engine produces the answer; a backend without one
        (pgvector) returns ``degraded=True`` instead of raising. The response
        mirrors the digest's four keys -- ``answer``/``generated_at``/
        ``backend``/``degraded`` -- plus ``detail``, with ``generated_at``
        serialised to ISO-8601. ``detail`` carries the degradation cause as
        ``engine_error:<ExceptionClassName>`` or
        ``unknown_scope:<ExceptionClassName>`` (never user data) when the answer
        degraded, so a caller can tell a backend outage apart from an unknown
        scope -- and both from "nothing known". The exception class name stays a
        substring for backwards compatibility. It is an empty string on a
        successful answer.

        Registered as a WRITE tool (``_WRITE_TOOL_PREFIXES``): the call drives a
        generative LLM, so a read_only/Viewer key must not reach it.
        """
        query = require_param(params, "query")
        workspace_id = require_param(params, "workspace_id")
        artifact_id = optional_uuid(params, "artifact_id")
        reasoning_level = params.get("reasoning_level")

        def _call() -> Dict[str, Any]:
            answer = MemoryEntryService().ask(
                auth_context,
                query=query,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                reasoning_level=reasoning_level,
            )
            return {
                "answer": answer.text,
                "generated_at": answer.generated_at.isoformat(),
                "backend": answer.backend,
                "degraded": answer.degraded,
                "detail": answer.detail,
            }

        return self._service_call(_call)

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
