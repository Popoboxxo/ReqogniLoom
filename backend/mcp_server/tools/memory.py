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

Surface added by the Wave-7 memory-MCP stream (#1301/#1302/#1300), each mapped
1:1 onto an existing REST service so no domain logic is duplicated here:

* ``memory.promote`` (#1301) — the MCP twin of
  ``POST /api/v1/memory/entries/<id>/promote/``; delegates to
  ``MemoryEntryService.promote`` (own user memory -> workspace, Editor+ in the
  target workspace).
* ``memory.overview`` / ``memory.projection`` / ``memory.export`` /
  ``memory.delete_workspace`` / ``memory.settings`` (#1302) — the MCP twins of
  the System-Admin REST memory surface. The four ``MemoryAdminService``
  operations re-assert ``System-Admin`` inside the service;
  ``memory.settings`` (whose service deliberately has no ctx check — see
  ``MemorySettingsService``'s docstring) applies the same ``MemoryPolicy``
  System-Admin gate the REST view uses.
* ``memory.remember_interaction`` (#1300, MCP part only) — explicitly triggers
  the consolidation pipeline (``memory.tasks.consolidate_interaction_task``)
  for one interaction, so the LLM extraction + duplicate/contradiction
  three-way logic runs instead of a raw ``memory.write``. The event/projector
  wiring for the automatic path is a separate stream.

These five admin tools and the two remaining writes are fail-closed
write-classified (see ``tool_registry``): a read_only/AUTHOR key must not reach
the tenant-wide admin surface or drive an LLM/embedding call. The admin five
additionally require the ADMIN capability tier (``_GOVERNANCE_TOOL_NAMES``),
mirroring the System-Admin bar REST enforces.

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

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict

from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    optional_uuid,
    require_param,
    require_uuid,
)
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.memory_admin_service import MemoryAdminService
from application.memory_entry_service import MemoryEntryService
from application.memory_settings_service import MemorySettingsService
from memory.backends import VALID_REASONING_LEVELS
from memory.health import envelope
from memory.policy import MemoryPolicy
from memory.ratelimit import MemoryWriteRateLimitExceeded


def _jsonable(value: Any) -> Any:
    """Recursively coerce UUID/datetime/date/Decimal into JSON-safe values.

    The admin memory services (``MemoryAdminService``) return ORM-typed fields
    — ``workspace_id`` UUIDs, ``created_at``/``last_consolidated_at``
    datetimes — that the MCP response encoder (``json.dumps``) cannot
    serialise. Mirrors ``GenericCrudToolGroup._jsonify``; kept local because
    that one is a private staticmethod of an unrelated group.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    # datetime is a subclass of date -- check it first for full ISO precision.
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


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
        # Wave-7 memory-MCP stream (#1301/#1302/#1300).
        "memory.promote": "_handle_promote",
        "memory.remember_interaction": "_handle_remember_interaction",
        "memory.overview": "_handle_overview",
        "memory.projection": "_handle_projection",
        "memory.export": "_handle_export",
        "memory.settings": "_handle_settings",
        "memory.delete_workspace": "_handle_delete_workspace",
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
        {
            "name": "memory.promote",
            "description": (
                "Promote the caller's own user-scoped memory into a workspace "
                "(write). Editor+ in the target workspace; the original entry is "
                "kept and marked superseded_by the new one."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entry_id": {"type": "string"},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "change_reason": {"type": "string"},
                },
                "required": ["entry_id", "workspace_id"],
            },
        },
        {
            "name": "memory.remember_interaction",
            "description": (
                "Enqueue the memory consolidation pipeline for one interaction "
                "text (write): an active worker runs LLM fact extraction + "
                "duplicate/contradiction handling, so this is NOT a raw write."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "interaction_text": {"type": "string"},
                    "artifact_id": {"type": "string", "format": "uuid"},
                    "entity_type": {"type": "string"},
                },
                "required": ["workspace_id", "interaction_text"],
            },
        },
        {
            "name": "memory.overview",
            "description": (
                "System-Admin overview of every workspace's memory in the "
                "active tenant: enabled flag, per-tier entry counts, contributor "
                "count and last consolidation timestamp."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "memory.projection",
            "description": (
                "System-Admin 2D PCA projection + similarity clustering of the "
                "scoped memory embeddings. scope='workspace' needs workspace_id; "
                "scope='global' spans the tenant."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["workspace", "global"]},
                    "workspace_id": {"type": "string", "format": "uuid"},
                },
                "required": ["scope"],
            },
        },
        {
            "name": "memory.export",
            "description": (
                "System-Admin DSGVO export of the tenant's live memory entries "
                "across both team-owned tiers (JSON shape; the REST twin also "
                "offers CSV)."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "memory.settings",
            "description": (
                "System-Admin view of the deployment-global effective memory "
                "configuration (DB override falling back to env vars per field), "
                "with a <field>_is_override flag per field."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "memory.delete_workspace",
            "description": (
                "System-Admin DSGVO delete of every memory tier a workspace "
                "owns (workspace, its artifacts and its current members' user "
                "memory) through the active backend."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "format": "uuid"},
                },
                "required": ["workspace_id"],
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
        service returns a ``datetime``. Besides ``digest``/``generated_at``/
        ``backend``/``degraded`` the answer carries the AP-B5.1 (#1155)
        derivation pair: ``derivation_status`` (one of ``ok``/``none``/
        ``failed``/``unsupported``/``unknown`` — whether the engine's DERIVER
        has produced anything for this scope, machine-distinguishable from
        "the read itself degraded") and ``derived_count`` (exact count only
        when the backend could bound it, else ``null`` — never a fabricated
        total). On pgvector the pair is always ``unsupported``/``null``.
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
                "derivation_status": digest.derivation_status,
                "derived_count": digest.derived_count,
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

    def _handle_promote(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Promote own user memory into workspace scope (write, #1301).

        The MCP twin of ``POST /api/v1/memory/entries/<id>/promote/``.
        ``workspace_id`` is required (the schema says so; a caller that omits it
        gets a clear ``VALIDATION_ERROR``) even though the service would fall
        back to ``ctx.workspace_id`` — the MCP surface keeps the target explicit.
        Ownership + Editor+ in the target workspace are enforced by
        ``MemoryEntryService.promote`` / ``MemoryPolicy``; the response is the
        promoted entry's view (same shape as ``memory.write``).
        """
        entry_id = require_param(params, "entry_id")
        workspace_id = require_uuid(params, "workspace_id")
        return self._service_call(
            lambda: MemoryEntryService().promote(
                auth_context,
                entry_id=entry_id,
                target_scope="workspace",
                workspace_id=workspace_id,
                change_reason=params.get("change_reason"),
            )
        )

    def _handle_remember_interaction(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """Enqueue the consolidation pipeline for one interaction (write, #1300).

        Unlike ``memory.write`` (a raw single fact), this dispatches
        ``memory.tasks.consolidate_interaction_task`` — the same Celery entry
        point the interview-outbox projector uses — so the LLM extraction plus
        the duplicate/contradiction three-way logic run instead of a blind
        write. The event/projector wiring for the *automatic* path is a separate
        stream; this tool is the explicit trigger.

        The call returns as soon as the task is enqueued (``scheduled`` /
        ``task_id``); the consolidation result is produced worker-side. The
        workspace memory-enabled toggle the projector honours is deliberately
        not re-checked here — same as every other ``memory.write`` surface, the
        toggle gates the automatic projector path, not an explicit call.
        """
        workspace_id = require_uuid(params, "workspace_id")
        interaction_text = require_param(params, "interaction_text")
        artifact_id = optional_uuid(params, "artifact_id")
        entity_type = str(params.get("entity_type") or "")

        def _call() -> Dict[str, Any]:
            from memory.tasks import consolidate_interaction_task

            result = consolidate_interaction_task.delay(
                tenant_id=str(auth_context.tenant_id),
                workspace_id=str(workspace_id),
                user_id=str(auth_context.user_id),
                interaction_text=interaction_text,
                artifact_id=str(artifact_id) if artifact_id else None,
                entity_type=entity_type,
            )
            return {"scheduled": True, "task_id": str(result.id)}

        return self._service_call(_call)

    def _handle_overview(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """System-Admin per-workspace memory overview (read, #1302).

        MCP twin of ``GET /api/v1/system/memory/workspaces/``.
        ``MemoryAdminService.list_workspace_overview`` asserts System-Admin
        itself; the handler only JSON-serialises the ORM-typed row fields.
        """
        return self._service_call(
            lambda: {
                "results": _jsonable(
                    MemoryAdminService().list_workspace_overview(auth_context)
                ),
                **envelope(),
            }
        )

    def _handle_projection(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """System-Admin PCA/cluster projection of scoped memory (read, #1302).

        MCP twin of ``GET /api/v1/system/memory/projection/``. Scope vocabulary
        and the ``workspace_id`` requirement for ``scope='workspace'`` are owned
        by ``MemoryAdminService.get_projection`` (System-Admin asserted there),
        so a bad scope is a clear ``VALIDATION_ERROR`` rather than a raw 500.
        """
        scope = require_param(params, "scope")
        workspace_id = optional_uuid(params, "workspace_id")
        return self._service_call(
            lambda: {
                **_jsonable(
                    MemoryAdminService().get_projection(
                        auth_context, scope=scope, workspace_id=workspace_id
                    )
                ),
                **envelope(),
            }
        )

    def _handle_export(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """System-Admin DSGVO export of the tenant's memory entries (#1302).

        MCP twin of ``GET /api/v1/system/memory/entries/export/`` (JSON shape;
        the REST view additionally offers CSV). Delegates to the same
        ``MemoryAdminService.list_entries`` (System-Admin asserted there), capped
        at the shared ``EXPORT_MAX_ROWS`` bound, and reports ``truncated`` when
        the cap bit.
        """
        def _call() -> Dict[str, Any]:
            from memory.memory_rest import EXPORT_MAX_ROWS

            result = MemoryAdminService().list_entries(
                auth_context, scope="global", page=1, page_size=EXPORT_MAX_ROWS
            )
            rows = result["results"]
            return {
                "entries": _jsonable(rows),
                "count": result["count"],
                "truncated": result["count"] > len(rows),
                **envelope(),
            }

        return self._service_call(_call)

    def _handle_settings(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """System-Admin view of the effective memory configuration (#1302).

        MCP twin of ``GET /api/v1/system/memory-settings/``. Unlike the other
        admin tools, ``MemorySettingsService`` has no ctx-based check by design
        (the REST view gates it), so the same ``MemoryPolicy`` System-Admin gate
        the REST twin applies is enforced here. The env-var overlay is reused
        from the REST view so both transports report the identical effective
        configuration instead of drifting.
        """
        def _call() -> Dict[str, Any]:
            MemoryPolicy.assert_can_purge(auth_context)
            from memory.memory_rest import _with_env_fallback

            return _with_env_fallback(
                MemorySettingsService().get_effective_settings()
            )

        return self._service_call(_call)

    def _handle_delete_workspace(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """System-Admin DSGVO delete of a workspace's memory (#1302).

        MCP twin of ``DELETE /api/v1/system/memory/workspaces/<id>/``.
        ``MemoryAdminService.delete_workspace_memory`` asserts System-Admin and
        answers ``NotFoundError`` for an unknown workspace; the handler only
        JSON-serialises the UUID in the result.
        """
        workspace_id = require_uuid(params, "workspace_id")
        return self._service_call(
            lambda: {
                **_jsonable(
                    MemoryAdminService().delete_workspace_memory(
                        auth_context, workspace_id
                    )
                ),
                **envelope(),
            }
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
