"""
IcdManagement — Django ORM models.

leaf_id: COMP-ICD-001 (IcdManager), COMP-ICD-002 (ContractValidator)
req_id:  REQ-L1-028, REQ-L2-ICD-001, REQ-L2-ICD-002
arch_id: ARCH-L1-014

Defines two entities:
  - Icd         : an Interface Control Document — identity *and* current
                  Design-by-Contract payload
  - IcdParameter: a structured parameter of the ICD's current contract

Datenmodell-Konsolidierung Task 28c-2 retired ``IcdVersion``. Contract history
now lives in the one shared, append-only snapshot store
(:class:`persistence.models.ArtifactVersion`, Task 27/28a) like every other
artifact type's; :class:`IcdRevision` below is the by-value read model those
snapshots are rehydrated into.

IF-L1-040: persistence of Icd and IcdParameter entities.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from django.db import models
from pgvector.django import HnswIndex, VectorField

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import TenantScopedModel
from persistence.tenancy import TenantManager, UnscopedManager


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
    """An Interface Control Document: identity plus its current contract.

    Stores the stable identity (source/target elements, workspace) *and* the
    current Design-by-Contract payload. Every update overwrites the payload in
    place and appends a snapshot of it to
    :class:`persistence.models.ArtifactVersion` — the same shape every other
    artifact type uses (Datenmodell-Konsolidierung Task 28c-2, which retired
    the dedicated ``IcdVersion`` table).

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
    # -- Current contract (Datenmodell-Konsolidierung Task 28c-1/28c-2) ------
    # IcdVersion used to be both this subsystem's history store *and* the only
    # place the current Design-by-Contract payload lived. Task 28a moved the
    # history into persistence.ArtifactVersion, Task 28c-1 added the columns
    # below, and Task 28c-2 made them authoritative and dropped IcdVersion.
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
            "EMBEDDING_VECTOR_DIMENSIONS (#794). This row is mutable, so the "
            "embedding is re-generated on every contract change and a failed "
            "generation can be retried. Best-effort: NULL when no embedding "
            "provider is configured."
        ),
    )
    # Revision number of the contract above, in the same numbering space as
    # persistence.ArtifactVersion.revision — icd.icd_manager allocates the two
    # together, under the same row lock. 0 means "no revision recorded yet",
    # which is only reachable for a row whose backing Artifact is missing.
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
            # REQ-L2-VS-004: HNSW approximate-nearest-neighbour index for
            # cosine-distance similarity queries (embedding <=> query_vector).
            # Replaces icd_version_embedding_hnsw, which went away with
            # IcdVersion (Task 28c-2).
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

        Datenmodell-Konsolidierung Task 28c-1/28c-2. Every other artifact
        type's fields are captured *by value* into each ``ArtifactVersion``
        payload; ``IcdParameter`` is the one exception, because it lives in
        its own child rows. This property is the bridge: it renders the
        current parameter set into the same by-value shape, and
        ``"parameters_snapshot"`` is registered in
        ``artifact_diff_service._ENTITY_FIELDS["Icd"]`` so the stored and the
        diffed field sets stay identical by construction.

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
# IcdRevision — by-value read model for one historical contract revision
# REQ-L2-ICD-001 (history), REQ-L2-ICD-002 (DbC fields)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IcdRevision:
    """One ICD contract revision, rehydrated from an ``ArtifactVersion`` row.

    Datenmodell-Konsolidierung Task 28c-2. Replaces the ``IcdVersion`` ORM row
    that :func:`icd.services.get_icd_history` and
    :func:`icd.services.get_icd_versions` used to return. It is deliberately a
    plain frozen dataclass, not a model: contract history is no longer a table
    of its own, it is a set of JSON snapshots in the one shared
    :class:`persistence.models.ArtifactVersion` store, and rehydrating them
    into an ORM instance would invite callers to ``save()`` a row that has no
    table behind it.

    The attribute names match the ones the retired ``IcdVersion`` exposed, so
    every ``revision.version_number`` / ``revision.preconditions`` reader
    keeps working unchanged.
    """

    icd_id: uuid.UUID
    version_number: int
    name: str = ""
    direction: str = IcdDirection.UNIDIRECTIONAL
    interface_type: str = ""
    semantic_description: str = ""
    preconditions: list[str] = dataclass_field(default_factory=list)
    postconditions: list[str] = dataclass_field(default_factory=list)
    invariants: list[str] = dataclass_field(default_factory=list)
    parameters_snapshot: list[dict[str, Any]] = dataclass_field(default_factory=list)
    #: ``False`` for a revision recorded before ``parameters_snapshot`` joined
    #: ``_ENTITY_FIELDS["Icd"]`` (Task 28c-2). Distinguishes "this revision had
    #: no parameters" from "this revision's parameters were never captured" —
    #: without it, both render as an empty list and the API would answer a
    #: question about revision N with a confident, wrong ``[]``.
    parameters_captured: bool = True
    created_at: dt.datetime | None = None

    @classmethod
    def from_payload(
        cls,
        icd_id: uuid.UUID,
        revision: int,
        payload: dict[str, Any],
        created_at: dt.datetime | None = None,
    ) -> "IcdRevision":
        """Build a revision from a stored ``ArtifactVersion.payload``.

        Every field defaults rather than raising on a missing key: payloads
        written before a field joined ``_ENTITY_FIELDS["Icd"]`` legitimately
        lack it (``parameters_snapshot`` is the first such case), and a
        history reader must not fail on its own older records.

        Args:
            icd_id:     Owning ICD's primary key.
            revision:   Revision number (``ArtifactVersion.revision``).
            payload:    The stored snapshot dict.
            created_at: When the revision was recorded.
        """
        return cls(
            icd_id=icd_id,
            version_number=revision,
            name=payload.get("name") or "",
            direction=payload.get("direction") or IcdDirection.UNIDIRECTIONAL,
            interface_type=payload.get("interface_type") or "",
            semantic_description=payload.get("semantic_description") or "",
            preconditions=list(payload.get("preconditions") or []),
            postconditions=list(payload.get("postconditions") or []),
            invariants=list(payload.get("invariants") or []),
            parameters_snapshot=list(payload.get("parameters_snapshot") or []),
            parameters_captured="parameters_snapshot" in payload,
            created_at=created_at,
        )

    @classmethod
    def from_icd(cls, icd: "Icd") -> "IcdRevision":
        """Build the *current* revision straight off the ICD header."""
        return cls(
            icd_id=icd.pk,
            version_number=icd.current_revision,
            name=icd.name,
            direction=icd.direction,
            interface_type=icd.interface_type,
            semantic_description=icd.semantic_description,
            preconditions=list(icd.preconditions or []),
            postconditions=list(icd.postconditions or []),
            invariants=list(icd.invariants or []),
            parameters_snapshot=icd.parameters_snapshot,
            created_at=icd.modified_at,
        )


# ---------------------------------------------------------------------------
# IcdParameter — structured interface parameter of an ICD's current contract
# REQ-L2-ICD-002 (Design-by-Contract): extends the free-text pre/post/invariant
# JSON lists with structured parameters carrying units, value ranges and
# tolerances.
# ---------------------------------------------------------------------------


class IcdParameter(TenantScopedModel):
    """A single structured parameter of an ICD's current interface contract.

    Numeric bounds live in ``min_value``/``max_value``; symbolic or string
    defaults live in ``nominal_value``; ``tolerance`` stays free text (e.g.
    ``"±5%"`` or ``"0.1"``) as it varies by engineering domain.

    Current-state-only (Datenmodell-Konsolidierung Task 28c-2): a parameter
    belongs to the ICD, not to one of its revisions. Historical parameter sets
    are preserved *by value* in each ``ArtifactVersion`` payload's
    ``parameters_snapshot`` key (see :attr:`Icd.parameters_snapshot`) — the
    same way every other artifact type's fields are captured. The previous
    ``icd_version`` FK never actually delivered per-revision semantics:
    parameter rows have always been mutable in place, and ``update_icd`` never
    carried them forward to the new version.

    leaf_id: COMP-ICD-001
    req_id: REQ-L2-ICD-002
    IF: IF-L1-040 (output to PersistenceLayer)
    """

    icd = models.ForeignKey(
        Icd,
        on_delete=models.CASCADE,
        related_name="parameters",
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
                fields=["icd", "ordering"],
                name="idx_icd_param_icd_order",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"IcdParameter({self.name}, icd={self.icd_id})"


__all__ = [
    "Icd",
    "IcdDirection",
    "IcdParameter",
    "IcdParameterDataType",
    "IcdParameterDirection",
    "IcdRevision",
    "IcdType",
]
