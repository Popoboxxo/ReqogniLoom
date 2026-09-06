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
from typing import Any, TYPE_CHECKING

from django.db import models
from pgvector.django import HnswIndex, VectorField

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
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


class IcdType(models.TextChoices):
    """Interface type classification (REQ-006).

    Classifies the communication pattern of the interface control document.
    """

    PROVIDES = "provides", "Provides"
    REQUIRES = "requires", "Requires"
    EVENT_IN = "event-in", "Event In"
    EVENT_OUT = "event-out", "Event Out"
    DATA = "data", "Data"
    CONTROL = "control", "Control"
    MECHANICAL = "mechanical", "Mechanical"
    ELECTRICAL = "electrical", "Electrical"


class IcdParameterDataType(models.TextChoices):
    """Data type of a structured interface parameter (REQ-L2-ICD-002).

    Classifies the value domain so consumers can interpret ``min_value`` /
    ``max_value`` / ``nominal_value`` correctly.
    """

    FLOAT = "float", "Float"
    INT = "int", "Integer"
    STRING = "string", "String"
    BOOLEAN = "boolean", "Boolean"
    ENUM = "enum", "Enum"
    OTHER = "other", "Other"


class IcdParameterDirection(models.TextChoices):
    """Data-flow direction of a structured interface parameter.

    Independent from the ICD-level :class:`IcdDirection`: describes the flow of
    a single parameter across the interface, not the overall contract.
    """

    INPUT = "input", "Input"
    OUTPUT = "output", "Output"
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
    # Datenmodell-Konsolidierung Phase 3 (spec §4): backing Artifact row so an
    # ICD is a valid TraceLink endpoint and a Document-scope baseline subject.
    # SET_NULL rather than CASCADE, matching Diagram.artifact: removing the
    # shadow Artifact (e.g. a TraceLink cleanup cascade) must never delete the
    # ICD itself.
    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="icd",
    )
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
    # -- Current contract (Datenmodell-Konsolidierung Task 28c-1, Expand) ----
    # IcdVersion is both this subsystem's history store *and* the only place
    # the current Design-by-Contract payload lives. Task 28a moved the history
    # into persistence.ArtifactVersion; the columns below take over the
    # "current content" half so IcdVersion can be dropped in Task 28c-2.
    #
    # During the Expand phase both stores coexist: every write path still
    # writes IcdVersion and still moves `current_version`, and nothing reads
    # the columns below yet. Migration 0011 backfills them from
    # `current_version`; Task 28c-2 repoints the readers and the writers.
    direction = models.CharField(
        max_length=32,
        choices=IcdDirection.choices,
        default=IcdDirection.UNIDIRECTIONAL,
    )
    interface_type = models.CharField(
        max_length=32,
        choices=IcdType.choices,
        blank=True,
        default="",
        help_text="Interface type classification: provides, requires, event-in, event-out, data, control.",
    )
    semantic_description = models.TextField(blank=True, default="")
    preconditions = models.JSONField(default=list, blank=True)
    postconditions = models.JSONField(default=list, blank=True)
    invariants = models.JSONField(default=list, blank=True)
    embedding = VectorField(
        dimensions=EMBEDDING_VECTOR_DIMENSIONS,
        null=True,
        blank=True,
        help_text=(
            "REQ-L2-VS-004: Semantic embedding for cosine similarity search, "
            "sized by persistence.embedding_dimensions."
            "EMBEDDING_VECTOR_DIMENSIONS (#794). Unlike IcdVersion.embedding "
            "this row is mutable, so it is re-generated on every contract "
            "change. Best-effort: NULL when no embedding provider is "
            "configured."
        ),
    )
    # Revision number of the contract above, in the same numbering space as
    # IcdVersion.version_number and persistence.ArtifactVersion.revision
    # (icd.icd_manager._record_artifact_revision keeps the two identical).
    # 0 means "no revision recorded yet" — the only valid state for an Icd
    # with no current_version.
    current_revision = models.PositiveIntegerField(default=0)

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
            # REQ-L2-VS-004: mirrors icd_version_embedding_hnsw so ICD
            # semantic search keeps its index once search_service reads the
            # current contract off this row instead of off IcdVersion.
            HnswIndex(
                name="icd_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"ICD({self.name})"

    @property
    def parameters_snapshot(self) -> list[dict[str, Any]]:
        """Return this ICD's structured parameters as a JSON-safe list.

        Datenmodell-Konsolidierung Task 28c-1. Every other artifact type's
        fields are captured *by value* into each ``ArtifactVersion`` payload;
        ``IcdParameter`` is the one exception, because it lives in its own
        child rows. This property is the bridge: it renders the current
        parameter set into the same by-value shape, so
        ``application.artifact_version_service.snapshot_fields`` can pick it
        up through a plain ``getattr`` once ``"parameters_snapshot"`` is added
        to ``_ENTITY_FIELDS["Icd"]`` (Task 28c-2 — see the report for why that
        wiring is deliberately not part of the Expand step).

        Reads through ``unscoped`` with an explicit ``tenant_id`` rather than
        the ``parameters`` related manager: the related manager is derived
        from :class:`~persistence.tenancy.TenantManager` and would raise
        ``TenantContextNotSetError`` on the Ext-layer write paths, which pass
        the tenant explicitly instead of arming the thread-local context
        (same convention as :mod:`icd.icd_manager`).

        ``Decimal`` bounds are stringified: ``ArtifactVersion.payload`` is a
        plain ``JSONField`` with no custom encoder, and ``json.dumps`` rejects
        ``Decimal``. ``str`` keeps the value lossless, unlike ``float``.

        Returns:
            One dict per parameter, ordered by ``ordering`` then ``name``
            (matching :class:`IcdParameter` ``Meta.ordering``), each carrying
            every user-editable parameter field.
        """
        rows = IcdParameter.unscoped.filter(
            icd_id=self.pk, tenant_id=self.tenant_id
        ).order_by("ordering", "name")
        return [
            {
                "name": row.name,
                "description": row.description,
                "unit": row.unit,
                "data_type": row.data_type,
                "direction": row.direction,
                "min_value": None if row.min_value is None else str(row.min_value),
                "max_value": None if row.max_value is None else str(row.max_value),
                "nominal_value": row.nominal_value,
                "tolerance": row.tolerance,
                "ordering": row.ordering,
            }
            for row in rows
        ]


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
    interface_type = models.CharField(
        max_length=32,
        choices=IcdType.choices,
        blank=True,
        default="",
        help_text="Interface type classification: provides, requires, event-in, event-out, data, control.",
    )
    semantic_description = models.TextField(blank=True, default="")
    # Design-by-Contract fields — stored as JSON lists of strings
    preconditions = models.JSONField(default=list, blank=True)
    postconditions = models.JSONField(default=list, blank=True)
    invariants = models.JSONField(default=list, blank=True)
    embedding = VectorField(
        dimensions=EMBEDDING_VECTOR_DIMENSIONS,
        null=True,
        blank=True,
        help_text=(
            "REQ-L2-VS-004: Semantic embedding for cosine similarity search, "
            "sized by persistence.embedding_dimensions."
            "EMBEDDING_VECTOR_DIMENSIONS (#794). Set at creation time only — "
            "IcdVersion is immutable (DB trigger). Best-effort: NULL when no "
            "embedding provider is configured."
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


# ---------------------------------------------------------------------------
# IcdParameter — structured, version-specific interface parameter
# REQ-L2-ICD-002 (Design-by-Contract): extends the free-text pre/post/invariant
# JSON lists with structured parameters carrying units, value ranges and
# tolerances. Parameters are attached to a concrete IcdVersion (append-only),
# so a parameter set is immutable together with the version it belongs to.
# ---------------------------------------------------------------------------


class IcdParameter(TenantScopedModel):
    """A single structured parameter of an interface contract revision.

    Parameters are version-specific: each :class:`IcdVersion` owns its own set
    of parameters, mirroring the append-only immutability of the version itself.
    Numeric bounds live in ``min_value``/``max_value``; symbolic or string
    defaults live in ``nominal_value``; ``tolerance`` stays free text (e.g.
    ``"±5%"`` or ``"0.1"``) as it varies by engineering domain.

    leaf_id: COMP-ICD-001
    req_id: REQ-L2-ICD-002
    IF: IF-L1-040 (output to PersistenceLayer)
    """

    icd_version = models.ForeignKey(
        IcdVersion,
        on_delete=models.CASCADE,
        related_name="parameters",
        db_index=True,
    )
    # -- Owner after the IcdVersion retirement (Task 28c-1, Expand) ---------
    # Nullable and unused during the Expand phase: migration 0011 backfills it
    # from ``icd_version.icd_id`` for every existing row, Task 28c-2 repoints
    # the readers/writers and then drops ``icd_version`` above.
    #
    # This flattens parameters from "the set belonging to revision N" to
    # "the ICD's current parameter set", matching every other artifact type —
    # a Requirement's fields are captured by value into each ArtifactVersion
    # snapshot, they do not live in child rows that survive across revisions.
    # ``Icd.parameters_snapshot`` provides the by-value capture that keeps
    # historical parameter states reconstructable.
    icd = models.ForeignKey(
        Icd,
        on_delete=models.CASCADE,
        related_name="parameters",
        null=True,
        blank=True,
        db_index=True,
    )
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=2000, blank=True, default="")
    unit = models.CharField(max_length=50, blank=True, default="")
    data_type = models.CharField(
        max_length=20,
        choices=IcdParameterDataType.choices,
        default=IcdParameterDataType.OTHER,
    )
    direction = models.CharField(
        max_length=15,
        choices=IcdParameterDirection.choices,
        default=IcdParameterDirection.INPUT,
    )
    min_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
    )
    max_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
    )
    # Nominal/default value for enum and string types (kept as text so it can
    # carry symbolic values that do not fit the numeric min/max bounds).
    nominal_value = models.CharField(max_length=200, blank=True, default="")
    # Free-text tolerance such as "±5%" or "0.1" — format varies by domain.
    tolerance = models.CharField(max_length=100, blank=True, default="")
    ordering = models.PositiveSmallIntegerField(default=0)

    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        db_table = "icd_parameter"
        ordering = ["ordering", "name"]
        indexes = [
            models.Index(
                fields=["icd_version", "ordering"],
                name="idx_icd_param_version_order",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"IcdParameter({self.name}, v={self.icd_version_id})"


__all__ = [
    "Icd",
    "IcdDirection",
    "IcdParameter",
    "IcdParameterDataType",
    "IcdParameterDirection",
    "IcdType",
    "IcdVersion",
]
