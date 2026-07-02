"""
ARCH-L1-013 DiagramService — Mermaid Live Renderer component.

leaf_id: COMP-DS-007_MermaidLiveRenderer
req_id: REQ-L1-057, REQ-L2-DS-007

External interface (incoming):
  IF-L1-059: PUT /api/v1/diagrams/{id}/mermaid-source — Source-Update

Internal interfaces (outgoing):
  IF-DS-INT-007: → COMP-DS-001 (DiagramManager) — persist_mermaid_source
  IF-DS-INT-008: → COMP-DS-003 (DiagramRenderer) — get_render_hints
  IF-DS-INT-009: → COMP-DS-005 (McpArtifactProvider) — register_mcp_type

Responsibilities (REQ-L2-DS-007):
  - Mermaid-Code-Editor mit Live-Preview für 5 Mermaid-Typen
  - 5 Mermaid-Typen: flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram
  - Clientseitiges Rendering (mermaid.js) — ADR-DS-03
  - Fallback: Bei Renderer-Ausfall → Quellcode lesbar als Fallback (AC5/AC9)
  - Performance: <2s Rendering bei 100 Knoten/Kanten
  - Resilienz: Renderer-Failure → Fehlermeldung + Fallback

Design notes:
  This component orchestrates validation (COMP-DS-002), persistence (COMP-DS-001),
  and rendering hints (COMP-DS-003) for Mermaid diagram types.
  It does NOT perform the actual client-side rendering — that happens in the
  frontend using mermaid.js.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from diagram.manager import DiagramManager
from diagram.models import Diagram, DiagramType, PayloadFormat
from diagram.renderer import DiagramRenderer, RenderHints
from diagram.validator import DiagramValidator, ValidationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LivePreviewData:
    """Output contract for get_live_preview_data — IF-L1-061.

    REQ-L2-DS-007: Contains all data needed for the Mermaid live preview.

    Attributes:
        diagram_id:     UUID of the diagram.
        source:         Raw Mermaid source code.
        diagram_type:   Detected Mermaid diagram type (e.g. 'flowchart').
        render_hints:   RenderHints from DiagramRenderer (COMP-DS-003).
        export_data:    Optional SVG/PNG export data (stub — not implemented).
        fallback_mode:  True if renderer failed and fallback is active.
        error_message:  Error message if validation or rendering failed.
    """

    diagram_id: uuid.UUID
    source: str
    diagram_type: str
    render_hints: Optional[RenderHints] = None
    export_data: Optional[dict[str, Any]] = None
    fallback_mode: bool = False
    error_message: str = ""


# ---------------------------------------------------------------------------
# Public interface — COMP-DS-007
# ---------------------------------------------------------------------------

class MermaidLiveRenderer:
    """COMP-DS-007: Mermaid Live Renderer with editor and preview.

    req_id: REQ-L1-057, REQ-L2-DS-007
    leaf_id: COMP-DS-007_MermaidLiveRenderer

    Orchestrates validation, persistence, and rendering hints for Mermaid
    diagram types. Uses dependency injection for collaborators.

    Supported Mermaid types (REQ-L2-DS-007):
      - flowchart (graph)
      - sequenceDiagram
      - classDiagram
      - stateDiagram
      - erDiagram
    """

    # Supported Mermaid diagram types
    SUPPORTED_MERMAID_TYPES: frozenset[str] = frozenset([
        "flowchart",
        "graph",
        "sequenceDiagram",
        "classDiagram",
        "stateDiagram",
        "erDiagram",
    ])

    def __init__(
        self,
        manager: Optional[DiagramManager] = None,
        validator: Optional[DiagramValidator] = None,
        renderer: Optional[DiagramRenderer] = None,
    ) -> None:
        """Initialize with optional collaborator injection (for testing).

        Args:
            manager:   DiagramManager instance (COMP-DS-001).
            validator: DiagramValidator instance (COMP-DS-002).
            renderer:  DiagramRenderer instance (COMP-DS-003).
        """
        self._manager = manager or DiagramManager()
        self._validator = validator or DiagramValidator()
        self._renderer = renderer or DiagramRenderer()

    # ------------------------------------------------------------------
    # IF-L1-059: handle_source_update — Source-Update
    # REQ-L2-DS-007
    # ------------------------------------------------------------------

    def handle_source_update(
        self,
        diagram_id: uuid.UUID,
        source: str,
        tenant: object,
        user: Optional[object] = None,
    ) -> Diagram:
        """Handle Mermaid source update for an existing diagram.

        IF-L1-059 entry point: PUT /api/v1/diagrams/{id}/mermaid-source

        Validates the source, persists via DiagramManager (IF-DS-INT-007),
        and returns the updated Diagram.

        Args:
            diagram_id: UUID of the diagram to update.
            source:     New Mermaid source code.
            tenant:     Active Tenant ORM object.
            user:       Optional User ORM object for audit.

        Returns:
            The updated Diagram ORM object.

        Raises:
            DiagramValidationError: If source validation fails.
            Diagram.DoesNotExist:   If diagram_id not found.
        """
        # Validate source first
        validation = self.validate_mermaid_source(source)
        if not validation.is_valid:
            from diagram.validator import DiagramValidationError
            raise DiagramValidationError(
                f"Mermaid source validation failed: {validation.error_msg}"
            )

        # IF-DS-INT-007: persist via DiagramManager
        return self._manager.update_diagram(
            diagram_id=diagram_id,
            payload_format=PayloadFormat.MERMAID,
            content=source,
            modified_by=user,
        )

    # ------------------------------------------------------------------
    # IF-DS-INT-010: validate_mermaid_source
    # REQ-L2-DS-007
    # ------------------------------------------------------------------

    def validate_mermaid_source(
        self,
        source: str,
        diagram_type: str = "",
    ) -> ValidationResult:
        """Validate Mermaid source code for the 5 supported types.

        Delegates to DiagramValidator.validate_mermaid_source() (IF-DS-INT-010).

        Args:
            source:       Raw Mermaid source code string.
            diagram_type: Optional declared diagram type for cross-check.

        Returns:
            ValidationResult with is_valid, error_msg, line_number, diagram_type.
        """
        return self._validator.validate_mermaid_source(source, diagram_type)

    # ------------------------------------------------------------------
    # IF-L1-061: get_live_preview_data
    # REQ-L2-DS-007
    # ------------------------------------------------------------------

    def get_live_preview_data(
        self,
        diagram_id: uuid.UUID,
    ) -> LivePreviewData:
        """Retrieve all data needed for Mermaid live preview.

        IF-L1-061 output: Source code + Render-Hints + Export data.

        Fetches the diagram from DiagramManager, retrieves render hints from
        DiagramRenderer (IF-DS-INT-008), and packages everything for the frontend.

        Fallback behavior (REQ-L2-DS-007 AC5/AC9):
          If rendering fails (library load error, timeout, CORS), the source
          code is still returned in fallback_mode=True so the frontend can
          display it as readable text.

        Args:
            diagram_id: UUID of the diagram.

        Returns:
            LivePreviewData with source, render_hints, and fallback info.

        Raises:
            Diagram.DoesNotExist: If diagram_id not found.
        """
        try:
            # Fetch diagram via DiagramManager
            result = self._manager.get_diagram(diagram_id)

            if result.version is None:
                return LivePreviewData(
                    diagram_id=diagram_id,
                    source="",
                    diagram_type=result.diagram.diagram_type,
                    fallback_mode=True,
                    error_message="No version available for this diagram.",
                )

            source = result.version.payload
            detected_type = self._detect_mermaid_type(source)

            # IF-DS-INT-008: get render hints
            try:
                render_hints = self._renderer.get_render_hints(
                    diagram_type=result.diagram.diagram_type,
                    payload_format=result.version.payload_format,
                )
            except Exception as exc:
                # REQ-L2-DS-007 AC5/AC9: Fallback on renderer failure
                logger.warning(
                    "Renderer failed for diagram %s: %s. Activating fallback mode.",
                    diagram_id,
                    exc,
                )
                return LivePreviewData(
                    diagram_id=diagram_id,
                    source=source,
                    diagram_type=detected_type,
                    render_hints=None,
                    fallback_mode=True,
                    error_message=f"Renderer error: {exc}",
                )

            # Export data stub (not implemented — see renderer.py)
            export_data = None

            return LivePreviewData(
                diagram_id=diagram_id,
                source=source,
                diagram_type=detected_type,
                render_hints=render_hints,
                export_data=export_data,
                fallback_mode=False,
                error_message="",
            )

        except Exception as exc:
            # Catch-all for unexpected errors — activate fallback
            logger.error(
                "Unexpected error in get_live_preview_data for %s: %s",
                diagram_id,
                exc,
            )
            return LivePreviewData(
                diagram_id=diagram_id,
                source="",
                diagram_type="",
                fallback_mode=True,
                error_message=f"Unexpected error: {exc}",
            )

    # ------------------------------------------------------------------
    # IF-DS-INT-009: register_mermaid_mcp_type
    # REQ-L2-DS-007
    # ------------------------------------------------------------------

    def register_mermaid_mcp_type(self) -> None:
        """Register Mermaid diagram type with MCP artifact provider.

        IF-DS-INT-009: register_mcp_type(diagram_type, payload_format) -> None

        Registers the MERMAID diagram type with PayloadFormat.MERMAID so that
        MCP clients can discover and request Mermaid diagrams.

        This is a no-op in v1 since the MCP artifact provider already supports
        all DiagramType values. The method exists to fulfill the interface
        contract and allow future extensibility.
        """
        # In v1, this is a no-op. The MCP artifact provider (COMP-DS-005)
        # already handles all DiagramType values including MERMAID.
        # Future versions could add type-specific MCP metadata here.
        logger.debug(
            "register_mermaid_mcp_type called — no-op in v1. "
            "DiagramType.MERMAID is already supported by McpArtifactProvider."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_mermaid_type(self, source: str) -> str:
        """Detect the Mermaid diagram type from source code.

        Args:
            source: Raw Mermaid source code.

        Returns:
            Detected diagram type (e.g. 'flowchart', 'sequenceDiagram').
            Returns empty string if detection fails.
        """
        if not source or not source.strip():
            return ""

        first_line = source.strip().splitlines()[0].strip()
        first_token = first_line.split()[0] if first_line else ""
        first_token_lower = first_token.lower()

        # Map keywords to canonical type names
        type_map = {
            "flowchart": "flowchart",
            "graph": "flowchart",
            "sequencediagram": "sequenceDiagram",
            "classdiagram": "classDiagram",
            "statediagram": "stateDiagram",
            "erdiagram": "erDiagram",
        }

        return type_map.get(first_token_lower, "")


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-initialised)
# ---------------------------------------------------------------------------

_mermaid_live_renderer: Optional[MermaidLiveRenderer] = None


def get_mermaid_live_renderer() -> MermaidLiveRenderer:
    """Get or create the module-level MermaidLiveRenderer singleton."""
    global _mermaid_live_renderer
    if _mermaid_live_renderer is None:
        _mermaid_live_renderer = MermaidLiveRenderer()
    return _mermaid_live_renderer


__all__ = [
    "MermaidLiveRenderer",
    "LivePreviewData",
    "get_mermaid_live_renderer",
]
