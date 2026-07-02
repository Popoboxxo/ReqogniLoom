"""
ARCH-L1-013 DiagramService — ORM models.

leaf_id: COMP-DS-001 (DiagramManager), COMP-DS-002 (DiagramValidator),
         COMP-DS-006 (CanvasEditor)
req_id: REQ-L1-027, REQ-L2-DS-001, REQ-L1-056, REQ-L2-DS-006

Entities:
  Diagram        — the mutable header record (name, type, current version pointer)
  DiagramVersion — append-only, immutable payload per change (version N+1)

Both inherit TenantScopedModel (UUID PK, tenant FK, audit fields, TenantManager).

Architecture reference:
  docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/
  L2_DiagramServiceSystem_Architecture.md (IF-L1-035)
"""
from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Diagram (mutable header)
# ---------------------------------------------------------------------------

class Diagram(TenantScopedModel):
    """Mutable header record for a versioned diagram artefact.

    COMP-DS-001 DiagramManager creates and updates Diagram objects.
    Each write operation creates a new DiagramVersion; the current_version
    FK is updated to point at the latest immutable snapshot.

    REQ-L2-DS-001, REQ-L3-DM-001, REQ-L3-DM-002, REQ-L3-DM-003 (IF-L1-035)
    """

    name = models.CharField(max_length=500)
    diagram_type = models.CharField(
        max_length=32,
        choices=DiagramType.choices,
        db_index=True,
    )
    current_version = models.ForeignKey(
        "DiagramVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Optional free-text description for UI / MCP context
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "diagram_diagram"

    def __str__(self) -> str:
        return f"{self.diagram_type}:{self.name}:{self.id}"


# ---------------------------------------------------------------------------
# DiagramVersion (immutable, append-only)
# ---------------------------------------------------------------------------

class DiagramVersion(TenantScopedModel):
    """Immutable payload snapshot for a Diagram.

    One record is created for every write (create / update).  Existing
    records are NEVER modified after creation (REQ-L2-DS-001, REQ-L3-DM-002).

    version_number increments monotonically per diagram (1, 2, 3 …).
    payload holds the raw diagram source (Mermaid string, PlantUML string,
    or a JSON-serialised dict depending on payload_format).

    IF-L1-035 (PersistenceLayer outgoing data)
    """

    diagram = models.ForeignKey(
        Diagram,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField()
    payload_format = models.CharField(
        max_length=16,
        choices=PayloadFormat.choices,
    )
    payload = models.TextField()

    class Meta:
        db_table = "diagram_diagramversion"
        # Composite unique constraint: each (diagram, version_number) must be unique.
        constraints = [
            models.UniqueConstraint(
                fields=["diagram", "version_number"],
                name="uq_diagram_version_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["diagram", "version_number"],
                name="idx_diagramversion_history",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.diagram_id}:v{self.version_number}"


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "Diagram",
    "DiagramVersion",
    "DiagramType",
    "PayloadFormat",
]
