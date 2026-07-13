"""App configuration for ARCH-L1-013 DiagramService."""
from django.apps import AppConfig


class DiagramConfig(AppConfig):
    """ARCH-L1-013 DiagramService — Versioned Diagram Artifact Management.

    Responsibilities:
    - Manages diagrams (block, flow, context — min. 3 types) as standalone,
      versioned artifacts with structured payload (Mermaid, PlantUML, or JSON).
    - Payload validation, immutable versioning, renderable representations.
    - Links diagrams to Requirements/ArchitectureElements via TraceabilityEngine
      with link_type='documents' (IF-L1-034).
    - Accessed from ApplicationService via DiagramFacadeService (IF-L1-032).

    See: docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/L2_DiagramServiceSystem_Architecture.md
    REQ-L1: REQ-L1-027 (Diagram management)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "diagram"
    verbose_name = "ARCH-L1-013 DiagramService"
