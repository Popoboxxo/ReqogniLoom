"""
ARCH-L1-013 DiagramService — ORM models.

leaf_id: COMP-DS-001 (DiagramManager), COMP-DS-002 (DiagramValidator),
         COMP-DS-006 (CanvasEditor)
req_id: REQ-L1-027, REQ-L2-DS-001, REQ-L1-056, REQ-L2-DS-006

Entities:
  Diagram        — the diagram record: identity *and* current payload
  DiagramRevision — by-value read model over one recorded content revision

Datenmodell-Konsolidierung Task 28c-2 retired the ``DiagramVersion`` table.
Content history lives in the one shared, append-only snapshot store
(:class:`persistence.models.ArtifactVersion`, Task 27/28a) like every other
artifact type's.

Architecture reference:
  docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/
  L2_DiagramServiceSystem_Architecture.md (IF-L1-035)
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from django.db import models

from persistence.models import TenantScopedModel


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DiagramType(models.TextChoices):
    """Supported diagram types (REQ-L2-DS-002: at least 3 types).

    COMP-DS-002 DiagramValidator uses this enum to route type-specific rules.
    COMP-DS-006 CanvasEditor uses CANVAS for free-hand drawings.
    COMP-DS-007 MermaidLiveRenderer uses MERMAID for all 5 Mermaid diagram types
    (flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram).
    """

    BLOCK = "block", "Block Diagram"
    FLOW = "flow", "Flow Diagram"
    CONTEXT = "context", "Context Diagram"
    CANVAS = "canvas", "Canvas Drawing"
    MERMAID = "mermaid", "Mermaid Diagram"


class PayloadFormat(models.TextChoices):
    """Supported payload serialisation formats.

    COMP-DS-002 uses this to select the correct syntax validator.
    COMP-DS-003 uses this to select the correct renderer hint.
    COMP-DS-006 uses CANVAS_STROKE for canvas stroke data (JSON).
    """

    MERMAID = "mermaid", "Mermaid"
    PLANTUML = "plantuml", "PlantUML"
    JSON = "json", "Structured JSON"
    CANVAS_STROKE = "canvas_stroke", "Canvas Stroke Data (JSON)"
    NODE_GRAPH = "node_graph", "Node Graph (JSON)"


# ---------------------------------------------------------------------------
# Diagram (mutable header)
# ---------------------------------------------------------------------------

class Diagram(TenantScopedModel):
    """A versioned diagram artefact: identity plus its current payload.

    COMP-DS-001 DiagramManager creates and updates Diagram objects. Each write
    overwrites the payload in place and appends a snapshot of it to
    :class:`persistence.models.ArtifactVersion` — the same shape every other
    artifact type uses (Datenmodell-Konsolidierung Task 28c-2, which retired
    the dedicated ``DiagramVersion`` table).

    REQ-L2-DS-001, REQ-L3-DM-001, REQ-L3-DM-002, REQ-L3-DM-003 (IF-L1-035)
    """

    name = models.CharField(max_length=500)
    # Owning workspace (Artifact-scoping). Mirrors the Icd.workspace_id pattern
    # (icd/models.py): a decoupled UUIDField rather than a hard cross-app FK, to
    # avoid coupling the DiagramService to the persistence app's Workspace table.
    # Nullable for backwards-compatible rollout (REQ-173): existing Diagram rows
    # predate workspace scoping and are backfilled per tenant in a later step —
    # see migration 0005 for the Expand/Contract backfill strategy.
    # A single named index is declared in Meta (idx_diagram_workspace) rather
    # than db_index=True here, to avoid a redundant second index on the column.
    workspace_id = models.UUIDField(null=True, blank=True)
    diagram_type = models.CharField(
        max_length=32,
        choices=DiagramType.choices,
        db_index=True,
    )
    # -- Current content (Datenmodell-Konsolidierung Task 28c-1/28c-2) -------
    # DiagramVersion used to be both this subsystem's history store *and* the
    # only place the current payload lived. Task 28a moved the history into
    # persistence.ArtifactVersion, Task 28c-1 added the columns below, and
    # Task 28c-2 made them authoritative and dropped DiagramVersion.
    #
    # `blank=True, default=""` rather than the NOT-NULL shape the version row
    # had: a Diagram that has never been written still has to be representable.
    payload_format = models.CharField(
        max_length=16,
        choices=PayloadFormat.choices,
        blank=True,
        default="",
    )
    payload = models.TextField(blank=True, default="")
    canvas_json = models.JSONField(null=True, blank=True, default=None)
    # Revision number of the content above, in the same numbering space as
    # persistence.ArtifactVersion.revision — diagram.manager allocates the two
    # together, under the same row lock. 0 means "no revision recorded yet",
    # which a workspace-less legacy Diagram stays at forever: Artifact.workspace
    # is not nullable, so it can have no backing Artifact to hang history on.
    current_revision = models.PositiveIntegerField(default=0)
    # Optional free-text description for UI / MCP context
    description = models.TextField(blank=True, default="")
    # Codeberg #353 Task 3 / #392: shadow Artifact side-channel. Diagram is
    # deliberately NOT an Artifact subclass (see traceability_connector.py's
    # module docstring) — this nullable 1:1 FK gives a Diagram a real,
    # persisted Artifact row it can own so it can act as a valid TraceLink
    # endpoint (Artifact.unscoped.get(pk=...) needs a real Artifact row;
    # a bare diagram.id always raised SourceNotFoundError, #392). Lazily
    # created on first use by diagram.traceability_connector._resolve_artifact_id
    # — NOT backfilled for pre-existing rows in this task. on_delete=SET_NULL
    # so deleting the shadow Artifact (e.g. cascade from a TraceLink cleanup)
    # never cascades into deleting the Diagram itself.
    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diagram",
    )

    class Meta:
        db_table = "diagram_diagram"
        indexes = [
            # Workspace scoping index, mirrors idx_icd_workspace (icd/models.py):
            # serves DiagramViewSet workspace-filtered list/resolve queries.
            models.Index(fields=["workspace_id"], name="idx_diagram_workspace"),
        ]

    def __str__(self) -> str:
        return f"{self.diagram_type}:{self.name}:{self.id}"


# ---------------------------------------------------------------------------
# DiagramRevision — by-value read model for one recorded content revision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiagramRevision:
    """One diagram content revision, rehydrated from an ``ArtifactVersion``.

    Datenmodell-Konsolidierung Task 28c-2. Replaces the ``DiagramVersion`` ORM
    row that :func:`diagram.services.list_versions` / ``update_diagram`` /
    :attr:`diagram.manager.DiagramResult.version` used to hand out. It is
    deliberately a plain frozen dataclass, not a model: content history is no
    longer a table of its own, it is a set of JSON snapshots in the one shared
    :class:`persistence.models.ArtifactVersion` store, and rehydrating them
    into an ORM instance would invite callers to ``save()`` a row that has no
    table behind it.

    The attribute names match the ones the retired ``DiagramVersion`` exposed,
    so every ``version.payload`` / ``version.version_number`` reader keeps
    working unchanged.
    """

    diagram_id: uuid.UUID
    version_number: int
    payload_format: str = ""
    payload: str = ""
    canvas_json: Optional[dict] = None
    created_at: Optional[dt.datetime] = None

    @classmethod
    def from_payload(
        cls,
        diagram_id: uuid.UUID,
        revision: int,
        payload: dict[str, Any],
        created_at: Optional[dt.datetime] = None,
    ) -> "DiagramRevision":
        """Build a revision from a stored ``ArtifactVersion.payload``.

        Keys default rather than raising: a snapshot written before a field
        joined ``artifact_diff_service._ENTITY_FIELDS["Diagram"]`` legitimately
        lacks it, and a history reader must not fail on its own older records.
        """
        return cls(
            diagram_id=diagram_id,
            version_number=revision,
            payload_format=payload.get("payload_format") or "",
            payload=payload.get("payload") or "",
            canvas_json=payload.get("canvas_json"),
            created_at=created_at,
        )

    @classmethod
    def from_diagram(cls, diagram: Diagram) -> "DiagramRevision":
        """Build the *current* revision straight off the Diagram row."""
        return cls(
            diagram_id=diagram.pk,
            version_number=diagram.current_revision,
            payload_format=diagram.payload_format,
            payload=diagram.payload,
            canvas_json=diagram.canvas_json,
            created_at=diagram.modified_at,
        )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "Diagram",
    "DiagramRevision",
    "DiagramType",
    "PayloadFormat",
]
