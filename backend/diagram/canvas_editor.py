"""
ARCH-L1-013 DiagramService — CanvasEditor component.

leaf_id: COMP-DS-006_CanvasEditor
req_id: REQ-L1-056, REQ-L2-DS-006

External interfaces:
  IF-L1-058 (input):  Canvas Auto-Save Push (JSON stroke data, max 5s interval)
  IF-L1-060 (output): Canvas Stroke-Daten (JSON) + SVG/PNG Export

Internal interfaces (outgoing):
  IF-DS-INT-004: CanvasEditor → DiagramValidator
                 validate_canvas_strokes(stroke_data) -> ValidationResult
  IF-DS-INT-005: CanvasEditor → DiagramManager
                 persist_canvas(name, stroke_data, tenant, user) -> Diagram
  IF-DS-INT-006: CanvasEditor → TraceabilityConnector
                 link_canvas_to_artifact(diagram_id, target_id) -> TraceLink

Manages Free-Hand Canvas diagrams.  JSON stroke data is the primary format
(versioned, diff-able); SVG is a derived export format.  Auto-Save persists
stroke data via DiagramManager (COMP-DS-001) with immutable versioning.

Performance: ≥30fps at 500 stroke elements + 100 shapes (REQ-L2-DS-006).
Resilience: Auto-Save ≤5s interval, max 5s data loss on browser crash.

Design notes (ADR-DS-04):
  JSON stroke data is the primary format — diff-able, versionable, compact.
  SVG export is derived from stroke data on demand.
  PNG export is a client-side operation (Canvas.toDataURL) — backend provides
  only a stub.

Architecture reference:
  docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/
  L2_DiagramServiceSystem_Architecture.md (COMP-DS-006)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from diagram.manager import DiagramManager, DiagramResult
from diagram.models import Diagram, DiagramType, DiagramVersion, PayloadFormat
from diagram.traceability_connector import TraceabilityConnector
from diagram.validator import DiagramValidator, ValidationResult


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CanvasExportResult:
    """Output contract for IF-L1-060 (canvas export).

    Attributes:
        diagram_id:  UUID of the canvas diagram.
        stroke_data: JSON-serialised stroke data (primary format).
        svg:         SVG string (derived export format).
        version:     Current DiagramVersion.
    """

    diagram_id: uuid.UUID
    stroke_data: dict
    svg: str
    version: Optional[DiagramVersion] = None


# ---------------------------------------------------------------------------
# SVG generation helpers
# ---------------------------------------------------------------------------

def _escape_xml_attr(value: str) -> str:
    """Escape special characters for XML attribute values."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _stroke_to_svg_path(points: list[dict]) -> str:
    """Convert a list of {x, y} points to an SVG path 'd' attribute."""
    if not points:
        return ""
    parts = [f"M {points[0].get('x', 0)} {points[0].get('y', 0)}"]
    for pt in points[1:]:
        parts.append(f"L {pt.get('x', 0)} {pt.get('y', 0)}")
    return " ".join(parts)


def _element_to_svg(element: dict) -> str:
    """Convert a single canvas element to an SVG element string."""
    elem_type = element.get("type", "")
    stroke_color = _escape_xml_attr(element.get("color", "#000000"))
    stroke_width = element.get("width", 2)
    fill = _escape_xml_attr(element.get("fill", "none"))
    opacity = element.get("opacity", 1.0)

    if elem_type == "pen":
        points = element.get("points", [])
        path_d = _stroke_to_svg_path(points)
        return (
            f'<path d="{_escape_xml_attr(path_d)}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'fill="none" opacity="{opacity}" />'
        )

    if elem_type == "rect":
        x = element.get("x", 0)
        y = element.get("y", 0)
        w = element.get("width", 0)
        h = element.get("height", 0)
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'fill="{fill}" opacity="{opacity}" />'
        )

    if elem_type == "circle":
        cx = element.get("cx", 0)
        cy = element.get("cy", 0)
        r = element.get("r", 0)
        return (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'fill="{fill}" opacity="{opacity}" />'
        )

    if elem_type == "line":
        x1 = element.get("x1", 0)
        y1 = element.get("y1", 0)
        x2 = element.get("x2", 0)
        y2 = element.get("y2", 0)
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'opacity="{opacity}" />'
        )

    if elem_type == "text":
        x = element.get("x", 0)
        y = element.get("y", 0)
        content = _escape_xml_attr(element.get("content", ""))
        font_size = element.get("font_size", 16)
        return (
            f'<text x="{x}" y="{y}" '
            f'font-size="{font_size}" fill="{stroke_color}" '
            f'opacity="{opacity}">{content}</text>'
        )

    if elem_type == "arrow":
        x1 = element.get("x1", 0)
        y1 = element.get("y1", 0)
        x2 = element.get("x2", 0)
        y2 = element.get("y2", 0)
        elem_id = _escape_xml_attr(element.get("id", ""))
        return (
            f'<line id="{elem_id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'marker-end="url(#arrowhead)" opacity="{opacity}" />'
        )

    if elem_type == "connector":
        # Connectors are rendered as arrows between source/target shapes.
        # Actual coordinates are resolved at render time from linked shapes.
        x1 = element.get("x1", 0)
        y1 = element.get("y1", 0)
        x2 = element.get("x2", 0)
        y2 = element.get("y2", 0)
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="5,5" marker-end="url(#arrowhead)" '
            f'opacity="{opacity}" />'
        )

    return ""


def _generate_svg(stroke_data: dict) -> str:
    """Generate SVG string from canvas stroke data.

    REQ-L2-DS-006: SVG is a derived export format from JSON stroke data.
    """
    strokes = stroke_data.get("strokes", [])
    width = stroke_data.get("width", 800)
    height = stroke_data.get("height", 600)

    elements_svg = "\n  ".join(_element_to_svg(el) for el in strokes)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'  <defs>\n'
        f'    <marker id="arrowhead" markerWidth="10" markerHeight="7" '
        f'refX="10" refY="3.5" orient="auto">\n'
        f'      <polygon points="0 0, 10 3.5, 0 7" fill="#000000" />\n'
        f'    </marker>\n'
        f'  </defs>\n'
        f'  {elements_svg}\n'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# CanvasEditor — COMP-DS-006
# ---------------------------------------------------------------------------

class CanvasEditor:
    """COMP-DS-006: Manages Free-Hand Canvas diagrams.

    req_id: REQ-L1-056, REQ-L2-DS-006
    leaf_id: COMP-DS-006_CanvasEditor

    Wires together DiagramValidator (IF-DS-INT-004), DiagramManager (IF-DS-INT-005)
    and TraceabilityConnector (IF-DS-INT-006) via registered internal interfaces.

    Auto-Save (IF-L1-058): Frontend pushes stroke data at max 5s intervals.
    Export (IF-L1-060): Returns JSON stroke data + SVG export.
    """

    def __init__(
        self,
        validator: Optional[DiagramValidator] = None,
        manager: Optional[DiagramManager] = None,
        traceability: Optional[TraceabilityConnector] = None,
    ) -> None:
        self._validator = validator or DiagramValidator()
        self._manager = manager or DiagramManager()
        self._traceability = traceability or TraceabilityConnector()

    # ------------------------------------------------------------------
    # IF-L1-058 / IF-DS-INT-004 + IF-DS-INT-005: handle_stroke_update
    # REQ-L2-DS-006: Auto-Save
    # ------------------------------------------------------------------

    def handle_stroke_update(
        self,
        diagram_id: Optional[uuid.UUID],
        stroke_data: dict,
        tenant: object,
        user: Optional[object] = None,
        name: str = "Canvas Drawing",
        target_id: Optional[uuid.UUID] = None,
    ) -> Diagram:
        """Validate and persist canvas stroke data (Auto-Save entry point).

        IF-L1-058 contract: receives JSON stroke data from frontend.
        IF-DS-INT-004: validates stroke data via DiagramValidator.
        IF-DS-INT-005: persists via DiagramManager (create or update).
        IF-DS-INT-006: optionally creates TraceLink if target_id is given.

        Args:
            diagram_id: UUID of existing diagram (update), or None (create).
            stroke_data: Canvas stroke data dict with 'strokes' key.
            tenant:      Active Tenant ORM object.
            user:        Optional User ORM object for audit.
            name:        Diagram name (used only on create).
            target_id:   Optional target Artifact UUID for TraceLink creation.

        Returns:
            The created or updated Diagram ORM object.

        Raises:
            DiagramValidationError: If stroke data fails validation (IF-DS-INT-004).
        """
        # IF-DS-INT-004: validate stroke data
        result = self._validator.validate_canvas_strokes(stroke_data)
        if not result.is_valid:
            from diagram.validator import DiagramValidationError
            raise DiagramValidationError(
                f"Canvas stroke validation failed: {result.error_msg}"
            )

        # Serialise stroke data to JSON string for persistence
        payload_json = json.dumps(stroke_data, ensure_ascii=False)

        if diagram_id is None:
            # IF-DS-INT-005: create new canvas diagram
            diagram = self._manager.create_diagram(
                name=name,
                diagram_type=DiagramType.CANVAS,
                payload_format=PayloadFormat.CANVAS_STROKE,
                content=payload_json,
                tenant=tenant,
                created_by=user,
                target_id=target_id,
            )
        else:
            # IF-DS-INT-005: update existing canvas diagram (new version)
            self._manager.update_diagram(
                diagram_id=diagram_id,
                payload_format=PayloadFormat.CANVAS_STROKE,
                content=payload_json,
                modified_by=user,
                target_id=target_id,
            )
            diagram = Diagram.objects.get(id=diagram_id)

        return diagram

    # ------------------------------------------------------------------
    # IF-DS-INT-006: link_canvas_to_artifact
    # REQ-L2-DS-006: TraceLink
    # ------------------------------------------------------------------

    def link_canvas_to_artifact(
        self,
        diagram_id: uuid.UUID,
        target_id: uuid.UUID,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> object:
        """Create a 'documents' TraceLink between a canvas and a target artifact.

        IF-DS-INT-006 contract: link_canvas_to_artifact(diagram_id, target_id) -> TraceLink

        Args:
            diagram_id:    UUID of the canvas Diagram.
            target_id:     UUID of the target Artifact.
            created_by_id: Optional actor UUID for audit.

        Returns:
            The created TraceLink ORM object.

        Raises:
            TraceLinkError: If TraceabilityEngine rejects the link.
        """
        return self._traceability.create_document_link(
            diagram_id=diagram_id,
            target_id=target_id,
            created_by_id=created_by_id,
        )

    # ------------------------------------------------------------------
    # IF-L1-060: export_svg
    # REQ-L2-DS-006: SVG Export
    # ------------------------------------------------------------------

    def export_svg(self, stroke_data: dict) -> str:
        """Convert canvas stroke data to SVG string.

        IF-L1-060 contract: SVG export from JSON stroke data.

        Args:
            stroke_data: Canvas stroke data dict with 'strokes' key.

        Returns:
            SVG string representing the canvas content.
        """
        return _generate_svg(stroke_data)

    # ------------------------------------------------------------------
    # IF-L1-060: export_png
    # REQ-L2-DS-006: PNG Export (stub — client-side)
    # ------------------------------------------------------------------

    def export_png(self, stroke_data: dict) -> bytes:
        """Stub: PNG export is a client-side operation.

        REQ-L2-DS-006: PNG export happens client-side via Canvas.toDataURL().
        The backend does not generate PNG binaries.

        Raises:
            NotImplementedError: Always. PNG export is client-side.
        """
        raise NotImplementedError(
            "PNG export is a client-side operation (Canvas.toDataURL). "
            "Use the SVG export or stroke data for server-side rendering. "
            "See ADR-DS-04: JSON stroke data is the primary format."
        )

    # ------------------------------------------------------------------
    # IF-L1-060: get_canvas
    # REQ-L2-DS-006: Canvas retrieval + export data
    # ------------------------------------------------------------------

    def get_canvas(
        self,
        diagram_id: uuid.UUID,
        version_number: Optional[int] = None,
    ) -> CanvasExportResult:
        """Retrieve a canvas diagram with stroke data and SVG export.

        IF-L1-060 contract: returns JSON stroke data + SVG export.

        Args:
            diagram_id:     UUID of the canvas diagram.
            version_number: Optional specific version. Defaults to current.

        Returns:
            CanvasExportResult with stroke_data, svg, and version info.

        Raises:
            Diagram.DoesNotExist: If diagram_id not found.
        """
        result: DiagramResult = self._manager.get_diagram(
            diagram_id=diagram_id,
            version_number=version_number,
        )

        # Parse stroke data from the version payload
        stroke_data: dict = {}
        if result.version and result.version.payload:
            try:
                stroke_data = json.loads(result.version.payload)
            except json.JSONDecodeError:
                stroke_data = {"strokes": []}

        # Generate SVG from stroke data
        svg = _generate_svg(stroke_data)

        return CanvasExportResult(
            diagram_id=diagram_id,
            stroke_data=stroke_data,
            svg=svg,
            version=result.version,
        )


__all__ = [
    "CanvasEditor",
    "CanvasExportResult",
]
