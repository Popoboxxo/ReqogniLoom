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
from django.db import models
from pgvector.django import HnswIndex, VectorField

from persistence.models import TenantScopedModel, Workspace


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
