"""AI Long-Term Memory models (Spec 2026-08-24, Task 2 + Task 11).

Two tenant-scoped tables holding consolidated, embeddable memory facts:

- ``WorkspaceMemory``: facts scoped to a single ``Workspace`` (e.g. team
  preferences learned from interactions within that workspace).
- ``UserTenantMemory``: facts scoped to a single user across the whole
  tenant (no ``workspace`` field) — e.g. a user's own preferences that
  should follow them between workspaces.

Both models are additive read/write targets for the (future, Task 3+)
``MemoryBackend`` abstraction; nothing here queries or writes to them yet.
``superseded_by`` is a self-referential FK used by the (future, Task 5)
consolidation pipeline to mark a fact as replaced by a newer one without
deleting the historical row.

``WorkspaceMemorySettings`` (Task 11) is a third, independent table: the
per-workspace enable/disable toggle for the memory feature. Missing row =
feature ON (``enabled`` defaults ``True``), mirroring the "missing row =
default state" convention already used by ``LlmSettings``.
"""
from uuid import UUID

from django.db import models
from pgvector.django import HnswIndex, VectorField

from persistence.encryption import decrypt_secret, encrypt_secret
from persistence.models import AuditableModel, TenantScopedModel, Workspace


class WorkspaceMemory(TenantScopedModel):
    """A consolidated memory fact scoped to a single ``Workspace``."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memory_entries")
    content = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="supersedes"
    )
    confidence = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mem_workspace_memory"
        indexes = [
            models.Index(fields=["tenant", "workspace", "created_at"], name="idx_mem_ws_created"),
            HnswIndex(
                name="mem_ws_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]


class UserTenantMemory(TenantScopedModel):
    """A consolidated memory fact scoped to a single user, tenant-wide
    (no ``workspace`` field — follows the user between workspaces).
    """

    user = models.ForeignKey("persistence.User", on_delete=models.CASCADE, related_name="tenant_memory_entries")
    content = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="supersedes"
    )
    confidence = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mem_user_tenant_memory"
        indexes = [
            models.Index(fields=["tenant", "user", "created_at"], name="idx_mem_user_created"),
            HnswIndex(
                name="mem_user_embedding_hnsw",
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
