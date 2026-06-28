"""
ARCH-L1-006 BaselineService — Django ORM models for Baseline persistence.

leaf_id: COMP-BL-003 (BaselineStore)
req_id:  REQ-L2-BL-001, REQ-L2-BL-002, REQ-L2-BL-005, REQ-L2-BL-007

Two new models are defined here (ADR-BL-02: Delta-Storage):

    BaselineSnapshot  — immutable Baseline header record
    BaselineDeltaIndexEntry — one (item_id, version, entity_type) tuple per entry

Immutability is enforced at two levels (ADR-L3-BL003-01):
  1. Application layer: ``BaselineStore.update()`` / ``delete()`` raise
     ``BaselineImmutableError`` before any SQL is executed.
  2. Database level (PostgreSQL): the migration installs BEFORE UPDATE and
     BEFORE DELETE triggers that raise an exception from within PostgreSQL,
     preventing bypasses through raw SQL or direct ORM abuse.

Unique constraints:
  - BaselineSnapshot: UNIQUE(workspace_id, name) — REQ-L2-BL-005
  - BaselineDeltaIndexEntry: UNIQUE(baseline, item_id) — prevents duplicates

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/Components/
  COMP-BL-003_BaselineStore/L3_COMP-BL-003_BaselineStore_Architecture.md
"""
from __future__ import annotations

import uuid

from django.db import models

from persistence.models import TenantScopedModel


class BaselineSnapshot(TenantScopedModel):
    """Immutable Baseline header (COMP-BL-003, REQ-L2-BL-001/002/005).

    Stores metadata only; the actual item/version pairs live in
    :class:`BaselineDeltaIndexEntry`.  Once created, this record MUST NOT be
    modified or deleted — enforced by DB triggers (see migration) and the
    application-layer :class:`baseline.store.BaselineStore`.

    Inherits from TenantScopedModel:
        id, tenant, created_at, created_by, modified_at, modified_by, version
    """

    # Workspace scope for tenant-internal partitioning.
    workspace_id = models.UUIDField(db_index=True)

    # Baseline scope: document | project | global (REQ-L2-BL-001)
    scope = models.CharField(max_length=32)

    # Human-readable name — unique within a workspace (REQ-L2-BL-005)
    name = models.CharField(max_length=500)

    # Optional free-text description
    description = models.TextField(blank=True, default="")

    # User / agent identifier that triggered creation (stored as string)
    created_by_ref = models.CharField(max_length=255, blank=True, default="")

    # Optional link to the root Artifact (nullable for project/global scope).
    # Migrated from legacy persistence.Baseline (REQ-L2-BL-001).
    artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="baseline_snapshots",
    )

    class Meta:
        db_table = "bl_baseline_snapshot"
        constraints = [
            # REQ-L2-BL-005: name unique per workspace
            models.UniqueConstraint(
                fields=["workspace_id", "name"],
                name="uq_baseline_ws_name",
            ),
        ]
        indexes = [
            # Listing queries filter by workspace_id + created_at DESC
            models.Index(
                fields=["workspace_id", "-created_at"],
                name="idx_baseline_snapshot_ws_cat",
            ),
            models.Index(
                fields=["workspace_id", "scope"],
                name="idx_baseline_snapshot_ws_scope",
            ),
        ]

    def __str__(self) -> str:
        return f"BaselineSnapshot({self.name!r}, scope={self.scope}, id={self.id})"


class BaselineDeltaIndexEntry(models.Model):
    """Single (item_id, version, entity_type) tuple in a Baseline.

    Each entry is one atomic reference captured at Baseline creation time.
    The entry MUST NOT be modified or deleted after creation (immutability
    mirrors :class:`BaselineSnapshot`).

    entity_type differentiates items from ICD versions and TraceLinks
    ("item" | "icd" | "trace_link").

    COMP-BL-003 (REQ-L2-BL-001, ADR-BL-02)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Foreign key to the owning Baseline — CASCADE so that if a snapshot is
    # ever physically removed (maintenance-only), orphan rows are cleaned up.
    # Application-layer immutability prevents normal delete paths.
    baseline = models.ForeignKey(
        BaselineSnapshot,
        on_delete=models.CASCADE,
        related_name="delta_entries",
        db_index=True,
    )

    # The entity being versioned (Requirement/Artifact UUID as string to avoid
    # coupling to specific persistence models from other apps)
    item_id = models.CharField(max_length=64, db_index=True)

    # Version number at snapshot time (from AuditableModel.version)
    version = models.IntegerField()

    # Discriminator for entity kind
    entity_type = models.CharField(max_length=32, default="item")

    class Meta:
        db_table = "bl_delta_index_entry"
        constraints = [
            # UNIQUE(baseline, item_id) prevents duplicate entries for the same
            # item within a single baseline (REQ-L3-BL003-001)
            models.UniqueConstraint(
                fields=["baseline", "item_id"],
                name="uq_delta_entry_baseline_item",
            ),
        ]
        indexes = [
            # Lookup by (baseline_id, item_id) — used by VersionReconstructor
            models.Index(
                fields=["baseline", "item_id"],
                name="idx_delta_entry_baseline_item",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"DeltaEntry(baseline={self.baseline_id}, "
            f"item={self.item_id}, v={self.version})"
        )


__all__ = [
    "BaselineSnapshot",
    "BaselineDeltaIndexEntry",
]
