"""AI Long-Term Memory models (Spec 2026-08-24; unified by RFC #1002 PR A).

``MemoryEntry`` is the single, canonical tenant-scoped table holding
consolidated, embeddable memory facts. It replaces the former
``WorkspaceMemory``/``UserTenantMemory`` split: a ``scope`` column
(``"user"``/``"workspace"``/``"artifact"``) selects which of the three nullable
owner FKs is meaningful, and backend provenance travels as columns
(``language``, ``confidence``, ``contributor_user_id``, ``source_event_id``,
``source_session_id``, ``entity_type``, ``backend_ref``) rather than in a
sidecar table. ``superseded_by`` is a self-referential FK used by the
consolidation pipeline to mark a fact as replaced by a newer one without
deleting the historical row.

The table is the read/write target of the ``MemoryBackend`` abstraction
(``memory.backends``); the pgvector backend makes it authoritative, the honcho
backend keeps it as the local canonical mirror of the external service.

``WorkspaceMemorySettings`` (Task 11) is an independent table: the
per-workspace enable/disable toggle for the memory feature. Missing row =
feature ON (``enabled`` defaults ``True``), mirroring the "missing row =
default state" convention already used by ``LlmSettings``.

``SystemMemorySettings`` (Memory Admin UI Phase 3) is the process-wide
singleton overriding the memory-related env vars.
"""
from uuid import UUID

from django.db import models
from pgvector.django import HnswIndex, VectorField

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.encryption import decrypt_secret, encrypt_secret
from persistence.models import AuditableModel, TenantScopedModel, Workspace


class MemoryEntry(TenantScopedModel):
    """Canonical, unified consolidated memory fact (RFC #1002, PR A).

    Replaces the former ``WorkspaceMemory``/``UserTenantMemory`` split with one
    table carrying provenance as columns (no sidecar table). ``scope`` selects
    which of the three nullable owner FKs is meaningful:

    ==================  ==================================================
    ``scope``           owner column / ``scope_id`` semantics
    ==================  ==================================================
    ``"workspace"``     ``workspace`` (workspace_id)
    ``"user"``          ``user`` (user_id)
    ``"artifact"``      ``artifact`` (artifact_id)
    ==================  ==================================================

    ``entry_id`` is always OUR UUID primary key. :attr:`backend_ref` carries the
    id the *external* memory backend issued for this entry (a Honcho nanoid for
    the honcho backend; NULL for pgvector), so a locally-canonical row can be
    reconciled against the external service without ever rewriting the PK.

    ``contributor_user_id`` is a plain UUID, deliberately NOT a ``User`` FK:
    attribution must survive the contributor's deletion, which ``SET_NULL`` on
    an FK could not express. ``superseded_by`` is a self-referential FK marking a
    fact replaced by a newer one without deleting history.
    """

    SCOPE_USER = "user"
    SCOPE_WORKSPACE = "workspace"
    SCOPE_ARTIFACT = "artifact"
    SCOPE_CHOICES = (
        (SCOPE_USER, SCOPE_USER),
        (SCOPE_WORKSPACE, SCOPE_WORKSPACE),
        (SCOPE_ARTIFACT, SCOPE_ARTIFACT),
    )

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES)
    workspace = models.ForeignKey(
        "persistence.Workspace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="memory_entries",
    )
    user = models.ForeignKey(
        "persistence.User",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="memory_entries",
    )
    artifact = models.ForeignKey(
        "persistence.Artifact",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="memory_entries",
    )
    content = models.TextField()
    # #794: sourced from the project-wide SSOT rather than a local literal, so
    # this column can no longer silently drift apart from the Requirement/
    # TraceLink/Icd embedding columns the way it had (384 vs 1536).
    embedding = VectorField(dimensions=EMBEDDING_VECTOR_DIMENSIONS, null=True, blank=True)
    language = models.CharField(max_length=8, blank=True, default="")
    confidence = models.FloatField(default=1.0)
    superseded_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="supersedes"
    )
    # Plain UUID, NOT an FK: attribution must outlive the contributor's deletion.
    contributor_user_id = models.UUIDField(null=True, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True)
    source_session_id = models.UUIDField(null=True, blank=True)
    entity_type = models.CharField(max_length=32, blank=True, default="")
    # Backend-issued id for this entry (e.g. a Honcho nanoid); NULL for pgvector.
    backend_ref = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "mem_memory_entry"
        indexes = [
            models.Index(
                fields=["tenant", "scope", "workspace", "created_at"],
                name="idx_mem_entry_ws_created",
            ),
            models.Index(
                fields=["tenant", "scope", "user", "created_at"],
                name="idx_mem_entry_user_created",
            ),
            models.Index(
                fields=["tenant", "scope", "artifact", "created_at"],
                name="idx_mem_entry_artifact_created",
            ),
            models.Index(fields=["backend_ref"], name="idx_mem_entry_backend_ref"),
            HnswIndex(
                name="mem_entry_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]


class WorkspaceMemorySettings(TenantScopedModel):
    """Per-workspace enable/disable toggle for the AI Long-Term Memory feature.

    One row per ``Workspace`` (``OneToOneField``, mirrors
    ``context_graph.models.WorkspaceContextSettings``). Missing row = feature
    ON (``enabled`` defaults ``True``) — the read path (``memory_rest``) never
    creates this row as a side effect; only the write path (PUT) does.
    """

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE)
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "mem_workspace_memory_settings"


SYSTEM_MEMORY_SETTINGS_ID = UUID("00000000-0000-0000-0000-000000000001")


class SystemMemorySettings(AuditableModel):
    """Process-wide singleton: DB override for the memory feature's
    environment configuration (Memory Admin UI Phase 3, spec 2026-08-26).

    Deliberately NOT ``TenantScopedModel`` — see Phase 3 plan Ruling 1.
    ``get_embedding_provider()``/``get_memory_backend()`` are process-global
    functions with no tenant parameter; this table backs exactly the env
    vars they already read (``EMBEDDING_PROVIDER``, ``MEMORY_BACKEND``, ...).

    Every field is nullable: ``NULL`` means "no override, environment wins".
    Singleton enforced by ``save()`` always forcing the same primary key —
    there is only ever one row, created lazily on first write (issue #276
    precedent: reads never create a row, only PUT/reset do).
    """

    embedding_provider = models.CharField(max_length=32, null=True, blank=True)
    embedding_model_name = models.CharField(max_length=128, null=True, blank=True)
    ollama_base_url = models.CharField(max_length=255, null=True, blank=True)
    embedding_timeout = models.PositiveIntegerField(null=True, blank=True)
    memory_backend = models.CharField(max_length=32, null=True, blank=True)
    honcho_base_url = models.CharField(max_length=255, null=True, blank=True)
    # RFC #1002 PR B: admin-configurable, fixed-window write ratelimit for
    # ``memory.write``. NULL = "no override, env/default wins" (the env var is
    # ``MEMORY_WRITE_RATE_LIMIT_PER_HOUR``, default 60); ``0`` is an explicit
    # "unlimited" override. ``PositiveIntegerField`` therefore rules out a
    # negative value that could only ever be a typo.
    memory_write_rate_limit_per_hour = models.PositiveIntegerField(null=True, blank=True)
    # Fernet ciphertext, mirrors LlmSettings.api_key_encrypted. Never read/write
    # directly -- use the honcho_api_key property below.
    honcho_api_key_encrypted = models.TextField(blank=True, default="")

    class Meta:
        db_table = "mem_system_memory_settings"

    def save(self, *args, **kwargs) -> None:
        self.pk = SYSTEM_MEMORY_SETTINGS_ID
        super().save(*args, **kwargs)

    @property
    def honcho_api_key(self) -> str:
        return decrypt_secret(self.honcho_api_key_encrypted)

    @honcho_api_key.setter
    def honcho_api_key(self, value: str) -> None:
        self.honcho_api_key_encrypted = encrypt_secret(value or "")
