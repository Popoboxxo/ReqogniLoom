"""OpenAPI shapes for the memory endpoints typed for #1388.

The memory views return dicts assembled by
:class:`application.memory_entry_service.MemoryEntryService`,
:class:`application.memory_admin_service.MemoryAdminService`,
:class:`application.memory_settings_service.MemorySettingsService` and
:func:`memory.health.envelope`. The serializers below transcribe those shapes
for the generated contract only; the runtime code keeps returning the
services' dicts unchanged — nothing here is ever instantiated on a request
path.

Two invariants this module must respect:

* **It describes, it does not reshape.** Every field is ``required=False``
  where the producer may legitimately omit it (the health envelope is spread
  onto some payloads and not others, ``_view`` has a defensive branch that
  emits a subset, the settings payload gains ``warning``/``backends`` on
  reads only). Over-declaring ``required`` would publish a contract the
  service does not honour.
* **No secrets, ever.** ``honcho_api_key``/``qdrant_api_key`` are persisted
  write-only and reported through ``*_is_set`` flags; the response serializers
  therefore carry the flags only, mirroring ``MemorySettingsService._serialize``.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "MemoryAdminEntryListResponseSerializer",
    "MemoryAdminEntryRowSerializer",
    "MemoryAnswerResponseSerializer",
    "MemoryAskRequestSerializer",
    "MemoryDigestResponseSerializer",
    "MemoryEntryExportResponseSerializer",
    "MemoryEntryForgetResponseSerializer",
    "MemoryEntryListResponseSerializer",
    "MemoryEntryPromoteRequestSerializer",
    "MemoryEntryViewSerializer",
    "MemoryEnvelopeSerializer",
    "MemoryProjectionPointSerializer",
    "MemoryProjectionResponseSerializer",
    "MemoryScopePurgeResponseSerializer",
    "MemorySearchItemSerializer",
    "MemorySearchResponseSerializer",
    "MemorySelfServiceDeleteResponseSerializer",
    "MemorySelfServiceResponseSerializer",
    "MemoryWorkspaceDeleteResponseSerializer",
    "MemoryWorkspaceOverviewResponseSerializer",
    "MemoryWorkspaceOverviewRowSerializer",
    "SystemMemorySettingsResponseSerializer",
    "WorkspaceMemorySettingsResponseSerializer",
    "WorkspaceMemorySettingsWriteSerializer",
    "WorkspaceMemorySlotSerializer",
]


class MemorySearchItemSerializer(serializers.Serializer):
    """One semantic-search hit (``MemoryEntryService._view``).

    ``_view`` spreads the backend env onto the row, so the hit also carries the
    ``memory.health.envelope`` keys — ``capabilities`` (see below) included,
    not just the scalar flags.
    """

    entry_id = serializers.CharField(allow_null=True)
    content = serializers.CharField()
    scope = serializers.CharField()
    workspace_id = serializers.CharField(required=False, allow_null=True)
    user_id = serializers.CharField(required=False, allow_null=True)
    artifact_id = serializers.CharField(required=False, allow_null=True)
    entity_type = serializers.CharField(required=False, allow_blank=True)
    contributor_user_id = serializers.CharField(required=False, allow_null=True)
    source_event_id = serializers.CharField(required=False, allow_null=True)
    source_session_id = serializers.CharField(required=False, allow_null=True)
    confidence = serializers.FloatField(required=False, allow_null=True)
    language = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    superseded_by = serializers.CharField(required=False, allow_null=True)
    backend_ref = serializers.CharField(required=False, allow_null=True)
    # Health envelope copied onto every item.
    backend = serializers.CharField(required=False)
    ok = serializers.BooleanField(required=False)
    detail = serializers.CharField(required=False, allow_null=True)
    degraded = serializers.BooleanField(required=False)
    digest_available = serializers.BooleanField(required=False)
    ask_available = serializers.BooleanField(required=False)
    derivation_status = serializers.CharField(required=False)
    #: ``memory.health.envelope`` spreads the whole backend env onto the view
    #: (``_view`` merges it in), and that includes ``capabilities``. Declared
    #: exactly like :class:`MemoryEnvelopeSerializer` does — the same dict, so
    #: the two components must not disagree about it.
    capabilities = serializers.DictField(required=False)


class MemorySearchResponseSerializer(serializers.Serializer):
    """``GET /api/v1/workspaces/{workspace_id}/memory/search/`` body."""

    items = MemorySearchItemSerializer(many=True)
    query = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    backend = serializers.CharField(required=False)
    ok = serializers.BooleanField(required=False)
    detail = serializers.CharField(required=False, allow_null=True)
    degraded = serializers.BooleanField(required=False)
    digest_available = serializers.BooleanField(required=False)
    ask_available = serializers.BooleanField(required=False)
    derivation_status = serializers.CharField(required=False)
    #: ``MemoryEntryService.search`` merges ``**envelope()`` into its response,
    #: so ``capabilities`` is part of the top-level body as well.
    capabilities = serializers.DictField(required=False)


class MemoryEntryViewSerializer(MemorySearchItemSerializer):
    """One memory-entry view (``MemoryEntryService._view``).

    Same field set as :class:`MemorySearchItemSerializer` — both describe the
    identical ``_view`` producer. Declared as its own component so the
    entry/digest/self-service endpoints do not publish a component named after
    the *search* surface (#1388).
    """


class MemoryEnvelopeSerializer(serializers.Serializer):
    """The backend-health envelope spread onto most memory payloads.

    Mirrors :func:`memory.health.envelope` (``{backend, ok, detail, degraded,
    digest_available, ask_available, derivation_status, capabilities}``). Used
    as a base class here rather than as a ``many``-free nested field because
    the views spread the keys flat onto their own dict with ``**envelope()``.
    """

    backend = serializers.CharField(required=False)
    ok = serializers.BooleanField(required=False)
    detail = serializers.CharField(required=False, allow_null=True)
    degraded = serializers.BooleanField(required=False)
    digest_available = serializers.BooleanField(required=False)
    ask_available = serializers.BooleanField(required=False)
    derivation_status = serializers.CharField(required=False)
    #: ``memory.backends.MemoryCapabilities`` as a dict, ``scopes`` normalised
    #: to a list. Free-form because a third-party backend may add keys.
    capabilities = serializers.DictField(required=False)


class MemoryEntryListResponseSerializer(
    MemoryEnvelopeSerializer, serializers.Serializer
):
    """``MemoryEntryService.list`` page: ``{items, total, page, page_size}``."""

    items = MemoryEntryViewSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class MemoryScopePurgeResponseSerializer(MemoryEnvelopeSerializer):
    """``DELETE /workspaces/{id}/memory/entries/`` — ``{deleted: <count>}``."""

    deleted = serializers.IntegerField()


class MemoryEntryForgetResponseSerializer(MemoryEnvelopeSerializer):
    """``DELETE /memory/entries/{entry_id}/`` — ``{deleted: true}``."""

    deleted = serializers.BooleanField()


class MemoryDigestResponseSerializer(serializers.Serializer):
    """Digest body shared by the workspace and artifact digest endpoints.

    Mirrors the dict built in ``WorkspaceMemoryDigestView.get`` /
    ``ArtifactMemoryDigestView.get`` from a ``memory.backends.MemoryDigest``.
    """

    digest = serializers.CharField()
    generated_at = serializers.CharField()
    backend = serializers.CharField()
    degraded = serializers.BooleanField()
    derivation_status = serializers.CharField()
    derived_count = serializers.IntegerField()


class MemoryAskRequestSerializer(serializers.Serializer):
    """Body of ``POST /workspaces/{id}/memory/ask/``.

    Only the *shape* is declared; the bounds (non-blank, ``MAX_ASK_QUERY_CHARS``)
    and the reasoning-level vocabulary are enforced by
    ``MemoryEntryService.ask``, exactly as they are for the MCP ``memory.ask``
    tool.
    """

    query = serializers.CharField()
    artifact_id = serializers.UUIDField(required=False, allow_null=True)
    reasoning_level = serializers.ChoiceField(
        choices=["minimal", "low", "medium", "high", "max"],
        required=False,
        allow_null=True,
    )


class MemoryAnswerResponseSerializer(serializers.Serializer):
    """Answer body of ``POST /workspaces/{id}/memory/ask/`` (``MemoryAnswer``)."""

    answer = serializers.CharField()
    generated_at = serializers.CharField()
    backend = serializers.CharField()
    degraded = serializers.BooleanField()
    detail = serializers.CharField(required=False, allow_null=True)


class MemoryEntryPromoteRequestSerializer(serializers.Serializer):
    """Body of ``POST /memory/entries/{entry_id}/promote/``."""

    workspace_id = serializers.UUIDField(required=False, allow_null=True)
    target_scope = serializers.ChoiceField(
        choices=["workspace", "artifact"], required=False, default="workspace"
    )
    change_reason = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class MemorySelfServiceResponseSerializer(MemoryEnvelopeSerializer):
    """``GET /memory/me/`` — the caller's own user-scoped aggregate."""

    entry_count = serializers.IntegerField()
    last_updated_at = serializers.DateTimeField(required=False, allow_null=True)
    # Present only with ``?include_entries=true`` (RFC #1002 PR B).
    entries = MemoryEntryViewSerializer(many=True, required=False)
    total = serializers.IntegerField(required=False)
    page = serializers.IntegerField(required=False)
    page_size = serializers.IntegerField(required=False)


class MemorySelfServiceDeleteResponseSerializer(MemoryEnvelopeSerializer):
    """``DELETE /memory/me/`` — ``{deleted: <count>}``."""

    deleted = serializers.IntegerField()


class WorkspaceMemorySlotSerializer(serializers.Serializer):
    """One entry of ``available_slots`` (Plan A T-A1-3).

    ``hard_off`` marks a slot that can never receive memory (Plan A T-A1-1),
    so the UI disables the switch instead of offering a value the writer
    rejects with "slot is hard-off".
    """

    name = serializers.CharField()
    hard_off = serializers.BooleanField()


class WorkspaceMemorySettingsResponseSerializer(serializers.Serializer):
    """``GET/PUT /workspaces/{id}/memory-settings/``.

    Plan A T-A1-3 extends the historical ``{enabled: <bool>}`` additively.
    Two distinct values must not be confused:

    * ``disabled_slots`` / ``allow_user_opt_out`` are the **stored workspace
      level** — exactly what a PUT writes, so a GET→PUT round-trip is a no-op
      and cannot promote a caller's personal user-level opt-out into
      workspace-wide policy.
    * ``effective_disabled_slots`` is the **merged** value the injection policy
      applies (global ∪ workspace ∪ caller's user level). Read-only. There is
      no ``effective_allow_user_opt_out``: ``memory.allow_user_opt_out`` has
      only the workspace level, so a merged twin would be identical and merely
      invite the same confusion.

    ``available_slots`` is the derived slot catalogue. The new fields are
    ``required=False`` because the serializer describes every version of the
    payload, not just the current one.
    """

    enabled = serializers.BooleanField()
    disabled_slots = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text=(
            "Stored workspace level only (editable source of truth). A PUT of "
            "this value writes this level; other levels are not included."
        ),
    )
    allow_user_opt_out = serializers.BooleanField(
        required=False,
        help_text="Stored workspace level (the key's only level).",
    )
    effective_disabled_slots = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text=(
            "Merged value the injection policy applies (global ∪ workspace ∪ "
            "the caller's user level). Read-only, for display."
        ),
    )
    available_slots = WorkspaceMemorySlotSerializer(many=True, required=False)


class WorkspaceMemorySettingsWriteSerializer(serializers.Serializer):
    """Body of ``PUT /workspaces/{id}/memory-settings/``.

    Partial update (Plan A T-A1-3): every field is optional and an omitted
    field is left unchanged (``enabled`` included — the view keeps the stored
    value). A supplied non-boolean value or an unknown/hard-off slot name is
    answered with 400 by the view.
    """

    enabled = serializers.BooleanField(required=False)
    disabled_slots = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
        help_text=(
            "Consumer slots this workspace suppresses, at the workspace level "
            "only (not the merged value). Validated against the derived slot "
            "vocabulary; a hard-off slot is rejected. Omitted = unchanged; "
            "null = reset this level."
        ),
    )
    allow_user_opt_out = serializers.BooleanField(
        required=False,
        allow_null=True,
        help_text=(
            "Workspace level only. When false, a user's personal memory "
            "opt-out is overridden for workspace/artifact memory (the personal "
            "user scope stays off). Omitted = unchanged; null = reset."
        ),
    )


class SystemMemorySettingsResponseSerializer(serializers.Serializer):
    """Effective memory configuration (``MemorySettingsService``).

    Transcription of ``_serialize(row)`` + ``_with_env_fallback`` — the payload
    ``GET``/``PUT``/``POST …/reset/`` all answer with. Field list mirrors
    ``memory_settings_service._OVERRIDABLE_FIELDS`` one-to-one, plus the
    ``<field>_is_override`` flag the service emits for each; every value is
    nullable because an env var may be unset. ``honcho_api_key``/``qdrant_api_key``
    are write-only secrets and are published as ``*_is_set`` flags only.
    """

    embedding_provider = serializers.CharField(required=False, allow_null=True)
    embedding_provider_is_override = serializers.BooleanField(required=False)
    embedding_model_name = serializers.CharField(required=False, allow_null=True)
    embedding_model_name_is_override = serializers.BooleanField(required=False)
    ollama_base_url = serializers.CharField(required=False, allow_null=True)
    ollama_base_url_is_override = serializers.BooleanField(required=False)
    embedding_timeout = serializers.IntegerField(required=False, allow_null=True)
    embedding_timeout_is_override = serializers.BooleanField(required=False)
    memory_backend = serializers.CharField(required=False, allow_null=True)
    memory_backend_is_override = serializers.BooleanField(required=False)
    honcho_base_url = serializers.CharField(required=False, allow_null=True)
    honcho_base_url_is_override = serializers.BooleanField(required=False)
    qdrant_base_url = serializers.CharField(required=False, allow_null=True)
    qdrant_base_url_is_override = serializers.BooleanField(required=False)
    qdrant_collection_prefix = serializers.CharField(required=False, allow_null=True)
    qdrant_collection_prefix_is_override = serializers.BooleanField(required=False)
    qdrant_distance = serializers.CharField(required=False, allow_null=True)
    qdrant_distance_is_override = serializers.BooleanField(required=False)
    qdrant_timeout = serializers.FloatField(required=False, allow_null=True)
    qdrant_timeout_is_override = serializers.BooleanField(required=False)
    qdrant_hnsw_m = serializers.IntegerField(required=False, allow_null=True)
    qdrant_hnsw_m_is_override = serializers.BooleanField(required=False)
    qdrant_hnsw_ef_construct = serializers.IntegerField(required=False, allow_null=True)
    qdrant_hnsw_ef_construct_is_override = serializers.BooleanField(required=False)
    qdrant_prefer_grpc = serializers.BooleanField(required=False, allow_null=True)
    qdrant_prefer_grpc_is_override = serializers.BooleanField(required=False)
    memory_write_rate_limit_per_hour = serializers.IntegerField(
        required=False, allow_null=True
    )
    memory_write_rate_limit_per_hour_is_override = serializers.BooleanField(
        required=False
    )
    # Secrets are reported by presence only (never plaintext).
    honcho_api_key_is_set = serializers.BooleanField(required=False)
    qdrant_api_key_is_set = serializers.BooleanField(required=False)
    #: ``get_effective_settings`` only: migration hint, non-null only when
    #: ``embedding_provider``/``memory_backend`` actually changed.
    warning = serializers.CharField(required=False, allow_null=True)
    #: ``get_effective_settings`` only: per-backend option/secret schema. A
    #: nested, registry-driven document, so it stays free-form.
    backends = serializers.DictField(required=False)
    #: ``_with_env_fallback`` additions for fields the row does not store
    #: (the Honcho dialectic/peer/scope surface plus the read-only version).
    honcho_dialectic_level = serializers.CharField(required=False, allow_null=True)
    honcho_peer_name = serializers.CharField(required=False, allow_null=True)
    honcho_workspace_id = serializers.CharField(required=False, allow_null=True)
    honcho_app_id = serializers.CharField(required=False, allow_null=True)
    honcho_session_ttl = serializers.IntegerField(required=False, allow_null=True)
    honcho_version = serializers.CharField(required=False, allow_null=True)


class MemoryWorkspaceOverviewRowSerializer(serializers.Serializer):
    """One ``MemoryAdminService.list_workspace_overview`` row."""

    workspace_id = serializers.CharField()
    workspace_name = serializers.CharField()
    enabled = serializers.BooleanField()
    workspace_entry_count = serializers.IntegerField()
    user_entry_count = serializers.IntegerField()
    by_scope = serializers.DictField(child=serializers.IntegerField())
    contributor_count = serializers.IntegerField()
    degraded = serializers.BooleanField()
    last_consolidated_at = serializers.DateTimeField(required=False, allow_null=True)


class MemoryWorkspaceOverviewResponseSerializer(MemoryEnvelopeSerializer):
    """``GET /system/memory/workspaces/`` — overview rows + consolidation counters."""

    results = MemoryWorkspaceOverviewRowSerializer(many=True)
    #: Per-trigger-source counter (issue #1300); best-effort, ``{}`` on outage.
    memory_consolidations_total = serializers.DictField(
        child=serializers.IntegerField()
    )
    consolidation_total = serializers.IntegerField()


class MemoryWorkspaceDeleteResponseSerializer(MemoryEnvelopeSerializer):
    """``DELETE /system/memory/workspaces/{id}/`` — per-tier deletion counters."""

    workspace_id = serializers.CharField()
    workspace_memory_deleted = serializers.IntegerField()
    artifact_memory_deleted = serializers.IntegerField()
    user_memory_deleted = serializers.IntegerField()


class MemoryAdminEntryRowSerializer(serializers.Serializer):
    """One ``MemoryAdminService.list_entries`` row."""

    id = serializers.CharField()
    content = serializers.CharField()
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    confidence = serializers.FloatField(required=False, allow_null=True)
    owner_type = serializers.CharField()
    owner_id = serializers.CharField()
    owner_label = serializers.CharField(required=False, allow_blank=True)


class MemoryAdminEntryListResponseSerializer(MemoryEnvelopeSerializer):
    """``GET /system/memory/entries/`` — ``{results, count, page, page_size}``."""

    results = MemoryAdminEntryRowSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class MemoryEntryExportResponseSerializer(MemoryEnvelopeSerializer):
    """JSON branch of ``GET /system/memory/entries/export/``.

    The CSV branch of the same endpoint is published separately as
    ``text/csv`` (a binary stream) — see
    ``SystemMemoryEntriesExportView.get``. It is deliberately NOT folded into
    this component: the endpoint's media type, not its shape, decides which
    body a client receives.
    """

    entries = MemoryAdminEntryRowSerializer(many=True)
    count = serializers.IntegerField()
    truncated = serializers.BooleanField()


class MemoryProjectionPointSerializer(serializers.Serializer):
    """One projected 2D memory point."""

    id = serializers.CharField()
    x = serializers.FloatField()
    y = serializers.FloatField()
    cluster_id = serializers.IntegerField()
    owner_type = serializers.CharField()
    owner_id = serializers.CharField()
    owner_label = serializers.CharField(required=False, allow_blank=True)


class MemoryProjectionResponseSerializer(MemoryEnvelopeSerializer):
    """``GET /system/memory/projection/`` — PCA coordinates + cluster ids."""

    points = MemoryProjectionPointSerializer(many=True)
    sampled = serializers.BooleanField()
    sample_size = serializers.IntegerField()
    total_size = serializers.IntegerField()
    excluded_no_embedding = serializers.IntegerField()
