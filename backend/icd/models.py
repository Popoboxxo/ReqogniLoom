"""
IcdManagement — Django ORM models.

leaf_id: COMP-ICD-001 (IcdManager), COMP-ICD-002 (ContractValidator)
req_id:  REQ-L1-028, REQ-L2-ICD-001, REQ-L2-ICD-002
arch_id: ARCH-L1-014

Defines two entities:
  - Icd       : logical identity of an Interface Control Document
  - IcdVersion: immutable, append-only version record (Design-by-Contract fields)

DB-level immutability for IcdVersion is enforced via a BEFORE UPDATE/DELETE
trigger in migration 0001_initial, mirroring the baseline immutability pattern
(ADR-ICD-01, baseline/migrations/0001_initial.py).

IF-L1-040: persistence of Icd and IcdVersion entities.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.db import models
from pgvector.django import HnswIndex, VectorField

from persistence.models import TenantScopedModel
from persistence.tenancy import TenantManager, UnscopedManager

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Direction choices (REQ-L2-ICD-002)
# ---------------------------------------------------------------------------

class IcdDirection(models.TextChoices):
    """Direction of the interface contract."""

    UNIDIRECTIONAL = "unidirectional", "Unidirectional"
    BIDIRECTIONAL = "bidirectional", "Bidirectional"


# ---------------------------------------------------------------------------
# Icd — logical identity
# REQ-L2-ICD-001: CRUD, REQ-L2-ICD-002: Design-by-Contract fields
# ---------------------------------------------------------------------------

class Icd(TenantScopedModel):
    """Logical identity of an Interface Control Document.

    Stores the stable identity (source/target elements, workspace) and points
    to the current active IcdVersion via ``current_version``. Every update
    appends a new IcdVersion; this header is the only mutable record.

    leaf_id: COMP-ICD-001
    req_id:  REQ-L2-ICD-001, REQ-L2-ICD-002
    IF:      IF-L1-040 (output to PersistenceLayer)
    """

    workspace_id = models.UUIDField(db_index=True)
    # Source and target architecture element IDs (Artifact UUIDs)
    source_element_id = models.UUIDField(db_index=True)
    target_element_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=500)
    # FK to the most recent IcdVersion (null until first version is saved)
    current_version = models.OneToOneField(
        "IcdVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_for_icd",
    )

    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        db_table = "icd_icd"
        indexes = [
            models.Index(fields=["workspace_id"], name="idx_icd_workspace"),
            models.Index(
                fields=["source_element_id", "target_element_id"],
                name="idx_icd_source_target",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"ICD({self.name})"


# ---------------------------------------------------------------------------
# IcdVersion — immutable Design-by-Contract record
# REQ-L2-ICD-001 (immutable), REQ-L2-ICD-002 (DbC fields)
# ---------------------------------------------------------------------------

class IcdVersion(TenantScopedModel):
    """Immutable snapshot of an ICD contract at a specific revision.

    Each update to an ICD appends a new IcdVersion row; existing rows are
    never modified or deleted. DB-level enforcement via trigger (see migration).

    Design-by-Contract fields (REQ-L2-ICD-002):
      - direction / interface_type : structural contract metadata
      - semantic_description       : human-readable contract intent
      - preconditions              : caller obligations (JSON list of strings)
      - postconditions             : callee guarantees (JSON list of strings)
      - invariants                 : conditions that must always hold (JSON list)

    leaf_id: COMP-ICD-001, COMP-ICD-002
    req_id:  REQ-L2-ICD-001, REQ-L2-ICD-002
    IF:      IF-L1-040 (output to PersistenceLayer)
    """

    icd = models.ForeignKey(
        Icd,
        on_delete=models.CASCADE,
        related_name="versions",
        db_index=True,
    )
    version_number = models.PositiveIntegerField()
    direction = models.CharField(
        max_length=32,
        choices=IcdDirection.choices,
        default=IcdDirection.UNIDIRECTIONAL,
    )
    interface_type = models.CharField(max_length=128, blank=True, default="")
    semantic_description = models.TextField(blank=True, default="")
    # Design-by-Contract fields — stored as JSON lists of strings
    preconditions = models.JSONField(default=list, blank=True)
    postconditions = models.JSONField(default=list, blank=True)
    invariants = models.JSONField(default=list, blank=True)
    embedding = VectorField(
        dimensions=1536,
        null=True,
        blank=True,
        help_text=(
            "REQ-L2-VS-004: Semantic embedding (1536-dim, OpenAI "
            "text-embedding-3-small compatible) for cosine similarity search. "
            "Set at creation time only — IcdVersion is immutable (DB trigger). "
            "Best-effort: NULL when no embedding provider is configured."
        ),
    )

    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        db_table = "icd_version"
        constraints = [
            models.UniqueConstraint(
                fields=["icd", "version_number"],
                name="uq_icd_version_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["icd", "version_number"],
                name="idx_icd_version_icd_num",
            ),
            models.Index(
                fields=["icd", "-created_at"],
                name="idx_icd_version_icd_cat",
            ),
            # REQ-L2-VS-004: HNSW approximate-nearest-neighbour index for
            # cosine-distance similarity queries (embedding <=> query_vector).
            HnswIndex(
                name="icd_version_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"IcdVersion(icd={self.icd_id}, v{self.version_number})"


__all__ = [
    "Icd",
    "IcdDirection",
    "IcdVersion",
]
