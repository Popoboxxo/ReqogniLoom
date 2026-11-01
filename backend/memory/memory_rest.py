"""
memory — REST adapter for Memory Settings (Spec 2026-08-24, Task 11) and
Memory Admin UI Phase 1 (Spec 2026-08-26).

Endpoints:
    GET/PUT /api/v1/workspaces/<uuid:workspace_id>/memory-settings/
        GET: any workspace member may view (missing row -> ``enabled: True``,
        the memory feature defaults ON, mirrors
        ``WorkspaceContextSettings``'s "missing row = default state"
        convention). PUT: editor or admin (workspace-scoped) may toggle.
    GET/PUT /api/v1/system/memory-settings/
        GET: System-Admin (``ctx.has_role("admin") or
        AuthorizationService().is_tenant_admin(...)`` — same pattern as
        ``TenantThemeDefaultView``) and returns the effective configuration
        (DB override from ``SystemMemorySettings`` falling back to env vars
        per field, see :func:`_with_env_fallback`).
        PUT: **Django superuser only** (:func:`_is_superuser`) — the write
        target is a deployment-global, cross-tenant row, which a merely
        workspace-scoped admin must not be able to change (final
        whole-branch review C-1). Applies a partial override (Memory Admin
        UI Phase 3, spec 2026-08-26). Delegates to
        :class:`application.memory_settings_service.MemorySettingsService`.
    POST /api/v1/system/memory-settings/reset/
        Django superuser only (same rationale as PUT). Clears every override
        field back to NULL, so the effective configuration falls back
        entirely to env vars. See :class:`SystemMemorySettingsResetView`.
    GET /api/v1/system/memory/workspaces/
        System-Admin only. Lists one overview row per workspace in the
        active tenant. Delegates to
        :meth:`application.memory_admin_service.MemoryAdminService.list_workspace_overview`.
    DELETE /api/v1/system/memory/workspaces/<uuid:workspace_id>/
        System-Admin only. Deletes both memory tiers for a workspace.
        Delegates to
        :meth:`application.memory_admin_service.MemoryAdminService.delete_workspace_memory`.
    GET /api/v1/system/memory/entries/
        System-Admin only (Memory Admin UI Phase 5, spec 2026-08-26).
        Paginated, full-text-filterable list of live consolidated memory
        entries across both tiers. See :class:`SystemMemoryEntriesListView`.
    GET /api/v1/system/memory/projection/
        System-Admin only (Memory Admin UI Phase 5). 2D PCA projection +
        similarity clustering of the scoped embedding vectors. See
        :class:`SystemMemoryProjectionView`.
    GET/DELETE /api/v1/memory/me/
        Any authenticated user, no role required (Memory Admin UI Phase 4,
        spec 2026-08-26). Self-service over the caller's OWN
        own ``scope="user"`` ``MemoryEntry`` rows only — never workspace-scoped
        memory. See :class:`MemorySelfServiceView`.
    GET/PUT /api/v1/memory/me/settings/   (Plan A T-A1-4)
        Any authenticated user reads and updates their OWN memory switches,
        stored as Q1 user-level preferences (``memory.enabled``,
        ``memory.disabled_slots``) through :mod:`memory.user_settings`. With
        ``?workspace_id=<uuid>`` the GET additionally reports that workspace's
        ``opt_out_allowed``; a caller without a role there gets 404 (QR-S21).
        See :class:`MemorySelfServiceSettingsView`.
    POST /api/v1/memory/me/   (issue #1291)
        Any authenticated user writes a ``scope="user"`` fact for themselves —
        the REST write path for the personal scope, which previously existed
        only over MCP ``memory.write``. Same ``MemoryPolicy`` write matrix and
        same ``memory.write`` rate limiter as MCP. See
        :meth:`MemorySelfServiceView.post`.
    POST /api/v1/workspaces/<uuid:workspace_id>/memory/entries/   (existing)
        Editor+ creates a ``scope="workspace"`` fact (issue #1291 adds a
        fail-closed guard: a body naming another scope is rejected, since the
        URL pins it). See :meth:`WorkspaceMemoryEntriesView.post`.
    PATCH /api/v1/memory/entries/<str:entry_id>/   (issue #1291)
        Rewrite one entry's content history-preservingly (a new entry
        supersedes the old). Owner for ``user`` memory, Editor+ for
        ``workspace``/``artifact``; charged to the ``memory.write`` limiter.
        See :meth:`MemoryEntryDetailView.patch`.
    DELETE /api/v1/workspaces/<uuid:workspace_id>/memory/entries/   (issue #1291)
        Purge the whole workspace scope; Workspace-Admin only. See
        :meth:`WorkspaceMemoryEntriesView.delete`.
    POST /api/v1/system/memory/entries/   (issue #1291)
        System-Admin write on the entries collection, same body contract and
        same per-scope ``MemoryPolicy`` as the other write surfaces (the admin
        gate can only narrow). See :meth:`SystemMemoryEntriesListView.post`.
    GET /api/v1/system/memory/workspaces/   (issue #1300)
        The System-Admin overview additionally carries
        ``memory_consolidations_total`` (per-trigger-source counter of enqueued
        memory consolidations) + ``consolidation_total``, so the learning
        loop's health is readable without a log grep. See
        :meth:`SystemMemoryWorkspaceOverviewView.get` and :mod:`memory.metrics`.

Both views rely on the tenant context already activated by
``AuthTenancyAuthentication`` during DRF authentication (COMP-AT-003
``TenantContextService.activate`` -> ``persistence.middleware.
set_request_tenant``) — mirrors ``rest_api.settings_views.
ContextGraphSettingsView``/``ReviewPolicyView``/``rest_api.preference_views.
UserPreferenceView``, none of which re-activate the tenant context
themselves. No bare ``persistence.tenancy.TenantContext.set_tenant(...)``
call appears anywhere in this module — that call only satisfies the
Django-ORM side and never arms Postgres RLS's ``app.current_tenant`` session
variable (the exact bug class already fixed in ``memory/backends.py``,
``llm_adapter/tasks.py`` and others); it is unnecessary here because a real
HTTP request already has both isolation layers armed by the time a view
method runs.
"""
from __future__ import annotations

import csv
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Max
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.memory_admin_service import MemoryAdminService
from application.memory_entry_service import MAX_PAGE_SIZE as MEMORY_MAX_PAGE_SIZE
from application.memory_entry_service import VALID_SCOPES, MemoryEntryService
from application.memory_settings_service import (
    BackendSettingsValidationError,
    MemorySettingsService,
)
from application.preference_registry import get_preference_key, validate_preference_value
from application.preference_service import PreferenceService, levels_for
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService
from memory.backends import VALID_QUERY_SOURCES
from memory.health import envelope
from memory.injection_policy import (
    ALLOW_USER_OPT_OUT_KEY,
    DISABLED_SLOTS_KEY,
    MEMORY_CONSUMER_SLOTS,
)
from memory.models import MemoryEntry, WorkspaceMemorySettings
from memory.schema_serializers import (
    MemoryAdminEntryListResponseSerializer,
    MemoryAnswerResponseSerializer,
    MemoryAskRequestSerializer,
    MemoryDigestResponseSerializer,
    MemoryEntryExportResponseSerializer,
    MemoryEntryForgetResponseSerializer,
    MemoryEntryListResponseSerializer,
    MemoryEntryPromoteRequestSerializer,
    MemoryEntryViewSerializer,
    MemoryProjectionResponseSerializer,
    MemoryScopePurgeResponseSerializer,
    MemorySearchResponseSerializer,
    MemorySelfServiceDeleteResponseSerializer,
    MemorySelfServiceResponseSerializer,
    MemorySelfServiceSettingsResponseSerializer,
    MemorySelfServiceSettingsWriteSerializer,
    MemoryWorkspaceDeleteResponseSerializer,
    MemoryWorkspaceOverviewResponseSerializer,
    SystemMemorySettingsResponseSerializer,
    WorkspaceMemorySettingsResponseSerializer,
    WorkspaceMemorySettingsWriteSerializer,
)
from memory.ratelimit import MemoryWriteRateLimitExceeded
from memory.user_settings import (
    MemoryUserSettingRejected,
    read_user_settings,
    write_user_settings,
)
from persistence.models import User
from persistence.qdrant_config import (
    DEFAULT_QDRANT_COLLECTION_PREFIX,
    DEFAULT_QDRANT_DISTANCE,
    DEFAULT_QDRANT_HNSW_EF_CONSTRUCT,
    DEFAULT_QDRANT_HNSW_M,
    DEFAULT_QDRANT_TIMEOUT,
    QDRANT_DISTANCE_ATTRS,
)
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang

#: Upper bound on rows returned by the DSGVO export (Auskunftsanspruch). Large
#: enough for a realistic tenant, bounded so the endpoint cannot stream an
#: unbounded table into memory.
EXPORT_MAX_ROWS = 5000


def _parse_uuid_param(raw: Any, name: str) -> Any:
    """Return *raw* as a ``UUID``, or ``None`` when absent; raise on malformed."""
    if raw in (None, ""):
        return None
    try:
        return UUID(str(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(f"Invalid {name}: {raw!r}") from exc


class MemoryEntryWriteSerializer(serializers.Serializer):
    """Body for the canonical memory write surfaces (issue #1291).

    Mirrors the MCP ``memory.write`` tool's input schema 1:1 -- ``content``,
    ``scope`` (``user``|``workspace``|``artifact``), an optional
    ``workspace_id``/``artifact_id`` for the scope's target and an optional
    ``confidence``/``change_reason`` -- so the REST and MCP transports cannot
    drift in the scopes they accept. Only the *shape* is validated here; the
    per-scope owner contract (``scope="workspace"`` requires ``workspace_id``,
    ``scope="artifact"`` requires ``artifact_id``, ``scope="user"`` forbids
    both) and the ``MemoryPolicy`` permission matrix are enforced by
    :class:`application.memory_entry_service.MemoryEntryService.write`, exactly
    as they are for the MCP tool.
    """

    content = serializers.CharField()
    scope = serializers.ChoiceField(choices=["user", "workspace", "artifact"])
    workspace_id = serializers.UUIDField(required=False, allow_null=True)
    artifact_id = serializers.UUIDField(required=False, allow_null=True)
    confidence = serializers.FloatField(required=False, default=1.0)
    change_reason = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class MemoryEntryContentSerializer(serializers.Serializer):
    """Body for the content-bearing write surfaces (issue #1291).

    Shared by ``PATCH /api/v1/memory/entries/<entry_id>/`` and
    ``POST /api/v1/memory/me/``. ``content`` is required (a write that changes
    nothing is pointless); ``confidence``/``change_reason`` are optional. The
    entry's scope/owner are never taken from the body -- an edit cannot move a
    fact into another scope.
    """

    content = serializers.CharField()
    confidence = serializers.FloatField(required=False, allow_null=True)
    change_reason = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


def _memory_error_response(exc: Exception, lang: str) -> Response:
    """Map a memory-service exception onto the standard REST error body.

    ``MemoryWriteRateLimitExceeded`` -> 429 with a ``Retry-After`` header;
    permission -> 403; not found -> 404; validation -> 400. Anything else
    re-raises (a genuine bug must not be masked as a 4xx).
    """
    if isinstance(exc, MemoryWriteRateLimitExceeded):
        response = Response(
            build_error_response(
                "RATE_LIMITED",
                lang,
                details=[{"field": "limit", "errors": [exc.limit]}],
                message=str(exc),
            ),
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        response["Retry-After"] = str(exc.retry_after)
        return response
    if isinstance(exc, PermissionDeniedError):
        return Response(
            build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
            status=status.HTTP_403_FORBIDDEN,
        )
    if isinstance(exc, NotFoundError):
        return Response(
            build_error_response("NOT_FOUND", lang, message=str(exc)),
            status=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, ValidationError):
        return Response(
            build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
            status=status.HTTP_400_BAD_REQUEST,
        )
    raise exc


def _auth_or_401(request: Request, lang: str):
    """Return the request's AuthContext, or a 401 Response."""
    try:
        return get_auth_context(request)
    except Exception:  # noqa: BLE001 - any auth failure maps to 401 here
        return Response(
            build_error_response("AUTHENTICATION_REQUIRED", lang),
            status=status.HTTP_401_UNAUTHORIZED,
        )


def _is_system_admin(ctx) -> bool:
    """True tenant-admin only — READ-side gate for ``SystemMemorySettingsView``.

    Tightened per a 5-phase Memory Admin UI review: this endpoint carries no
    ``workspace_id``, so the previous ``ctx.has_role("admin") or ...`` form
    let a caller who is merely admin of ONE workspace through — ``has_role``
    resolves from the tenant-wide UNION of the caller's ``UserRole`` rows
    when no workspace is in scope. That let a workspace-scoped admin read
    the deployment-global effective config (embedding provider/model,
    ollama_base_url, whether a Honcho API key is set) for every tenant, the
    exact class of over-broad access :func:`_is_superuser`'s docstring
    already calls out for the write side. Now matches the same
    tenant-admin-only bar every sibling System-Admin endpoint in this file
    uses (``MemoryAdminService._assert_system_admin``, Phase 1/5). Deliberately
    NOT used for the write side of ``/api/v1/system/memory-settings/`` — see
    :func:`_is_superuser`, which requires Django superuser, stricter still.
    """
    return AuthorizationService().is_tenant_admin(
        user_id=ctx.user_id, tenant_id=ctx.tenant_id
    )


def _is_superuser(user_id) -> bool:
    """Return whether *user_id* belongs to a Django superuser.

    Write gate for the deployment-global ``SystemMemorySettings`` singleton.
    :func:`_is_system_admin` is NOT sufficient here: this endpoint carries no
    ``workspace_id``, so ``ctx.has_role("admin")`` resolves from the
    tenant-wide UNION of the caller's ``UserRole`` rows — a merely
    workspace-scoped admin passes it. The row written here is process-global
    and shared by every tenant (it can, for instance, redirect all embedding
    traffic to an arbitrary ``ollama_base_url``), so a write needs a
    deployment-level identity, not a tenant/workspace one.

    Local copy of ``mcp_server.tools.users.UserTools._caller_is_superuser``
    (same semantics, same best-effort ``except`` policy) rather than an
    import: ``memory`` has no dependency on ``mcp_server`` today and a Layer-3
    app should not start importing another Layer-3 app for three lines.
    """
    try:
        user = User.objects.filter(id=user_id).first()
    except Exception:  # noqa: BLE001 - a lookup failure must never grant access
        return False
    return bool(user and user.is_superuser)


class SystemMemorySettingsWriteSerializer(serializers.Serializer):
    """Partial-update payload for ``PUT /api/v1/system/memory-settings/``."""

    # "openai" is a registered, documented provider and must stay selectable
    # here so a deployment can re-affirm its own configuration. Note (#794):
    # selecting a provider whose native output width differs from
    # persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS disables
    # embedding writes and semantic search for the mismatched columns — that
    # is now reported by `manage.py check` and at WARNING on the first skip,
    # rather than degrading silently.
    embedding_provider = serializers.ChoiceField(
        choices=["sentence-transformers", "ollama", "openai", "mock"], required=False, allow_null=True
    )
    embedding_model_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=128)
    ollama_base_url = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    embedding_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # "honcho" is selectable again: memory.honcho_backend now implements the
    # full MemoryBackend contract against the verified honcho-ai SDK and is
    # registered at startup via memory.apps.MemoryConfig.ready(), so
    # get_memory_backend() resolves it instead of raising. It still requires
    # HONCHO_BASE_URL (or the honcho_base_url override below) to be set —
    # that is surfaced as a health-check failure, not a save-time error, so an
    # admin can configure the URL and the backend in either order.
    memory_backend = serializers.ChoiceField(
        choices=["pgvector", "honcho", "qdrant"], required=False, allow_null=True
    )
    honcho_base_url = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    honcho_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=512)
    # #1286: the dialectic/peer/scope surface was configurable only via env.
    # Expose it (override-or-env, same pattern as the fields above).
    honcho_dialectic_level = serializers.ChoiceField(
        choices=["minimal", "low", "medium", "high", "max"], required=False, allow_null=True
    )
    honcho_peer_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    honcho_workspace_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    honcho_app_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    honcho_session_ttl = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    # ADR-020 V1: Qdrant is an optional vector backend. It requires
    # QDRANT_BASE_URL (or the qdrant_base_url override below); a missing value
    # is surfaced as a health-check failure, not a save-time error, so an admin
    # can configure URL and backend in either order. There is deliberately NO
    # qdrant dimension field -- the width mirrors EMBEDDING_VECTOR_DIMENSIONS.
    qdrant_base_url = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=255
    )
    qdrant_collection_prefix = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=64
    )
    qdrant_distance = serializers.ChoiceField(
        # Vocabulary comes from the shared SSOT so the serializer can never
        # reject a name the runtime backend accepts (or vice versa).
        choices=list(QDRANT_DISTANCE_ATTRS),
        required=False,
        allow_null=True,
    )
    qdrant_timeout = serializers.FloatField(required=False, allow_null=True, min_value=0.1)
    qdrant_hnsw_m = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    qdrant_hnsw_ef_construct = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    qdrant_prefer_grpc = serializers.BooleanField(required=False, allow_null=True)
    qdrant_api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=512
    )
    # RFC #1002 PR B: fixed-window write ratelimit for ``memory.write``.
    # ``0`` is an explicit "unlimited" override; ``null`` clears the override so
    # ``MEMORY_WRITE_RATE_LIMIT_PER_HOUR`` (default 60) wins again.
    memory_write_rate_limit_per_hour = serializers.IntegerField(
        required=False, allow_null=True, min_value=0
    )
    # T-A0b-3: backend-neutral maps. Per-field validation (types, choices,
    # secret routing) lives in MemorySettingsService, which owns the registry;
    # the view maps its BackendSettingsValidationError to a 400 with the exact
    # ``backend_options.<backend>.<field>`` paths.
    backend_options = serializers.JSONField(required=False)
    backend_secrets = serializers.JSONField(required=False, write_only=True)


def _with_env_fallback(effective: dict) -> dict:
    """Fill in the env-var value for every field the DB override left None,
    so the response's top-level fields are always the ACTUAL effective
    configuration (override-or-env), not just the raw override row.
    """
    import os

    env_defaults = {
        "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "sentence-transformers"),
        "embedding_model_name": os.environ.get("EMBEDDING_MODEL_NAME"),
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL"),
        "embedding_timeout": int(os.environ.get("EMBEDDING_TIMEOUT", "10")),
        "memory_backend": os.environ.get("MEMORY_BACKEND", "pgvector"),
        "honcho_base_url": os.environ.get("HONCHO_BASE_URL"),
        # #1286: honcho dialectic/peer/scope overrides (override-or-env).
        "honcho_dialectic_level": os.environ.get("HONCHO_DIALECTIC_LEVEL"),
        "honcho_peer_name": os.environ.get("HONCHO_PEER_NAME"),
        "honcho_workspace_id": os.environ.get("HONCHO_WORKSPACE_ID"),
        "honcho_app_id": os.environ.get("HONCHO_APP_ID"),
        "honcho_session_ttl": (
            int(os.environ["HONCHO_SESSION_TTL"]) if os.environ.get("HONCHO_SESSION_TTL") else None
        ),
        # Read-only: the targeted Honcho service version (best-effort from env;
        # the UI shows a placeholder when unknown).
        "honcho_version": os.environ.get("HONCHO_VERSION"),
        "qdrant_base_url": os.environ.get("QDRANT_BASE_URL"),
        "qdrant_collection_prefix": os.environ.get(
            "QDRANT_COLLECTION_PREFIX", DEFAULT_QDRANT_COLLECTION_PREFIX
        ),
        "qdrant_distance": os.environ.get("QDRANT_DISTANCE", DEFAULT_QDRANT_DISTANCE),
        "qdrant_timeout": float(os.environ.get("QDRANT_TIMEOUT", DEFAULT_QDRANT_TIMEOUT)),
        "qdrant_hnsw_m": int(os.environ.get("QDRANT_HNSW_M", DEFAULT_QDRANT_HNSW_M)),
        "qdrant_hnsw_ef_construct": int(
            os.environ.get("QDRANT_HNSW_EF_CONSTRUCT", DEFAULT_QDRANT_HNSW_EF_CONSTRUCT)
        ),
        "qdrant_prefer_grpc": os.environ.get("QDRANT_PREFER_GRPC", "").strip().lower()
        in ("1", "true", "yes", "on"),
        "memory_write_rate_limit_per_hour": int(
            os.environ.get("MEMORY_WRITE_RATE_LIMIT_PER_HOUR", "60")
        ),
    }
    out = dict(effective)
    for field, env_value in env_defaults.items():
        if out.get(field) is None:
            out[field] = env_value
    return out


class WorkspaceMemorySettingsView(APIView):
    """``/api/v1/workspaces/<uuid:workspace_id>/memory-settings/``.

    GET: any workspace member. PUT: editor or admin (workspace-scoped).

    Plan A T-A1-3 (ENT-A5 = A): the response is additive. ``enabled`` stays
    the ``WorkspaceMemorySettings.enabled`` facade column with its historical
    wire contract (``PUT {"enabled": …}`` behaves and is gated exactly as
    before); ``disabled_slots`` and ``allow_user_opt_out`` are Q1 workspace
    values written through :class:`application.preference_service.
    PreferenceService` — one validation path, one audit entry per key, no
    direct preference-row writes.

    Two different values, deliberately kept apart:

    * ``disabled_slots`` / ``allow_user_opt_out`` are the **stored workspace
      level** — exactly what a PUT writes. They are the editable source of
      truth, so a GET→PUT round-trip is a no-op and can never promote a
      caller's personal (user-level) opt-out into workspace-wide policy.
    * ``effective_disabled_slots`` is the **merged** value the injection
      policy actually applies (global ∪ workspace ∪ the caller's user level).
      Read-only, additive, for display only. ``memory.allow_user_opt_out`` has
      no merged dimension (workspace is its only level), so there is no
      ``effective_*`` twin for it.

    ``available_slots`` is the derived slot vocabulary the workspace may
    toggle (union of the policy's consumer slots and the explicit HARD_OFF slot
    names), so the UI never has to hard-code it.
    """

    #: Q1 keys this facade may write, mapped to their wire field name.
    _POLICY_FIELDS = (
        ("disabled_slots", DISABLED_SLOTS_KEY),
        ("allow_user_opt_out", ALLOW_USER_OPT_OUT_KEY),
    )

    @staticmethod
    def _available_slots() -> list[dict[str, Any]]:
        """Sorted slot catalogue; ``hard_off`` marks the never-injectable ones."""
        from application.prompt_slots import MEMORY_HARD_OFF_SLOTS

        names = set(MEMORY_CONSUMER_SLOTS) | set(MEMORY_HARD_OFF_SLOTS)
        return [
            {"name": name, "hard_off": name in MEMORY_HARD_OFF_SLOTS}
            for name in sorted(names)
        ]

    @staticmethod
    def _merge_disabled_slots(*levels: Any) -> list[str]:
        """Union of the set levels, in Q1's documented order (global, workspace, user).

        Mirrors ``application.preference_service._resolve``'s ``union`` mode for
        this key (its default is ``[]``). Duplicated here on purpose: the
        workspace view must be able to answer with the *post-write* merged value
        without a second preference read after the commit (a read after a
        committed write must never turn a successful PUT into a 500).
        """
        merged: list[str] = []
        for values in levels:
            if not isinstance(values, list):
                continue
            for item in values:
                if item not in merged:
                    merged.append(item)
        return merged

    @staticmethod
    def _policy_state(ctx, workspace_id: str) -> dict[str, Any]:
        """Read the stored workspace level and the two other union levels.

        One read of the workspace level (``get_level``: stored, not merged) plus
        the tenant-global and caller-user levels, which PUT cannot change and
        therefore reads exactly once, before any write.
        """
        workspace_uuid = UUID(str(workspace_id))
        stored = PreferenceService().get_level(
            ctx, scope="workspace", workspace_id=workspace_uuid
        )["values"]
        global_levels = levels_for(
            tenant_id=ctx.tenant_id,
            workspace_id=None,
            user_id=None,
            key=DISABLED_SLOTS_KEY,
        )
        user_levels = levels_for(
            tenant_id=ctx.tenant_id,
            workspace_id=None,
            user_id=ctx.user_id,
            key=DISABLED_SLOTS_KEY,
        )
        stored_disabled = stored.get(DISABLED_SLOTS_KEY)
        return {
            "stored_disabled_slots": (
                stored_disabled if isinstance(stored_disabled, list) else []
            ),
            "stored_allow_user_opt_out": stored.get(ALLOW_USER_OPT_OUT_KEY, True),
            "global_disabled_slots": global_levels.global_,
            "user_disabled_slots": user_levels.user,
        }

    def _payload(
        self,
        *,
        enabled: bool,
        stored_disabled_slots: list[str],
        stored_allow_user_opt_out: bool,
        effective_disabled_slots: list[str],
    ) -> dict[str, Any]:
        """Assemble the response from values that are already known/in memory."""
        return {
            "enabled": enabled,
            "disabled_slots": stored_disabled_slots,
            "allow_user_opt_out": stored_allow_user_opt_out,
            "effective_disabled_slots": effective_disabled_slots,
            "available_slots": self._available_slots(),
        }

    @extend_schema(
        tags=["memory"],
        summary="Read the workspace's memory feature toggle and injection policy",
        responses={
            200: WorkspaceMemorySettingsResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
        },
    )
    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        # Workspace membership + READ permission is already enforced by the
        # default RbacPermission gate (rest_api.auth_enforcer): the URL
        # carries workspace_id, so AuthTenancyAuthentication resolves
        # active_roles scoped to THIS workspace, and a non-member (no
        # UserRole here) resolves to () -> denied 403 before this method
        # ever runs (mirrors WorkspaceBannerView's GET, see its docstring).
        settings_row = WorkspaceMemorySettings.objects.filter(workspace_id=workspace_id).first()
        enabled = settings_row.enabled if settings_row else True
        state = self._policy_state(ctx, workspace_id)
        return Response(
            self._payload(
                enabled=enabled,
                stored_disabled_slots=state["stored_disabled_slots"],
                stored_allow_user_opt_out=state["stored_allow_user_opt_out"],
                effective_disabled_slots=self._merge_disabled_slots(
                    state["global_disabled_slots"],
                    state["stored_disabled_slots"],
                    state["user_disabled_slots"],
                ),
            )
        )

    @extend_schema(
        tags=["memory"],
        summary="Toggle the workspace's memory feature and injection policy",
        request=WorkspaceMemorySettingsWriteSerializer,
        responses={
            200: WorkspaceMemorySettingsResponseSerializer,
            400: OpenApiResponse(
                description=(
                    "'enabled'/'allow_user_opt_out' is not a boolean, or "
                    "'disabled_slots' names an unknown or hard-off slot."
                )
            ),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(
                description=(
                    "Editor or admin role required; the Q1 workspace policy "
                    "keys additionally require the workspace-config operation."
                )
            ),
        },
    )
    def put(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        roles = AuthorizationService().active_roles_for(user_id=ctx.user_id, workspace_id=workspace_id)
        if "editor" not in roles and "admin" not in roles:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data if isinstance(request.data, dict) else {}

        # ``enabled``: a supplied value wins; an omitted one keeps the stored
        # row (partial semantics) and defaults to True for a workspace with no
        # row yet — so ``PUT {"enabled": false}`` stays byte-identical.
        if "enabled" in data:
            enabled = data["enabled"]
            if not isinstance(enabled, bool):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang, message="Field 'enabled' must be a boolean."
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            stored_enabled = (
                WorkspaceMemorySettings.objects.filter(workspace_id=workspace_id)
                .values_list("enabled", flat=True)
                .first()
            )
            enabled = True if stored_enabled is None else stored_enabled

        # Validate the Q1 payload against the registry BEFORE anything is
        # written, and per field, so a rejection can name the field. This is
        # the same single validation path ``PreferenceService.set_level``
        # uses (the registry's own ``validate_preference_value``), not a
        # second implementation.
        submitted: dict[str, Any] = {}
        for field, key in self._POLICY_FIELDS:
            if field not in data:
                continue
            value = data[field]
            try:
                validate_preference_value(get_preference_key(key), value)
            except ValidationError as exc:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message=str(exc),
                        details=[{"field": field, "message": str(exc)}],
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            submitted[key] = value

        # Pre-write reads only: a failure here happens before anything is
        # committed, so it cannot leave a half-applied request behind. The
        # response is then assembled from these values plus the validated
        # payload — deliberately no preference lookup after the commit.
        state = self._policy_state(ctx, workspace_id)

        # Only fields that actually change are written: a GET→PUT round-trip of
        # the stored workspace level is a genuine no-op (no row, no audit
        # entry), which is what keeps a caller's personal opt-out out of the
        # workspace policy. A ``null`` value means "reset this level" (Q1's
        # documented semantics), so the response falls back to the default.
        stored_disabled_slots = state["stored_disabled_slots"]
        stored_allow_user_opt_out = state["stored_allow_user_opt_out"]
        policy_writes: dict[str, Any] = {}

        if DISABLED_SLOTS_KEY in submitted:
            value = submitted[DISABLED_SLOTS_KEY]
            if value is None:
                policy_writes[DISABLED_SLOTS_KEY] = None
                stored_disabled_slots = []
            else:
                if value != stored_disabled_slots:
                    policy_writes[DISABLED_SLOTS_KEY] = value
                stored_disabled_slots = value

        if ALLOW_USER_OPT_OUT_KEY in submitted:
            value = submitted[ALLOW_USER_OPT_OUT_KEY]
            if value is None:
                policy_writes[ALLOW_USER_OPT_OUT_KEY] = None
                stored_allow_user_opt_out = True
            else:
                if value != stored_allow_user_opt_out:
                    policy_writes[ALLOW_USER_OPT_OUT_KEY] = value
                stored_allow_user_opt_out = value

        try:
            with transaction.atomic():
                if policy_writes:
                    PreferenceService().set_level(
                        ctx,
                        scope="workspace",
                        values=policy_writes,
                        workspace_id=UUID(str(workspace_id)),
                    )
                # Explicit tenant_id (not relying on TenantManager.create()'s
                # auto-inject): update_or_create's create fallback goes through
                # the underlying QuerySet.create(), which bypasses the
                # Manager-level override, so tenant_id must be supplied here
                # directly (same pattern as TenantThemeDefaultView.put's
                # unscoped.update_or_create).
                settings_row, _ = WorkspaceMemorySettings.objects.update_or_create(
                    workspace_id=workspace_id,
                    defaults={"enabled": enabled, "tenant_id": ctx.tenant_id},
                )
        except PermissionDeniedError:
            # The Q1 workspace level is admin-tier (WORKSPACE_CONFIG); an
            # editor keeps the historical ``enabled`` right but not this one.
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            self._payload(
                enabled=settings_row.enabled,
                stored_disabled_slots=stored_disabled_slots,
                stored_allow_user_opt_out=stored_allow_user_opt_out,
                effective_disabled_slots=self._merge_disabled_slots(
                    state["global_disabled_slots"],
                    stored_disabled_slots,
                    state["user_disabled_slots"],
                ),
            )
        )


class SystemMemorySettingsView(APIView):
    """``/api/v1/system/memory-settings/`` — GET System-Admin, PUT superuser.

    GET returns the effective configuration (SystemMemorySettings DB
    override, falling back to env vars per field) plus an
    ``<field>_is_override`` flag per field so the UI can show what deviates
    from the default (Memory Admin UI Phase 3, spec 2026-08-26). PUT applies
    a partial override (Django superuser only, see :func:`_is_superuser`);
    omitted fields are left unchanged, a field sent as ``null`` (or, for the
    free-text fields, as ``""``) clears that field's override back to env.
    A response ``warning``
    (non-null only when embedding_provider/memory_backend actually changed)
    tells the caller existing embeddings were not migrated automatically.

    ``permission_classes``/no ``required_operation`` mirrors
    ``TenantThemeDefaultView``/``GlobalBannerView``'s write side: the default
    ``RbacPermission`` (``rest_api.auth_enforcer``) would deny a pure
    System-Admin outright, because ``active_roles`` resolves to ``()`` for a
    caller with a tenant-wide ``TenantRole`` but no workspace-scoped
    ``UserRole`` (this endpoint targets no workspace). ``HasOperationPermission``
    with no declared operation only requires an authenticated caller, leaving
    the real System-Admin gate to :func:`_is_system_admin` below.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["memory"],
        summary="Read the effective (override-or-env) memory configuration",
        responses={
            200: SystemMemorySettingsResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Tenant-Admin role required."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        effective = MemorySettingsService().get_effective_settings()
        return Response(_with_env_fallback(effective))

    @extend_schema(
        tags=["memory"],
        summary="Apply a partial memory-configuration override",
        request=SystemMemorySettingsWriteSerializer,
        responses={
            200: SystemMemorySettingsResponseSerializer,
            400: OpenApiResponse(description="Invalid override value."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Django superuser required."),
        },
    )
    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_superuser(ctx.user_id):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = SystemMemorySettingsWriteSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = MemorySettingsService().update_settings(
                dict(ser.validated_data), user_id=ctx.user_id
            )
        except BackendSettingsValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=exc.details),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(_with_env_fallback(result))


class SystemMemorySettingsResetView(APIView):
    """``POST /api/v1/system/memory-settings/reset/`` — superuser only.

    Clears every SystemMemorySettings override field back to NULL, so the
    effective configuration falls back entirely to environment variables.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["memory"],
        summary="Clear every memory-configuration override (fall back to env)",
        request=None,
        responses={
            200: SystemMemorySettingsResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Django superuser required."),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_superuser(ctx.user_id):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        result = MemorySettingsService().reset_settings(user_id=ctx.user_id)
        return Response(_with_env_fallback(result))


class SystemMemoryWorkspaceOverviewView(APIView):
    """``GET /api/v1/system/memory/workspaces/`` — System-Admin only.

    Memory Admin UI Phase 1 (spec 2026-08-26). Lists one row per workspace
    in the active tenant: memory enabled/disabled, entry counts per tier,
    last consolidation timestamp. Delegates to :class:`MemoryAdminService`.

    Since issue #1300 the response also carries ``memory_consolidations_total``
    (a per-trigger-source counter of enqueued memory consolidations) and its
    ``consolidation_total`` sum, so an operator can answer "is the memory
    learning loop running, and from which trigger?" on this admin surface
    instead of grepping worker logs. The counter is best-effort
    (:mod:`memory.metrics`); a cache outage yields ``{}``/``0`` rather than an
    error, exactly like the ``degraded`` envelope it rides next to.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["memory"],
        summary="List every workspace's memory overview (System-Admin)",
        responses={
            200: MemoryWorkspaceOverviewResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="System-Admin role required."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            overview = MemoryAdminService().list_workspace_overview(ctx)
        except PermissionDeniedError:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        # MemoryAdminService returns raw uuid.UUID values (see its own
        # UUID-to-UUID comparisons in application/tests/test_memory_admin_
        # service.py) — since this view returns a plain dict (no
        # Serializer/UUIDField doing the to_representation coercion that
        # e.g. StakeholderNeedViewSet gets for free), stringify workspace_id
        # here so response.data matches the actual over-the-wire JSON shape
        # (DRF's JSONRenderer already encodes UUID as str on the real
        # response body; this keeps `response.data` consistent with that
        # for API consumers/tests inspecting it directly).
        for row in overview:
            row["workspace_id"] = str(row["workspace_id"])
        from memory.metrics import consolidation_counts

        counts = consolidation_counts()
        return Response(
            {
                "results": overview,
                # Issue #1300: per-trigger-source consolidation counter.
                "memory_consolidations_total": counts,
                "consolidation_total": sum(counts.values()),
                **envelope(),
            }
        )


class SystemMemoryWorkspaceDeleteView(APIView):
    """``DELETE /api/v1/system/memory/workspaces/<uuid:workspace_id>/``.

    System-Admin only. Deletes BOTH tiers: the workspace's own
    workspace-scoped ``MemoryEntry`` rows and its current members' user-scoped
    rows. See :meth:`MemoryAdminService.delete_workspace_memory`.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["memory"],
        summary="Delete every memory tier of one workspace (System-Admin)",
        responses={
            200: MemoryWorkspaceDeleteResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="System-Admin role required."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def delete(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            result = MemoryAdminService().delete_workspace_memory(ctx, workspace_id)
        except PermissionDeniedError:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({**result, **envelope()})


class _SystemMemoryVisualizationView(APIView):
    """Shared scope/workspace_id query-param parsing for the Phase 5 views.

    Both subclasses are System-Admin gated INSIDE ``MemoryAdminService`` via
    ``_assert_system_admin`` (Phase 5 plan Ruling 3) — deliberately not via
    the older, view-level :func:`_is_system_admin` helper that
    ``SystemMemorySettingsView`` still uses. ``permission_classes`` /
    no ``required_operation`` mirrors ``SystemMemoryWorkspaceOverviewView``:
    the default ``RbacPermission`` would deny a pure System-Admin outright on
    a URL that carries no ``workspace_id`` kwarg.
    """

    permission_classes = [HasOperationPermission]

    @staticmethod
    def _parse_scope_params(request: Request) -> tuple[str, Any]:
        """Return ``(scope, workspace_id)``.

        Raises :class:`ValidationError` for a malformed ``workspace_id``; an
        absent or unknown ``scope`` is left to the service, which owns the
        scope vocabulary and raises the same exception type.
        """
        scope = request.query_params.get("scope", "")
        raw_workspace_id = request.query_params.get("workspace_id") or None
        workspace_id = None
        if raw_workspace_id is not None:
            try:
                workspace_id = UUID(raw_workspace_id)
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValidationError(f"Invalid workspace_id: {raw_workspace_id!r}") from exc
        return scope, workspace_id


class SystemMemoryEntriesListView(_SystemMemoryVisualizationView):
    """``GET /api/v1/system/memory/entries/`` — System-Admin only.

    Memory Admin UI Phase 5 (spec 2026-08-26). Query params: ``scope``
    (``workspace``|``global``), ``workspace_id`` (required for
    ``scope=workspace``), ``page`` (1-indexed), ``page_size``, ``q``
    (case-insensitive substring filter on ``content``). Returns
    ``{results, count, page, page_size}``.
    """

    #: Upper bound on ``page_size`` — this endpoint merges two tiers in
    #: Python, so an unbounded page size would be a trivial memory amplifier.
    MAX_PAGE_SIZE = 200

    @extend_schema(
        tags=["memory"],
        summary="List live memory entries across both team-owned tiers (System-Admin)",
        parameters=[
            OpenApiParameter(
                "scope",
                type=str,
                location=OpenApiParameter.QUERY,
                description="'workspace' or 'global'.",
            ),
            OpenApiParameter(
                "workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Required when scope=workspace.",
            ),
            OpenApiParameter(
                "page", type=int, location=OpenApiParameter.QUERY, default=1
            ),
            OpenApiParameter(
                "page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                default=25,
                description=(
                    "Page size; the view clamps it to its own MAX_PAGE_SIZE "
                    "upper bound."
                ),
            ),
            OpenApiParameter(
                "q",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Case-insensitive substring filter on content.",
            ),
        ],
        responses={
            200: MemoryAdminEntryListResponseSerializer,
            400: OpenApiResponse(description="Invalid scope/workspace_id/page parameters."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="System-Admin role required."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            scope, workspace_id = self._parse_scope_params(request)
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 25))
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (TypeError, ValueError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="page and page_size must be integers."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        page = max(1, page)
        page_size = max(1, min(page_size, self.MAX_PAGE_SIZE))
        q = (request.query_params.get("q") or "").strip() or None

        try:
            result = MemoryAdminService().list_entries(
                ctx, scope=scope, workspace_id=workspace_id, page=page, page_size=page_size, q=q
            )
        except PermissionDeniedError:            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({**result, **envelope()})

    @extend_schema(
        tags=["memory"],
        summary="Create one memory entry (System-Admin, any scope)",
        request=MemoryEntryWriteSerializer,
        responses={
            201: MemoryEntryViewSerializer,
            400: OpenApiResponse(description="Invalid scope or target."),
            403: OpenApiResponse(description="System-Admin role required."),
            429: OpenApiResponse(description="memory.write rate limit exceeded."),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """System-Admin write on the entries collection (issue #1291).

        Same body contract, same service, same ``MemoryPolicy`` and same rate
        limiter as ``POST /api/v1/memory/entries/``; this URL simply adds the
        System-Admin gate its sibling read uses. The admin gate can only
        NARROW, never widen: for ``scope="workspace"``/``"artifact"`` the
        service still requires Editor+ in the owning workspace, so a
        tenant-admin who is not a member of that workspace is denied -- exactly
        the "same permission check as ``memory.write``" rule.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = MemoryEntryWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            view = MemoryEntryService().write(
                ctx,
                content=ser.validated_data["content"],
                scope=ser.validated_data["scope"],
                workspace_id=ser.validated_data.get("workspace_id"),
                artifact_id=ser.validated_data.get("artifact_id"),
                confidence=ser.validated_data.get("confidence", 1.0),
                change_reason=ser.validated_data.get("change_reason"),
            )
        except (
            PermissionDeniedError,
            NotFoundError,
            ValidationError,
            MemoryWriteRateLimitExceeded,
        ) as exc:
            return _memory_error_response(exc, lang)
        return Response(view, status=status.HTTP_201_CREATED)


class SystemMemoryProjectionView(_SystemMemoryVisualizationView):
    """``GET /api/v1/system/memory/projection/`` — System-Admin only.

    Memory Admin UI Phase 5 (spec 2026-08-26). Query params: ``scope``
    (``workspace``|``global``), ``workspace_id`` (required for
    ``scope=workspace``). Returns ``{points, sampled, sample_size,
    total_size, excluded_no_embedding}``; the heavy numeric work (PCA +
    clustering) happens in the service and is Redis-cached there.
    """

    @extend_schema(
        tags=["memory"],
        summary="2D PCA projection + clusters of the scoped memory (System-Admin)",
        parameters=[
            OpenApiParameter(
                "scope",
                type=str,
                location=OpenApiParameter.QUERY,
                description="'workspace' or 'global'.",
            ),
            OpenApiParameter(
                "workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Required when scope=workspace.",
            ),
        ],
        responses={
            200: MemoryProjectionResponseSerializer,
            400: OpenApiResponse(description="Invalid scope/workspace_id parameters."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="System-Admin role required."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            scope, workspace_id = self._parse_scope_params(request)
            result = MemoryAdminService().get_projection(
                ctx, scope=scope, workspace_id=workspace_id
            )
        except PermissionDeniedError:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({**result, **envelope()})


class WorkspaceMemoryEntriesView(APIView):
    """``/api/v1/workspaces/<uuid:workspace_id>/memory/entries/``.

    GET: any workspace member lists the workspace's live entries (default
    ``scope=workspace``; ``scope=artifact`` needs ``artifact_id``). POST: Editor+
    creates a workspace-scoped fact. DELETE (issue #1291): Workspace-Admin purges
    the whole workspace scope. All delegate to
    :class:`application.memory_entry_service.MemoryEntryService`, so the
    response always carries ``backend`` + ``degraded`` (F9).
    """

    @extend_schema(
        tags=["memory"],
        summary="List the workspace's live memory entries",
        parameters=[
            OpenApiParameter(
                "scope",
                type=str,
                location=OpenApiParameter.QUERY,
                description=(
                    "Optional scope; defaults to 'workspace' because the URL "
                    "always carries a workspace_id."
                ),
            ),
            OpenApiParameter(
                "artifact_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Required for scope=artifact.",
            ),
            OpenApiParameter(
                "contributor_user_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Admin-only contributor filter.",
            ),
            OpenApiParameter(
                "page", type=int, location=OpenApiParameter.QUERY, default=1
            ),
            OpenApiParameter(
                "page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                default=25,
                description=f"Clamped to 1..{MEMORY_MAX_PAGE_SIZE}.",
            ),
            OpenApiParameter(
                "q",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Case-insensitive substring filter on content.",
            ),
        ],
        responses={
            200: MemoryEntryListResponseSerializer,
            400: OpenApiResponse(description="Invalid query parameter."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Permission denied for the scope."),
            404: OpenApiResponse(description="Workspace or artifact not found."),
        },
    )
    def get(self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            artifact_id = _parse_uuid_param(request.query_params.get("artifact_id"), "artifact_id")
            contributor_user_id = _parse_uuid_param(
                request.query_params.get("contributor_user_id"), "contributor_user_id"
            )
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 25))
        except (ValidationError, TypeError, ValueError) as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        scope = request.query_params.get("scope") or None
        # #1248: no explicit scope -> the service defaults to "workspace"
        # because this URL always carries a workspace_id (see
        # MemoryEntryService._default_scope's scope matrix). An
        # interview.chat-extracted workspace fact is therefore reachable here
        # with the same workspace_id, mirroring the MCP ``memory.list`` read.
        q = (request.query_params.get("q") or "").strip() or None
        try:
            result = MemoryEntryService().list(
                ctx,
                workspace_id=workspace_id,
                scope=scope,
                artifact_id=artifact_id,
                contributor_user_id=contributor_user_id,
                q=q,
                page=page,
                page_size=page_size,
            )
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response(result)

    @extend_schema(
        tags=["memory"],
        summary="Create a workspace-scoped memory entry",
        request=MemoryEntryContentSerializer,
        responses={
            201: MemoryEntryViewSerializer,
            400: OpenApiResponse(
                description="Empty content, or a 'scope' other than 'workspace'."
            ),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Editor role required in the workspace."),
            429: OpenApiResponse(description="memory.write rate limit exceeded."),
        },
    )
    def post(self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        # Issue #1291: the URL pins the scope. A body that names a different
        # one would otherwise be silently ignored -- a caller could believe
        # they wrote personal/artifact memory here. Fail closed instead; the
        # scope-parameterised write lives on ``/api/v1/memory/entries/``.
        requested_scope = request.data.get("scope")
        if requested_scope not in (None, "", MemoryEntry.SCOPE_WORKSPACE):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=(
                        "This endpoint always writes workspace scope; omit "
                        "'scope' or use POST /api/v1/memory/entries/ for "
                        "'user'/'artifact'."
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        content = request.data.get("content")
        try:
            view = MemoryEntryService().write(
                ctx,
                content=content,
                scope=MemoryEntry.SCOPE_WORKSPACE,
                workspace_id=workspace_id,
                confidence=request.data.get("confidence", 1.0),
                change_reason=request.data.get("change_reason"),
            )
        except (PermissionDeniedError, NotFoundError, ValidationError, MemoryWriteRateLimitExceeded) as exc:
            return _memory_error_response(exc, lang)
        return Response(view, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["memory"],
        summary="Purge every workspace-scoped memory entry",
        responses={
            200: MemoryScopePurgeResponseSerializer,
            403: OpenApiResponse(description="Workspace-Admin role required."),
        },
    )
    def delete(self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any) -> Response:
        """Delete the whole ``scope="workspace"`` slice (issue #1291).

        Requires Workspace-Admin (``MemoryPolicy.can_delete_scope``); a
        Viewer/Editor is denied. Deletes are not charged to the ``memory.write``
        limiter (that quota guards the embedding budget, and a delete embeds
        nothing) -- the same rule MCP ``memory.forget`` follows.
        """
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        change_reason = request.query_params.get("change_reason") or request.data.get(
            "change_reason"
        )
        try:
            removed = MemoryEntryService().delete_scope(
                ctx,
                scope=MemoryEntry.SCOPE_WORKSPACE,
                workspace_id=workspace_id,
                change_reason=change_reason,
            )
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response({"deleted": removed, **envelope()})


class WorkspaceMemoryDigestView(APIView):
    """``/api/v1/workspaces/<uuid:workspace_id>/memory/digest/``.

    GET: any workspace member reads the consolidated digest of the workspace's
    memory (``scope="workspace"``). Delegates to
    :class:`application.memory_entry_service.MemoryEntryService`; the body is
    the digest's own fields (``digest``/``generated_at``/``backend``/
    ``degraded`` + the AP-B5.1 derivation pair ``derivation_status``/
    ``derived_count``), so F9's degradation signal is carried by the digest
    itself rather than by a second health probe.
    """

    @extend_schema(
        tags=["memory"],
        summary="Read the workspace's consolidated memory digest",
        responses={
            200: MemoryDigestResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Permission denied for the workspace."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def get(self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            digest = MemoryEntryService().digest(ctx, workspace_id=workspace_id)
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response(
            {
                "digest": digest.text,
                "generated_at": digest.generated_at.isoformat(),
                "backend": digest.backend,
                "degraded": digest.degraded,
                "derivation_status": digest.derivation_status,
                "derived_count": digest.derived_count,
            }
        )


class WorkspaceMemorySearchView(APIView):
    """``/api/v1/workspaces/<uuid:workspace_id>/memory/search/``.

    GET: semantic search. Query params: ``q`` (required), ``scope`` (single) or
    ``scopes`` (comma-separated), ``source`` (``facts``/``derived``/``all``),
    ``artifact_id``, ``top_k``. Any workspace member may read; the service
    applies the full ``MemoryPolicy`` matrix.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "q",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Natural-language search query (must be non-blank).",
            ),
            OpenApiParameter(
                "scope",
                type=str,
                location=OpenApiParameter.QUERY,
                enum=list(VALID_SCOPES),
                description="A single scope to search.",
            ),
            OpenApiParameter(
                "scopes",
                type=str,
                location=OpenApiParameter.QUERY,
                description=(
                    "Comma-separated list of scopes; takes precedence over "
                    "``scope``."
                ),
            ),
            OpenApiParameter(
                "artifact_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Optional artifact UUID that aims the search at that artifact.",
            ),
            OpenApiParameter(
                "top_k",
                type=int,
                location=OpenApiParameter.QUERY,
                default=5,
                description=(
                    f"Maximum number of hits (clamped to 1..{MEMORY_MAX_PAGE_SIZE})."
                ),
            ),
            OpenApiParameter(
                "source",
                type=str,
                location=OpenApiParameter.QUERY,
                enum=list(VALID_QUERY_SOURCES),
                default="facts",
                description=(
                    "What to search. 'facts' (default) reads the backend's "
                    "stored/derived conclusions, 'derived' its message-level "
                    "(raw messages) recall, 'all' both. On a backend "
                    "without a second recall surface (pgvector, qdrant) "
                    "'derived'/'all' answer an empty list with "
                    "degraded=true, detail=\"unsupported\"."
                ),
            ),
        ],
        responses={200: MemorySearchResponseSerializer},
    )
    def get(self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        query = (request.query_params.get("q") or "").strip()
        raw_scopes = request.query_params.get("scopes")
        scopes: Any
        if raw_scopes:
            scopes = [part.strip() for part in raw_scopes.split(",") if part.strip()]
        else:
            scopes = request.query_params.get("scope") or None
        try:
            artifact_id = _parse_uuid_param(request.query_params.get("artifact_id"), "artifact_id")
            top_k = int(request.query_params.get("top_k", 5))
        except (ValidationError, TypeError, ValueError) as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = MemoryEntryService().search(
                ctx,
                query=query,
                scopes=scopes,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                top_k=top_k,
                source=request.query_params.get("source") or "facts",
            )
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response(result)


class WorkspaceMemoryAskView(APIView):
    """``POST /api/v1/workspaces/<uuid:workspace_id>/memory/ask/``.

    AP-B5.2 (#1155 Aspekt 1): the REST mirror of the MCP ``memory.ask`` tool
    (:meth:`mcp_server.tools.memory.MemoryToolGroup._handle_ask`) -- a
    natural-language question answered by the active backend's dialectic
    surface (Honcho ``peer.chat``; pgvector has none and degrades honestly,
    F9). Delegates to :meth:`application.memory_entry_service.
    MemoryEntryService.ask`; nothing is re-implemented here, so both
    transports share one validation, one policy and one answer shape.

    Request body: ``query`` (required, non-blank, <= ``MAX_ASK_QUERY_CHARS``),
    ``artifact_id`` (optional UUID -- aims the question at the artifact scope
    instead of the workspace scope), ``reasoning_level`` (optional, one of
    ``memory.backends.VALID_REASONING_LEVELS``). All three are validated by
    the service -- a missing/blank query or an unknown level answers
    ``VALIDATION_ERROR``/400 before any backend call; only the
    ``artifact_id`` UUID shape is parsed here (same helper as the entries/
    search views).

    Response mirrors the MCP payload exactly: ``answer``/``generated_at``
    (ISO-8601)/``backend``/``degraded``/``detail``. ``detail`` carries the
    degradation cause (``engine_error:<Class>`` / ``unknown_scope:<Class>`` /
    ``"no dialectic engine"``, never user data), so an outage stays
    distinguishable from "nothing known" (F9). ``derivation_status`` does
    NOT ride along: ``MemoryAnswer`` carries no such field (it is a
    :class:`MemoryDigest`-only signal) and the MCP tool does not emit one --
    inventing a second read just to fill a REST-only key would break the
    mirror.

    Authorization is the WRITE gate, identical to MCP ``memory.ask`` (a
    ``_WRITE_TOOL_PREFIXES`` tool) and to this module's ``memory.write``
    surfaces: the default ``RbacPermission`` maps POST to ``Operation.WRITE``
    and fails closed, so a Viewer-role member is denied 403 before this
    handler runs, and the API-key capability tier denies a ``read_only`` key
    independently of RBAC. Inside the service the scope matrix
    (``MemoryPolicy``) additionally fences the workspace/artifact scope.

    The ``memory.write`` rate limit (:mod:`memory.ratelimit`, RFC #1002 PR B)
    deliberately does NOT apply here: its counter and admin knob are a
    WRITES-per-hour quota (``mem:write:rl:*``,
    ``MEMORY_WRITE_RATE_LIMIT_PER_HOUR``) guarding the persistence +
    embedding budget, while ``ask`` stores nothing; charging ask calls to
    that counter would silently re-define an admin-configured knob AND let
    question-asking starve legitimate writes. The canonical MCP path enforces
    no such limit either, and a limit only on REST would be both asymmetric
    across transports and trivially bypassed through the other one. Cost of
    the LLM-invoking call is bounded instead by the WRITE gate, the transport
    throttles and ``MEMORY_ASK_TIMEOUT``. A dedicated ask quota, if ever
    wanted, belongs in ``MemoryEntryService.ask`` so both transports inherit
    it -- out of scope here.
    """

    @extend_schema(
        tags=["memory"],
        summary="Ask a natural-language question against the workspace's memory",
        request=MemoryAskRequestSerializer,
        responses={
            200: MemoryAnswerResponseSerializer,
            400: OpenApiResponse(description="Missing/blank query or unknown reasoning level."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Write role required in the workspace."),
            404: OpenApiResponse(description="Workspace or artifact not found."),
        },
    )
    def post(self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            artifact_id = _parse_uuid_param(request.data.get("artifact_id"), "artifact_id")
            answer = MemoryEntryService().ask(
                ctx,
                query=request.data.get("query"),
                workspace_id=workspace_id,
                artifact_id=artifact_id,
                reasoning_level=request.data.get("reasoning_level"),
            )
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response(
            {
                "answer": answer.text,
                "generated_at": answer.generated_at.isoformat(),
                "backend": answer.backend,
                "degraded": answer.degraded,
                "detail": answer.detail,
            }
        )


class MemoryEntryDetailView(APIView):
    """``/api/v1/memory/entries/<str:entry_id>/`` — GET / PATCH / DELETE.

    No workspace in the URL, so the coarse RbacPermission is deliberately
    replaced by :class:`HasOperationPermission` (any authenticated caller) and
    the real gate is ``MemoryPolicy`` on the resolved entry — a self-service
    user with no workspace role can still read/edit/delete their OWN memory.

    PATCH (issue #1291) rewrites the content history-preservingly; see
    :meth:`patch`.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["memory"],
        summary="Read one memory entry",
        responses={
            200: MemoryEntryViewSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Permission denied for the entry."),
            404: OpenApiResponse(description="Entry not found."),
        },
    )
    def get(self, request: Request, entry_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            view = MemoryEntryService().get(ctx, entry_id=entry_id)
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response(view)

    @extend_schema(
        tags=["memory"],
        summary="Delete one memory entry",
        parameters=[
            OpenApiParameter(
                "change_reason",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Optional audit reason (a body 'change_reason' also works).",
            ),
        ],
        responses={
            200: MemoryEntryForgetResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Permission denied for the entry."),
            404: OpenApiResponse(description="Entry not found."),
        },
    )
    def delete(self, request: Request, entry_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        change_reason = request.query_params.get("change_reason") or request.data.get(
            "change_reason"
        )
        try:
            MemoryEntryService().forget(ctx, entry_id=entry_id, change_reason=change_reason)
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response({"deleted": True, **envelope()})

    @extend_schema(
        tags=["memory"],
        summary="Replace one memory entry's content (history-preserving)",
        request=MemoryEntryContentSerializer,
        responses={
            200: MemoryEntryViewSerializer,
            400: OpenApiResponse(description="Empty content or invalid body."),
            403: OpenApiResponse(description="Permission denied for the entry."),
            404: OpenApiResponse(description="Entry not found."),
            429: OpenApiResponse(description="memory.write rate limit exceeded."),
        },
    )
    def patch(self, request: Request, entry_id: str, *args: Any, **kwargs: Any) -> Response:
        """Rewrite one entry's content without losing the old row.

        Delegates to :meth:`MemoryEntryService.update`, which writes the
        corrected content as a NEW entry and marks the edited row
        ``superseded_by`` it. The scope/owner come from the stored row, never
        the body, so a PATCH can never move a fact between scopes.
        """
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        ser = MemoryEntryContentSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            view = MemoryEntryService().update(
                ctx,
                entry_id=entry_id,
                content=ser.validated_data["content"],
                confidence=ser.validated_data.get("confidence"),
                change_reason=ser.validated_data.get("change_reason"),
            )
        except (
            PermissionDeniedError,
            NotFoundError,
            ValidationError,
            MemoryWriteRateLimitExceeded,
        ) as exc:
            return _memory_error_response(exc, lang)
        return Response(view)


class MemoryEntryPromoteView(APIView):
    """``/api/v1/memory/entries/<str:entry_id>/promote/`` — user -> workspace.

    Editor+ in the target workspace is required (enforced by ``MemoryPolicy``
    inside the service). The target workspace is the body's ``workspace_id`` or
    the active request workspace.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["memory"],
        summary="Promote the caller's own memory entry into a workspace",
        request=MemoryEntryPromoteRequestSerializer,
        responses={
            200: MemoryEntryViewSerializer,
            400: OpenApiResponse(description="Invalid target scope or workspace."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Editor role required in the target workspace."),
            404: OpenApiResponse(description="Entry not found."),
            429: OpenApiResponse(description="memory.write rate limit exceeded."),
        },
    )
    def post(self, request: Request, entry_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            workspace_id = _parse_uuid_param(request.data.get("workspace_id"), "workspace_id")
            view = MemoryEntryService().promote(
                ctx,
                entry_id=entry_id,
                target_scope=request.data.get("target_scope", "workspace"),
                workspace_id=workspace_id,
                change_reason=request.data.get("change_reason"),
            )
        except (PermissionDeniedError, NotFoundError, ValidationError, MemoryWriteRateLimitExceeded) as exc:
            return _memory_error_response(exc, lang)
        return Response(view)


class ArtifactMemoryView(APIView):
    """``/api/v1/artifacts/<uuid:artifact_id>/memory/`` — GET / POST.

    Artifact-scoped memory. GET: any active role in the artifact's workspace.
    POST: Editor+ in the artifact's workspace. The service resolves the
    artifact's workspace and applies the matrix.
    """

    @extend_schema(
        tags=["memory"],
        summary="List the artifact's live memory entries",
        parameters=[
            OpenApiParameter(
                "page", type=int, location=OpenApiParameter.QUERY, default=1
            ),
            OpenApiParameter(
                "page_size", type=int, location=OpenApiParameter.QUERY, default=25
            ),
            OpenApiParameter(
                "q",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Case-insensitive substring filter on content.",
            ),
        ],
        responses={
            200: MemoryEntryListResponseSerializer,
            400: OpenApiResponse(description="page/page_size are not integers."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="No active role in the artifact's workspace."),
            404: OpenApiResponse(description="Artifact not found."),
        },
    )
    def get(self, request: Request, artifact_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 25))
        except (TypeError, ValueError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="page and page_size must be integers."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        q = (request.query_params.get("q") or "").strip() or None
        try:
            result = MemoryEntryService().list(
                ctx,
                scope=MemoryEntry.SCOPE_ARTIFACT,
                artifact_id=artifact_id,
                q=q,
                page=page,
                page_size=page_size,
            )
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response(result)

    @extend_schema(
        tags=["memory"],
        summary="Create an artifact-scoped memory entry",
        request=MemoryEntryContentSerializer,
        responses={
            201: MemoryEntryViewSerializer,
            400: OpenApiResponse(
                description="Empty content, or a 'scope' other than 'artifact'."
            ),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Editor role required in the artifact's workspace."),
            404: OpenApiResponse(description="Artifact not found."),
            429: OpenApiResponse(description="memory.write rate limit exceeded."),
        },
    )
    def post(self, request: Request, artifact_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        # Issue #1291: the URL pins scope="artifact"; a conflicting body scope
        # is rejected rather than silently ignored (see the workspace sibling).
        requested_scope = request.data.get("scope")
        if requested_scope not in (None, "", MemoryEntry.SCOPE_ARTIFACT):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=(
                        "This endpoint always writes artifact scope; omit "
                        "'scope' or use POST /api/v1/memory/entries/ for "
                        "'user'/'workspace'."
                    ),
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            view = MemoryEntryService().write(
                ctx,
                content=request.data.get("content"),
                scope=MemoryEntry.SCOPE_ARTIFACT,
                artifact_id=artifact_id,
                confidence=request.data.get("confidence", 1.0),
                change_reason=request.data.get("change_reason"),
            )
        except (PermissionDeniedError, NotFoundError, ValidationError, MemoryWriteRateLimitExceeded) as exc:
            return _memory_error_response(exc, lang)
        return Response(view, status=status.HTTP_201_CREATED)


class ArtifactMemoryDigestView(APIView):
    """``/api/v1/artifacts/<uuid:artifact_id>/memory/digest/``.

    GET: any active role in the artifact's workspace reads the consolidated
    artifact-scoped digest. The service resolves the artifact's owning
    workspace and applies ``MemoryPolicy``, so a caller cannot aim a digest at
    an artifact of a workspace they have no role in.
    """

    @extend_schema(
        tags=["memory"],
        summary="Read the artifact's consolidated memory digest",
        responses={
            200: MemoryDigestResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="No active role in the artifact's workspace."),
            404: OpenApiResponse(description="Artifact not found."),
        },
    )
    def get(self, request: Request, artifact_id: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            digest = MemoryEntryService().digest(
                ctx, workspace_id=None, artifact_id=artifact_id
            )
        except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
            return _memory_error_response(exc, lang)
        return Response(
            {
                "digest": digest.text,
                "generated_at": digest.generated_at.isoformat(),
                "backend": digest.backend,
                "degraded": digest.degraded,
                "derivation_status": digest.derivation_status,
                "derived_count": digest.derived_count,
            }
        )


class SystemMemoryEntriesExportView(_SystemMemoryVisualizationView):
    """``GET /api/v1/system/memory/entries/export/`` — System-Admin only.

    DSGVO Auskunftsanspruch: exports the tenant's live memory entries as JSON
    (default) or CSV (``?format=csv``). Delegates to
    :class:`MemoryAdminService.list_entries` (backend-agnostic), capped at
    :data:`EXPORT_MAX_ROWS`.

    ``?format=`` is consumed by this view itself (as the export format) rather
    than by DRF's content negotiation — which is why
    :meth:`perform_content_negotiation` is overridden to ignore it. Without the
    override DRF's ``URL_FORMAT_OVERRIDE`` would look for a ``csv`` renderer,
    find none, and answer 404 before the handler ever runs.
    """

    def perform_content_negotiation(self, request: Request, force: bool = False):
        """Always negotiate the default renderer; ``?format=`` is ours."""
        renderers = self.get_renderers()
        return renderers[0], renderers[0].media_type

    @extend_schema(
        tags=["memory"],
        summary="Export the tenant's live memory entries (JSON or CSV)",
        description=(
            "DSGVO Auskunftsanspruch. Two media types, selected by "
            "``?format=``: the default ``json`` answers the structured "
            "document, ``csv`` streams a downloadable CSV file. They are "
            "deliberately published as two separate 200 responses (#1388) — "
            "folding them into one JSON schema would describe neither body."
        ),
        parameters=[
            OpenApiParameter(
                "format",
                type=str,
                location=OpenApiParameter.QUERY,
                enum=["json", "csv"],
                default="json",
                description="Export format.",
            ),
        ],
        responses={
            (200, "application/json"): MemoryEntryExportResponseSerializer,
            (200, "text/csv"): OpenApiTypes.BINARY,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="System-Admin role required."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = _auth_or_401(request, lang)
        if isinstance(ctx, Response):
            return ctx
        try:
            result = MemoryAdminService().list_entries(
                ctx, scope="global", page=1, page_size=EXPORT_MAX_ROWS
            )
        except PermissionDeniedError as exc:
            return _memory_error_response(exc, lang)
        rows = result["results"]
        export_format = (request.query_params.get("format") or "json").lower()
        if export_format == "csv":
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="memory-entries.csv"'
            writer = csv.writer(response)
            writer.writerow(
                ["id", "content", "owner_type", "owner_id", "owner_label", "created_at", "confidence"]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["id"],
                        row["content"],
                        row["owner_type"],
                        row["owner_id"],
                        row["owner_label"],
                        row["created_at"].isoformat() if row["created_at"] else "",
                        row["confidence"],
                    ]
                )
            return response
        return Response(
            {
                "entries": rows,
                "count": result["count"],
                "truncated": result["count"] > len(rows),
                **envelope(),
            }
        )


class MemorySelfServiceSettingsView(APIView):
    """``/api/v1/memory/me/settings/`` — the caller's own memory switches.

    Plan A T-A1-4 (ENT-A5 = A, ENT-A7 = B). Self-service over the caller's own
    Q1 **user** level only: there is no ``user_id`` parameter, so a foreign
    write is impossible by construction — ``ctx.user_id`` is the whole
    boundary. No admin gate (same ``HasOperationPermission`` pattern as
    :class:`MemorySelfServiceView`).

    The business logic lives in :mod:`memory.user_settings` (a thin facade over
    :class:`application.preference_service.PreferenceService`); this class only
    does transport work — auth guard, the workspace-membership answer and the
    error envelope.

    GET: ``{"enabled": bool, "disabled_slots": [str, ...]}`` — the *stored*
    user level (defaults ``true`` / ``[]``). With ``?workspace_id=<uuid>`` the
    payload additionally carries
    ``"effective": {"workspace_id": ..., "opt_out_allowed": bool}``: the
    workspace-level ``memory.allow_user_opt_out`` value, i.e. whether the
    personal switch is honoured there. A caller without a role in that
    workspace gets **404** (QR-S21) — never 403, so the route discloses neither
    the workspace's existence nor its policy.
    PUT: partial write of the caller's own level (``null`` resets), answered
    with the same ``{enabled, disabled_slots}`` shape. ``enabled=false`` is
    stored even when the workspace forbids the opt-out (ENT-A7 = B);
    ``effective.opt_out_allowed=false`` is how that workspace says it does not
    apply. ``?workspace_id=`` is a GET-only display aid: a PUT writes no
    workspace state, so it answers no workspace policy (and therefore needs no
    membership check).
    """

    permission_classes = [HasOperationPermission]

    @staticmethod
    def _is_member(ctx: Any, workspace_id: UUID) -> bool:
        """Whether the caller holds any (non-suspended) role in *workspace_id*.

        Every role in the RBAC matrix grants READ, so "any role" is exactly the
        READ permission this endpoint needs — and it stays one query. A
        non-existent workspace answers ``False`` for the same reason a foreign
        one does, which is what keeps the 404 non-disclosing.
        """
        return bool(
            AuthorizationService().active_roles_for(
                user_id=ctx.user_id, workspace_id=workspace_id
            )
        )

    @extend_schema(
        tags=["memory"],
        summary="Read the caller's own memory switches",
        parameters=[
            OpenApiParameter(
                "workspace_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Optional workspace whose opt-out policy is reported in "
                    "``effective``. The caller needs a role there; a foreign or "
                    "unknown workspace is answered with 404 (no disclosure)."
                ),
            ),
        ],
        responses={
            200: MemorySelfServiceSettingsResponseSerializer,
            400: OpenApiResponse(description="workspace_id is not a UUID."),
            401: OpenApiResponse(description="No valid credential."),
            404: OpenApiResponse(
                description="The caller has no role in the requested workspace."
            ),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            workspace_id = _parse_uuid_param(
                request.query_params.get("workspace_id"), "workspace_id"
            )
        except ValidationError as exc:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=str(exc),
                    details=[{"field": "workspace_id", "message": str(exc)}],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if workspace_id is not None and not self._is_member(ctx, workspace_id):
            # QR-S21: a 403 would confirm the workspace exists and that it has
            # a policy to hide. Both are answered as "not found".
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            read_user_settings(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                workspace_id=workspace_id,
            )
        )

    @extend_schema(
        tags=["memory"],
        summary="Update the caller's own memory switches",
        request=MemorySelfServiceSettingsWriteSerializer,
        responses={
            200: MemorySelfServiceSettingsResponseSerializer,
            400: OpenApiResponse(
                description=(
                    "'enabled' is not a boolean, or 'disabled_slots' names an "
                    "unknown or hard-off slot."
                )
            ),
            401: OpenApiResponse(description="No valid credential."),
        },
    )
    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        data = request.data if isinstance(request.data, dict) else {}
        try:
            payload = write_user_settings(ctx, payload=data)
        except MemoryUserSettingRejected as exc:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=str(exc),
                    details=[{"field": exc.field, "message": str(exc)}],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload)


class MemorySelfServiceView(APIView):
    """``/api/v1/memory/me/`` — any authenticated user, no role required.

    Memory Admin UI Phase 4 (spec 2026-08-26). Self-service over the
    caller's OWN ``scope="user"`` ``MemoryEntry`` rows only — never
    workspace-scoped memory, which is team-owned (see plan Ruling 1). No admin
    gate: the ``user_id``
    filter on every query IS the authorization boundary, mirroring
    ``ApiKeyViewSet``'s own-data-only self-service pattern.

    GET: ``{"entry_count": int, "last_updated_at": str | None}``.
    DELETE: deletes all of the caller's user-scoped ``MemoryEntry`` rows, returns
    ``{"deleted": int}`` — 200 even when nothing existed to delete.
    POST (issue #1291): create a ``scope="user"`` fact for the caller. This is
    the REST write path for the personal scope — before it, a user fact could
    only be created over MCP ``memory.write``. The write goes through
    :meth:`MemoryEntryService.write` exactly like the MCP tool, so the
    ``MemoryPolicy`` write matrix (any authenticated caller writes own) and the
    ``memory.write`` rate limiter apply unchanged. ``scope`` is deliberately
    NOT read from the body: this endpoint is the personal scope by definition,
    and the scope-parameterised writes live on the workspace/artifact entry
    endpoints and (for admins) ``/api/v1/system/memory/entries/``.
    """

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["memory"],
        summary="Read the caller's own (scope=user) memory aggregate",
        parameters=[
            OpenApiParameter(
                "include_entries",
                type=bool,
                location=OpenApiParameter.QUERY,
                default=False,
                description="Also return the caller's own entry list + page metadata.",
            ),
            OpenApiParameter(
                "page", type=int, location=OpenApiParameter.QUERY, default=1
            ),
            OpenApiParameter(
                "page_size", type=int, location=OpenApiParameter.QUERY, default=25
            ),
        ],
        responses={
            200: MemorySelfServiceResponseSerializer,
            400: OpenApiResponse(description="page/page_size are not integers."),
            401: OpenApiResponse(description="No valid credential."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        agg = MemoryEntry.objects.filter(
            scope=MemoryEntry.SCOPE_USER, user_id=ctx.user_id
        ).aggregate(count=Count("id"), last=Max("created_at"))
        payload: dict[str, Any] = {
            "entry_count": agg["count"] or 0,
            "last_updated_at": agg["last"],
            **envelope(),
        }
        # RFC #1002 PR B: ``include_entries=true`` additionally returns the
        # caller's own user-scoped entries (the id filter IS the authorization
        # boundary — see the class docstring).
        if str(request.query_params.get("include_entries", "")).lower() in ("1", "true", "yes"):
            try:
                page = int(request.query_params.get("page", 1))
                page_size = int(request.query_params.get("page_size", 25))
            except (TypeError, ValueError):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang, message="page and page_size must be integers."
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                page_result = MemoryEntryService().list(
                    ctx, scope=MemoryEntry.SCOPE_USER, page=page, page_size=page_size
                )
            except (PermissionDeniedError, NotFoundError, ValidationError) as exc:
                return _memory_error_response(exc, lang)
            payload["entries"] = page_result["items"]
            payload["total"] = page_result["total"]
            payload["page"] = page_result["page"]
            payload["page_size"] = page_result["page_size"]
        return Response(payload)

    @extend_schema(
        tags=["memory"],
        summary="Delete every personal (scope=user) memory entry of the caller",
        responses={
            200: MemorySelfServiceDeleteResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
        },
    )
    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        deleted, _ = MemoryEntry.objects.filter(
            scope=MemoryEntry.SCOPE_USER, user_id=ctx.user_id
        ).delete()
        return Response({"deleted": deleted, **envelope()})

    @extend_schema(
        tags=["memory"],
        summary="Create a personal (scope=user) memory entry for the caller",
        request=MemoryEntryContentSerializer,
        responses={
            201: MemoryEntryViewSerializer,
            400: OpenApiResponse(description="Empty content or invalid body."),
            429: OpenApiResponse(description="memory.write rate limit exceeded."),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Write a personal fact for the caller (issue #1291).

        The REST write path for ``scope="user"`` memory: delegates to
        :meth:`MemoryEntryService.write` with ``scope="user"``, so the
        ``MemoryPolicy`` write matrix (any authenticated caller writes their
        own) and the ``memory.write`` rate limiter apply exactly as they do for
        the MCP ``memory.write`` tool.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        ser = MemoryEntryContentSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        confidence = ser.validated_data.get("confidence")
        try:
            view = MemoryEntryService().write(
                ctx,
                content=ser.validated_data["content"],
                scope=MemoryEntry.SCOPE_USER,
                confidence=1.0 if confidence is None else confidence,
                change_reason=ser.validated_data.get("change_reason"),
            )
        except (
            PermissionDeniedError,
            NotFoundError,
            ValidationError,
            MemoryWriteRateLimitExceeded,
        ) as exc:
            return _memory_error_response(exc, lang)
        return Response(view, status=status.HTTP_201_CREATED)


__all__ = [
    "EXPORT_MAX_ROWS",
    "ArtifactMemoryDigestView",
    "ArtifactMemoryView",
    "MemoryEntryDetailView",
    "MemoryEntryPromoteView",
    "MemorySelfServiceSettingsView",
    "MemorySelfServiceView",
    "SystemMemoryEntriesExportView",
    "SystemMemoryEntriesListView",
    "SystemMemoryProjectionView",
    "SystemMemorySettingsResetView",
    "SystemMemorySettingsView",
    "SystemMemoryWorkspaceDeleteView",
    "SystemMemoryWorkspaceOverviewView",
    "WorkspaceMemoryAskView",
    "WorkspaceMemoryDigestView",
    "WorkspaceMemoryEntriesView",
    "WorkspaceMemorySearchView",
    "WorkspaceMemorySettingsView",
]
