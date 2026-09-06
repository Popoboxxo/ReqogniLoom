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
import math
import uuid
from dataclasses import dataclass
from typing import Optional

from diagram.manager import DiagramManager, DiagramResult
from diagram.models import Diagram, DiagramRevision, DiagramType, PayloadFormat
from diagram.svg_safety import escape_xml_text
from diagram.traceability_connector import TraceabilityConnector
from diagram.validator import DiagramValidator


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
        version:     Current DiagramRevision.
    """

    diagram_id: uuid.UUID
    stroke_data: dict
    svg: str
    version: Optional[DiagramRevision] = None
    # Optional full canvas JSON (e.g. fabric.js). None for legacy versions.
    canvas_json: Optional[dict] = None


# ---------------------------------------------------------------------------
# SVG generation helpers
# ---------------------------------------------------------------------------

def _escape_xml_attr(value: object) -> str:
    """Escape special characters for XML attribute values.

    Delegates to :func:`diagram.svg_safety.escape_xml_text` — the shared,
    format-agnostic implementation also used by
    :mod:`diagram.node_graph_renderer` (GH-353 Task 6), so this stays the
    single source of truth for XML escaping across both SVG export paths.
    """
    return escape_xml_text(value)


def _safe_number(value: object, default: float) -> float:
    """Coerce an untrusted JSON value to a finite number.

    Stroke data originates from user-supplied JSON.  Numeric-role fields
    (coordinates, sizes, opacity, font size) MUST never reach an SVG attribute
    unvalidated: a string value such as ``0" onload="alert(1)`` would otherwise
    break out of the attribute quotes and inject an SVG event handler
    (stored XSS, since the export is rendered for every reader of the diagram).

    Args:
        value:   Untrusted value from the stroke payload.
        default: Fallback used for anything that is not a finite number
                 (strings, None, bool, list, dict, NaN, inf).

    Returns:
        A finite float — never raises.
    """
    if isinstance(value, bool):
        return float(default)
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(number):
        return float(default)
    return number


def _num_attr(value: object, default: float) -> str:
    """Render an untrusted numeric field as a safe SVG attribute value.

    Combines coercion (:func:`_safe_number`) with XML escaping as
    defence-in-depth, so that a future element type cannot reintroduce the
    attribute-injection class of bug by forgetting the coercion step.
    Integral values keep their integer form (``400`` rather than ``400.0``)
    to preserve the historical export format.
    """
    number = _safe_number(value, default)
    if number.is_integer():
        return _escape_xml_attr(int(number))
    return _escape_xml_attr(number)


def _stroke_to_svg_path(points: list[dict]) -> str:
    """Convert a list of {x, y} points to an SVG path 'd' attribute."""
    if not isinstance(points, list) or not points:
        return ""
    coords: list[tuple[str, str]] = []
    for pt in points:
        source = pt if isinstance(pt, dict) else {}
        coords.append(
            (_num_attr(source.get("x", 0), 0), _num_attr(source.get("y", 0), 0))
        )
    parts = [f"M {coords[0][0]} {coords[0][1]}"]
    for x, y in coords[1:]:
        parts.append(f"L {x} {y}")
    return " ".join(parts)


def _element_to_svg(element: dict) -> str:
    """Convert a single canvas element to an SVG element string.

    All values are treated as untrusted: text-role fields are XML-escaped and
    numeric-role fields are coerced to finite numbers (see :func:`_num_attr`).
    """
    if not isinstance(element, dict):
        return ""

    elem_type = element.get("type", "")
    stroke_color = _escape_xml_attr(element.get("color", "#000000"))
    stroke_width = _num_attr(element.get("width", 2), 2)
    fill = _escape_xml_attr(element.get("fill", "none"))
    opacity = _num_attr(element.get("opacity", 1.0), 1.0)

    if elem_type == "pen":
        points = element.get("points", [])
        path_d = _stroke_to_svg_path(points)
        return (
            f'<path d="{_escape_xml_attr(path_d)}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'fill="none" opacity="{opacity}" />'
        )

    if elem_type == "rect":
        x = _num_attr(element.get("x", 0), 0)
        y = _num_attr(element.get("y", 0), 0)
        w = _num_attr(element.get("width", 0), 0)
        h = _num_attr(element.get("height", 0), 0)
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'fill="{fill}" opacity="{opacity}" />'
        )

    if elem_type == "circle":
        cx = _num_attr(element.get("cx", 0), 0)
        cy = _num_attr(element.get("cy", 0), 0)
        r = _num_attr(element.get("r", 0), 0)
        return (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'fill="{fill}" opacity="{opacity}" />'
        )

    if elem_type == "ellipse":
        # Added for the canvas_json full-fidelity path: Fabric's Ellipse has
        # independent rx/ry (unlike the pre-existing "circle" type), used by
        # the rect/ellipse/textbox/connector shape tools (see
        # _canvas_json_object_to_element).
        cx = _num_attr(element.get("cx", 0), 0)
        cy = _num_attr(element.get("cy", 0), 0)
        rx = _num_attr(element.get("rx", 0), 0)
        ry = _num_attr(element.get("ry", 0), 0)
        return (
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'fill="{fill}" opacity="{opacity}" />'
        )

    if elem_type == "line":
        x1 = _num_attr(element.get("x1", 0), 0)
        y1 = _num_attr(element.get("y1", 0), 0)
        x2 = _num_attr(element.get("x2", 0), 0)
        y2 = _num_attr(element.get("y2", 0), 0)
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'opacity="{opacity}" />'
        )

    if elem_type == "text":
        x = _num_attr(element.get("x", 0), 0)
        y = _num_attr(element.get("y", 0), 0)
        content = _escape_xml_attr(element.get("content", ""))
        font_size = _num_attr(element.get("font_size", 16), 16)
        return (
            f'<text x="{x}" y="{y}" '
            f'font-size="{font_size}" fill="{stroke_color}" '
            f'opacity="{opacity}">{content}</text>'
        )

    if elem_type == "arrow":
        x1 = _num_attr(element.get("x1", 0), 0)
        y1 = _num_attr(element.get("y1", 0), 0)
        x2 = _num_attr(element.get("x2", 0), 0)
        y2 = _num_attr(element.get("y2", 0), 0)
        elem_id = _escape_xml_attr(element.get("id", ""))
        return (
            f'<line id="{elem_id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'marker-end="url(#arrowhead)" opacity="{opacity}" />'
        )

    if elem_type == "connector":
        # Connectors are rendered as arrows between source/target shapes.
        # Actual coordinates are resolved at render time from linked shapes.
        x1 = _num_attr(element.get("x1", 0), 0)
        y1 = _num_attr(element.get("y1", 0), 0)
        x2 = _num_attr(element.get("x2", 0), 0)
        y2 = _num_attr(element.get("y2", 0), 0)
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="5,5" marker-end="url(#arrowhead)" '
            f'opacity="{opacity}" />'
        )

    return ""


def _pen_elements(stroke_data: dict) -> list[dict]:
    """Return the `strokes` entries that are full-fidelity today (bugfix helper).

    Root cause (see Task-2 brief / PR #350 follow-up): the frontend's
    `extractStrokeData` maps *every* Fabric object to ``{type: "pen", ...}``
    and only ever populates `points` for genuine freehand `fabric.Path`
    objects — rects, ellipses, textboxes and connectors all end up as
    ``{type: "pen", points: []}`` placeholders in `strokes`. Those
    placeholders render nothing (`_stroke_to_svg_path` returns `""` for an
    empty points list) and are superseded by `canvas_json` (see
    :func:`_canvas_json_object_to_element`); keep only the entries that
    actually carry real freehand geometry.
    """
    if not isinstance(stroke_data, dict):
        return []
    strokes = stroke_data.get("strokes", [])
    if not isinstance(strokes, list):
        return []
    return [
        el
        for el in strokes
        if isinstance(el, dict)
        and el.get("type") == "pen"
        and isinstance(el.get("points"), list)
        and el.get("points")
    ]


# Fabric.js `data.type` discriminators that must never be rendered as their
# own SVG element (see CanvasEditor.tsx createConnector/mouse:down/
# mouse:dblclick for where each is created).
_SKIPPED_CANVAS_JSON_DATA_TYPES = frozenset({"arrowHead", "connectorPreview"})


def _canvas_json_object_to_element(obj: dict) -> Optional[dict]:
    """Map one `canvas_json` (Fabric `toJSON(["data"])`) object to the
    internal element schema consumed by :func:`_element_to_svg`.

    `canvas_json` is the full-fidelity companion to the legacy `strokes`
    array (REQ-L2-CV-005): every rect/ellipse/textbox/connector the Fabric
    canvas editor creates is tagged with a custom `data.type` discriminator
    (`CanvasEditor.tsx`: `data: { id, type, ... }`), which is what this
    function reads to recover the shapes the lossy `strokes` array drops.

    Every value taken from `obj` is untrusted (canvas_json is user-supplied,
    persisted JSON) and is passed through *unmodified* into the returned
    element dict; :func:`_element_to_svg` is the single place that coerces
    numeric-role fields (:func:`_num_attr`) and escapes text-role fields
    (:func:`_escape_xml_attr`) before they reach the SVG string — this
    function performs no rendering-safety work of its own, by design, so the
    PR #351 XSS hardening only has to be maintained in one place.

    Args:
        obj: One entry of `canvas_json["objects"]`.

    Returns:
        An element dict for `_element_to_svg`, or None for object kinds that
        must not be rendered as their own element: arrowhead triangles are
        implied by the connector's own SVG `<marker>` arrowhead, connector
        drag-previews must never be persisted (skipped defensively), and
        freehand pen strokes (Fabric's own `type == "path"`, untagged by
        `data`) are already rendered from `strokes` (see :func:`_pen_elements`)
        since that one object kind was never lossy to begin with.
    """
    if not isinstance(obj, dict):
        return None

    data = obj.get("data")
    data_type = data.get("type") if isinstance(data, dict) else None

    if data_type in _SKIPPED_CANVAS_JSON_DATA_TYPES:
        return None
    if data_type is None and obj.get("type") == "path":
        return None

    scale_x = _safe_number(obj.get("scaleX", 1), 1)
    scale_y = _safe_number(obj.get("scaleY", 1), 1)
    stroke_color = obj.get("stroke", "#000000")
    fill = obj.get("fill", "none")
    opacity = obj.get("opacity", 1.0)

    if data_type == "rect":
        return {
            "type": "rect",
            "x": obj.get("left", 0),
            "y": obj.get("top", 0),
            "width": _safe_number(obj.get("width", 0), 0) * scale_x,
            "height": _safe_number(obj.get("height", 0), 0) * scale_y,
            "color": stroke_color,
            "fill": fill,
            "opacity": opacity,
        }

    if data_type == "ellipse":
        left = _safe_number(obj.get("left", 0), 0)
        top = _safe_number(obj.get("top", 0), 0)
        rx = _safe_number(obj.get("rx", 0), 0) * scale_x
        ry = _safe_number(obj.get("ry", 0), 0) * scale_y
        return {
            "type": "ellipse",
            "cx": left + rx,
            "cy": top + ry,
            "rx": rx,
            "ry": ry,
            "color": stroke_color,
            "fill": fill,
            "opacity": opacity,
        }

    if data_type in ("text", "label"):
        # Text color comes from Fabric's own `fill` property, but defaults to
        # black rather than "none" — the shared `fill` var above defaults to
        # "none", which is correct for rect/ellipse fills but would render
        # invisible text here.
        font_size = _safe_number(obj.get("fontSize", 16), 16) * scale_y
        top = _safe_number(obj.get("top", 0), 0)
        return {
            "type": "text",
            "x": obj.get("left", 0),
            "y": top + font_size,
            "content": obj.get("text", ""),
            "font_size": font_size,
            "color": obj.get("fill", "#000000"),
            "opacity": opacity,
        }

    if data_type == "connector":
        return {
            "type": "connector",
            "x1": obj.get("x1", 0),
            "y1": obj.get("y1", 0),
            "x2": obj.get("x2", 0),
            "y2": obj.get("y2", 0),
            "color": stroke_color,
            "width": obj.get("strokeWidth", 2),
            "opacity": opacity,
        }

    # Unrecognized object kind (future Fabric object types, corrupted or
    # hand-edited payloads, ...): render an explicit placeholder instead of
    # silently dropping the shape (Task-2 "Done when": never a silently
    # empty shape).
    return {
        "type": "text",
        "x": obj.get("left", 0),
        "y": obj.get("top", 0),
        "content": "[preview unavailable]",
        "font_size": 12,
        "color": "#999999",
        "opacity": 1,
    }


def _generate_svg(stroke_data: dict, canvas_json: Optional[dict] = None) -> str:
    """Generate SVG string from canvas stroke data.

    REQ-L2-DS-006: SVG is a derived export format from JSON stroke data.

    The canvas dimensions are attacker-controllable too (stroke data is stored
    user input), so they pass through the same numeric coercion as element
    attributes.

    Args:
        stroke_data:  Canvas stroke data dict with a 'strokes' key (legacy
                      primary format; also carries canvas width/height).
        canvas_json:  Optional full-fidelity Fabric.js canvas serialization
                      (REQ-L2-CV-005). When present and it carries an
                      `objects` list, it — not the lossy `strokes` array —
                      is used to build every rect/ellipse/textbox/connector
                      element; genuine freehand pen strokes are still taken
                      from `strokes` (see :func:`_pen_elements`). Falls back
                      to the legacy `strokes`-only path when absent (e.g.
                      pre-existing rows persisted before REQ-L2-CV-005).
    """
    if not isinstance(stroke_data, dict):
        stroke_data = {}
    width = _num_attr(stroke_data.get("width", 800), 800)
    height = _num_attr(stroke_data.get("height", 600), 600)

    if isinstance(canvas_json, dict) and isinstance(canvas_json.get("objects"), list):
        elements: list[dict] = _pen_elements(stroke_data)
        for obj in canvas_json["objects"]:
            element = _canvas_json_object_to_element(obj)
            if element is not None:
                elements.append(element)
    else:
        strokes = stroke_data.get("strokes", [])
        elements = strokes if isinstance(strokes, list) else []

    elements_svg = "\n  ".join(_element_to_svg(el) for el in elements)

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
        workspace_id: Optional[uuid.UUID] = None,
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
            workspace_id: Owning workspace UUID, used only on create. Without
                it the new Diagram has no backing Artifact and therefore no
                recorded content history at all (Task 28c-2 — Artifact.workspace
                is not nullable). Only the current payload survives; every
                revision list and diff for it comes back empty.

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

        # REQ-L2-CV-005: canvas_json is an optional additive companion to the
        # stroke payload. Keep the persisted stroke payload format stable by
        # excluding canvas_json from it; store canvas_json on its own field.
        canvas_json = stroke_data.get("canvas_json")
        stroke_payload = {
            key: value for key, value in stroke_data.items() if key != "canvas_json"
        }

        # Serialise stroke data to JSON string for persistence
        payload_json = json.dumps(stroke_payload, ensure_ascii=False)

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
                canvas_json=canvas_json,
                workspace_id=workspace_id,
            )
        else:
            # IF-DS-INT-005: update existing canvas diagram (new version)
            self._manager.update_diagram(
                diagram_id=diagram_id,
                payload_format=PayloadFormat.CANVAS_STROKE,
                content=payload_json,
                modified_by=user,
                target_id=target_id,
                canvas_json=canvas_json,
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

    def export_png(self, _stroke_data: dict) -> bytes:
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

        # Parse stroke data from the revision payload
        stroke_data: dict = {}
        if result.version and result.version.payload:
            try:
                stroke_data = json.loads(result.version.payload)
            except json.JSONDecodeError:
                stroke_data = {"strokes": []}

        # REQ-L2-CV-005: surface the optional canvas_json field (None for legacy).
        canvas_json = result.version.canvas_json if result.version else None

        # Generate SVG. When canvas_json is present it is full-fidelity and
        # takes priority over the legacy `strokes` array (see _generate_svg
        # docstring) — this is the Task-2 bugfix: previously every rect,
        # textbox and connector was invisible in the preview because the SVG
        # was always built from `strokes`, which is lossy for anything but
        # genuine freehand pen strokes.
        svg = _generate_svg(stroke_data, canvas_json=canvas_json)

        return CanvasExportResult(
            diagram_id=diagram_id,
            stroke_data=stroke_data,
            svg=svg,
            version=result.version,
            canvas_json=canvas_json,
        )


__all__ = [
    "CanvasEditor",
    "CanvasExportResult",
]
