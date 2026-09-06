"""
COMP-DS-006 CanvasEditor — Unit and integration tests.

leaf_id: COMP-DS-006_CanvasEditor
req_id: REQ-L1-056, REQ-L2-DS-006

Covers:
  REQ-L2-DS-006 AC1: Canvas diagram persisted as JSON stroke data (primary format).
  REQ-L2-DS-006 AC2: SVG export generated from stroke data.
  REQ-L2-DS-006 AC3: Auto-Save with max 5s interval (persistence path tested).
  REQ-L2-DS-006 AC5: TraceLink (type 'documents') creation.
  REQ-L2-DS-006 AC6: MCP artifact.get returns canvas payload.

  IF-DS-INT-004: validate_canvas_strokes(stroke_data) -> ValidationResult
  IF-DS-INT-005: persist_canvas(name, stroke_data, tenant, user) -> Diagram
  IF-DS-INT-006: link_canvas_to_artifact(diagram_id, target_id) -> TraceLink

  Validation: valid/invalid stroke data, element types, max elements, max points.
  Auto-Save: create + update via DiagramManager.
  SVG Export: structural validation of generated SVG.
  TraceLink: creation via TraceabilityConnector mock.
"""
from __future__ import annotations

import json
import uuid
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from diagram.canvas_editor import CanvasEditor, CanvasExportResult, _generate_svg
from diagram.models import Diagram, DiagramType, PayloadFormat
from diagram.tests.conftest import (
    VALID_CANVAS_CONNECTORS,
    VALID_CANVAS_STROKES,
    active_tenant,
)
from diagram.validator import DiagramValidator, DiagramValidationError, ValidationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def validator() -> DiagramValidator:
    return DiagramValidator()


@pytest.fixture
def canvas_editor() -> CanvasEditor:
    return CanvasEditor()


# ---------------------------------------------------------------------------
# IF-DS-INT-004: Canvas stroke validation — valid data
# ---------------------------------------------------------------------------

class TestCanvasStrokeValidationValid:
    """REQ-L2-DS-006: Valid stroke data passes validation."""

    def test_valid_strokes_pass(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes(VALID_CANVAS_STROKES)
        assert result.is_valid is True
        assert result.error_msg == ""
        assert result.diagram_type == "canvas"

    def test_valid_connectors_pass(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes(VALID_CANVAS_CONNECTORS)
        assert result.is_valid is True

    def test_empty_strokes_array_pass(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({"strokes": []})
        assert result.is_valid is True

    def test_all_element_types_valid(self, validator: DiagramValidator) -> None:
        """Each valid element type individually passes validation."""
        for elem_type in ["pen", "rect", "circle", "line", "text", "arrow", "connector"]:
            element = _make_element(elem_type)
            result = validator.validate_canvas_strokes({"strokes": [element]})
            assert result.is_valid is True, f"Element type '{elem_type}' should be valid"

    def test_pen_stroke_with_many_points(self, validator: DiagramValidator) -> None:
        """Pen stroke with 1000 points (well under 10000 limit)."""
        points = [{"x": i, "y": i} for i in range(1000)]
        data = {"strokes": [{"type": "pen", "points": points}]}
        result = validator.validate_canvas_strokes(data)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# IF-DS-INT-004: Canvas stroke validation — invalid data
# ---------------------------------------------------------------------------

class TestCanvasStrokeValidationInvalid:
    """REQ-L2-DS-006: Invalid stroke data fails validation with error detail."""

    def test_non_dict_raises(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes("not a dict")
        assert result.is_valid is False
        assert "must be a JSON object" in result.error_msg

    def test_missing_strokes_key(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({"data": []})
        assert result.is_valid is False
        assert "'strokes' key" in result.error_msg

    def test_strokes_not_a_list(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({"strokes": "not a list"})
        assert result.is_valid is False
        assert "must be a JSON array" in result.error_msg

    def test_exceeds_max_elements(self, validator: DiagramValidator) -> None:
        elements = [{"type": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1}] * 1001
        result = validator.validate_canvas_strokes({"strokes": elements})
        assert result.is_valid is False
        assert "exceeding maximum" in result.error_msg

    def test_element_not_a_dict(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({"strokes": ["not a dict"]})
        assert result.is_valid is False
        assert "must be a JSON object" in result.error_msg

    def test_missing_type_field(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({"strokes": [{"x": 1}]})
        assert result.is_valid is False
        assert "missing required 'type'" in result.error_msg

    def test_invalid_element_type(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [{"type": "triangle"}],
        })
        assert result.is_valid is False
        assert "invalid type" in result.error_msg

    def test_rect_missing_fields(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [{"type": "rect", "x": 0, "y": 0}],  # missing width, height
        })
        assert result.is_valid is False
        assert "missing" in result.error_msg.lower()

    def test_circle_missing_radius(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [{"type": "circle", "cx": 0, "cy": 0}],  # missing r
        })
        assert result.is_valid is False
        assert "missing" in result.error_msg.lower()

    def test_text_missing_content(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [{"type": "text", "x": 0, "y": 0}],  # missing content
        })
        assert result.is_valid is False
        assert "missing" in result.error_msg.lower()

    def test_connector_missing_source_target(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [{"type": "connector"}],  # missing source_id, target_id
        })
        assert result.is_valid is False
        assert "missing" in result.error_msg.lower()

    def test_pen_stroke_exceeds_max_points(self, validator: DiagramValidator) -> None:
        points = [{"x": i, "y": i} for i in range(10_001)]
        data = {"strokes": [{"type": "pen", "points": points}]}
        result = validator.validate_canvas_strokes(data)
        assert result.is_valid is False
        assert "exceeding maximum" in result.error_msg

    def test_error_includes_element_index(self, validator: DiagramValidator) -> None:
        """Validation error reports the element index (line_number)."""
        data = {
            "strokes": [
                {"type": "rect", "x": 0, "y": 0, "width": 10, "height": 10},
                {"type": "invalid_type"},
            ],
        }
        result = validator.validate_canvas_strokes(data)
        assert result.is_valid is False
        assert result.line_number == 1


# ---------------------------------------------------------------------------
# GH-352: numeric-role field type validation
# ---------------------------------------------------------------------------

class TestCanvasStrokeFieldTypeValidation:
    """GH-352: numeric-role fields must actually contain numbers.

    _validate_canvas_strokes() now delegates to CanvasStrokeElementSerializer
    (the same DRF serializer used by the dedicated canvas-strokes/ endpoint)
    so malformed types can no longer be silently persisted via the generic
    /api/v1/diagrams/ intake path.
    """

    def test_rect_non_numeric_width_rejected(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [
                {"type": "rect", "x": 0, "y": 0, "width": "not-a-number", "height": 10},
            ],
        })
        assert result.is_valid is False
        assert "width" in result.error_msg

    def test_rect_non_numeric_x_rejected(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [
                {"type": "rect", "x": [1, 2], "y": 0, "width": 10, "height": 10},
            ],
        })
        assert result.is_valid is False
        assert "x" in result.error_msg

    def test_circle_non_numeric_radius_rejected(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [
                {"type": "circle", "cx": 0, "cy": 0, "r": {"nested": "object"}},
            ],
        })
        assert result.is_valid is False
        assert "r" in result.error_msg

    def test_text_non_numeric_font_size_rejected(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [
                {"type": "text", "x": 0, "y": 0, "content": "hi", "font_size": "large"},
            ],
        })
        assert result.is_valid is False
        assert "font_size" in result.error_msg

    def test_line_non_numeric_coordinates_rejected(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [
                {"type": "line", "x1": "a", "y1": 0, "x2": 1, "y2": 1},
            ],
        })
        assert result.is_valid is False
        assert "x1" in result.error_msg

    def test_opacity_non_numeric_rejected(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes({
            "strokes": [
                {
                    "type": "rect",
                    "x": 0,
                    "y": 0,
                    "width": 10,
                    "height": 10,
                    "opacity": "transparent",
                },
            ],
        })
        assert result.is_valid is False
        assert "opacity" in result.error_msg

    def test_valid_typed_fields_still_pass(self, validator: DiagramValidator) -> None:
        """Sanity check: well-typed numeric fields keep passing (no regression)."""
        result = validator.validate_canvas_strokes(VALID_CANVAS_STROKES)
        assert result.is_valid is True

    def test_valid_connectors_still_pass(self, validator: DiagramValidator) -> None:
        result = validator.validate_canvas_strokes(VALID_CANVAS_CONNECTORS)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# IF-DS-INT-005: Auto-Save persistence — create
# ---------------------------------------------------------------------------

pytestmark_django = pytest.mark.django_db


class TestCanvasAutoSaveCreate:
    """REQ-L2-DS-006 AC1: Canvas diagram persisted as JSON stroke data."""

    def test_create_canvas_diagram(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                name="Test Canvas",
                workspace_id=workspace_a.id,
            )

        assert diagram.id is not None
        assert diagram.diagram_type == DiagramType.CANVAS
        assert diagram.name == "Test Canvas"

    def test_create_persists_canvas_stroke_format(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

        assert diagram.current_revision == 1
        assert diagram.payload_format == PayloadFormat.CANVAS_STROKE

    def test_create_persists_json_payload(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

        payload = json.loads(diagram.payload)
        assert "strokes" in payload
        assert len(payload["strokes"]) == 3

    def test_create_invalid_strokes_raises(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            with pytest.raises(DiagramValidationError):
                canvas_editor.handle_stroke_update(
                    diagram_id=None,
                    stroke_data={"strokes": [{"type": "invalid"}]},
                    tenant=tenant_a,
                    workspace_id=workspace_a.id,
                )

    def test_create_writes_audit_log(self, canvas_editor, tenant_a, workspace_a):
        with patch("diagram.manager.log_write") as mock_log:
            with active_tenant(tenant_a):
                canvas_editor.handle_stroke_update(
                    diagram_id=None,
                    stroke_data=VALID_CANVAS_STROKES,
                    tenant=tenant_a,
                    workspace_id=workspace_a.id,
                )

        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["operation"] == "create"


# ---------------------------------------------------------------------------
# IF-DS-INT-005: Auto-Save persistence — update
# ---------------------------------------------------------------------------

class TestCanvasAutoSaveUpdate:
    """REQ-L2-DS-006 AC3: Auto-Save creates new version on update."""

    def _make_canvas(self, canvas_editor, tenant_a, workspace_a):
        return canvas_editor.handle_stroke_update(
            diagram_id=None,
            stroke_data=VALID_CANVAS_STROKES,
            tenant=tenant_a,
            name="Auto-Save Test",
            workspace_id=workspace_a.id,
        )

    def test_update_creates_new_version(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_canvas(canvas_editor, tenant_a, workspace_a)
            updated = canvas_editor.handle_stroke_update(
                diagram_id=diagram.id,
                stroke_data={
                    "strokes": VALID_CANVAS_STROKES["strokes"] + [
                        {"type": "circle", "cx": 300, "cy": 300, "r": 50},
                    ],
                    "width": 800,
                    "height": 600,
                },
                tenant=tenant_a,
            )

        assert updated.current_revision == 2

    def test_update_old_version_unchanged(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_canvas(canvas_editor, tenant_a, workspace_a)
            original_payload = diagram.payload

            canvas_editor.handle_stroke_update(
                diagram_id=diagram.id,
                stroke_data={"strokes": [], "width": 800, "height": 600},
                tenant=tenant_a,
            )
            # Task 28c-2: revision 1 is an ArtifactVersion snapshot now.
            old_version = _revision_payload(diagram, 1)

        assert old_version["payload"] == original_payload


# ---------------------------------------------------------------------------
# IF-L1-060: SVG Export
# ---------------------------------------------------------------------------

class TestSVGExport:
    """REQ-L2-DS-006 AC2: SVG export generated from stroke data."""

    def test_svg_export_returns_string(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(VALID_CANVAS_STROKES)
        assert isinstance(svg, str)
        assert len(svg) > 0

    def test_svg_contains_svg_root(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(VALID_CANVAS_STROKES)
        assert "<svg" in svg
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg

    def test_svg_contains_rect_element(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(VALID_CANVAS_STROKES)
        assert "<rect" in svg

    def test_svg_contains_path_for_pen(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(VALID_CANVAS_STROKES)
        assert "<path" in svg

    def test_svg_contains_text_element(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(VALID_CANVAS_STROKES)
        assert "<text" in svg
        assert "Hello Canvas" in svg

    def test_svg_contains_arrowhead_marker(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(VALID_CANVAS_CONNECTORS)
        assert "arrowhead" in svg

    def test_svg_contains_connector_dash(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(VALID_CANVAS_CONNECTORS)
        assert "stroke-dasharray" in svg

    def test_svg_empty_strokes(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg({"strokes": [], "width": 400, "height": 300})
        assert "<svg" in svg
        assert 'width="400"' in svg

    def test_png_export_not_implemented(self, canvas_editor: CanvasEditor) -> None:
        with pytest.raises(NotImplementedError, match="client-side"):
            canvas_editor.export_png(VALID_CANVAS_STROKES)


# ---------------------------------------------------------------------------
# Security: SVG attribute injection (stored XSS) — REQ-L2-DS-006 AC2
# ---------------------------------------------------------------------------

# Payload that breaks out of an SVG attribute value and injects an event
# handler if a numeric-role field is interpolated without coercion/escaping.
XSS_ATTR_PAYLOAD = '0" onload="alert(1)'

# Every numeric-role field per element type, mapped to the attacker payload.
_NUMERIC_FIELD_CASES: list[dict] = [
    {"type": "rect", "x": 0, "y": 0, "width": XSS_ATTR_PAYLOAD, "height": 10},
    {"type": "rect", "x": XSS_ATTR_PAYLOAD, "y": XSS_ATTR_PAYLOAD,
     "width": 10, "height": XSS_ATTR_PAYLOAD},
    {"type": "circle", "cx": XSS_ATTR_PAYLOAD, "cy": XSS_ATTR_PAYLOAD,
     "r": XSS_ATTR_PAYLOAD},
    {"type": "line", "x1": XSS_ATTR_PAYLOAD, "y1": XSS_ATTR_PAYLOAD,
     "x2": XSS_ATTR_PAYLOAD, "y2": XSS_ATTR_PAYLOAD},
    {"type": "arrow", "x1": XSS_ATTR_PAYLOAD, "y1": XSS_ATTR_PAYLOAD,
     "x2": XSS_ATTR_PAYLOAD, "y2": XSS_ATTR_PAYLOAD},
    {"type": "connector", "x1": XSS_ATTR_PAYLOAD, "y1": XSS_ATTR_PAYLOAD,
     "x2": XSS_ATTR_PAYLOAD, "y2": XSS_ATTR_PAYLOAD},
    {"type": "text", "x": XSS_ATTR_PAYLOAD, "y": XSS_ATTR_PAYLOAD,
     "content": "hi", "font_size": XSS_ATTR_PAYLOAD},
    {"type": "pen", "points": [{"x": XSS_ATTR_PAYLOAD, "y": 0}, {"x": 1, "y": 2}]},
    # Shared fields present on every element type.
    {"type": "rect", "width": 1, "height": 1,
     "stroke_width": XSS_ATTR_PAYLOAD, "opacity": XSS_ATTR_PAYLOAD},
    # Non-string, non-numeric JSON types must not crash or leak either.
    {"type": "rect", "x": None, "y": [1, 2], "width": {"a": 1}, "height": True},
]


def _assert_no_attribute_breakout(svg: str) -> None:
    """Fail if the SVG contains an injected element/attribute.

    Parsing is the authoritative check: a payload that broke out of its
    attribute quotes shows up as an *additional parsed attribute* (or an extra
    element), whereas a properly escaped payload stays a single inert attribute
    value no matter what characters it contains.
    """
    # No DTD may reach the parser (guards XXE / entity expansion); the export
    # never emits one, so this doubles as an assertion about the generator.
    assert "<!DOCTYPE" not in svg
    assert "<!ENTITY" not in svg
    root = ET.fromstring(svg)
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        assert tag != "script", f"injected <script> element: {svg}"
        for name, value in node.attrib.items():
            assert not name.lower().startswith(
                "on"
            ), f"injected event handler attribute {name!r}: {svg}"
            assert not value.strip().lower().startswith(
                "javascript:"
            ), f"injected javascript: URL in {name!r}: {svg}"


class TestSVGAttributeInjection:
    """Stroke data is untrusted input; SVG export must never inject attributes.

    Regression guard for the stored-XSS vector where a string value in a
    numeric-role field (e.g. ``{"width": '0" onload="alert(1)'}``) escaped its
    attribute and injected an SVG event handler.  The generated SVG is rendered
    for every reader of the diagram, so this was cross-user, not self-XSS.
    """

    @pytest.mark.parametrize("element", _NUMERIC_FIELD_CASES)
    def test_numeric_fields_reject_attribute_injection(
        self, canvas_editor: CanvasEditor, element: dict
    ) -> None:
        svg = canvas_editor.export_svg(
            {"strokes": [element], "width": 800, "height": 600}
        )
        _assert_no_attribute_breakout(svg)
        # Numeric-role fields are coerced, so the payload is dropped entirely —
        # not even an escaped remnant survives.
        assert "onload" not in svg.lower()

    def test_canvas_dimensions_reject_attribute_injection(
        self, canvas_editor: CanvasEditor
    ) -> None:
        svg = canvas_editor.export_svg(
            {"strokes": [], "width": XSS_ATTR_PAYLOAD, "height": XSS_ATTR_PAYLOAD}
        )
        _assert_no_attribute_breakout(svg)
        # Falls back to the documented defaults.
        assert 'width="800"' in svg
        assert 'height="600"' in svg

    def test_text_fields_stay_escaped(self, canvas_editor: CanvasEditor) -> None:
        svg = canvas_editor.export_svg(
            {
                "strokes": [
                    {
                        "type": "text",
                        "x": 1,
                        "y": 2,
                        "content": '</text><script>alert(1)</script>',
                        "color": XSS_ATTR_PAYLOAD,
                        "fill": XSS_ATTR_PAYLOAD,
                        "id": XSS_ATTR_PAYLOAD,
                    }
                ],
                "width": 100,
                "height": 100,
            }
        )
        _assert_no_attribute_breakout(svg)

    def test_valid_numeric_values_are_preserved(
        self, canvas_editor: CanvasEditor
    ) -> None:
        svg = canvas_editor.export_svg(
            {
                "strokes": [
                    {"type": "rect", "x": 10, "y": 20, "width": 30, "height": 40.5}
                ],
                "width": 400,
                "height": 300,
            }
        )
        assert 'x="10"' in svg
        assert 'width="30"' in svg
        assert 'height="40.5"' in svg
        assert 'width="400"' in svg

    def test_malformed_stroke_entries_are_ignored(
        self, canvas_editor: CanvasEditor
    ) -> None:
        svg = canvas_editor.export_svg(
            {"strokes": ["not-a-dict", None, 42], "width": 100, "height": 100}
        )
        _assert_no_attribute_breakout(svg)


# ---------------------------------------------------------------------------
# Task-2 bugfix: SVG preview built from canvas_json (full fidelity), not the
# lossy `strokes` array.
#
# Root cause: frontend's extractStrokeData maps every Fabric object to
# {type: "pen", ...} and only populates `points` for genuine freehand
# fabric.Path objects — rects/ellipses/textboxes/connectors all became
# {type: "pen", points: []} placeholders in `strokes`, which rendered as an
# empty <path d=""/>. `canvas_json` (Fabric's own toJSON(["data"]) output)
# tags every shape/text/connector with a `data.type` discriminator and is
# now the primary source for the preview SVG (see _generate_svg / the
# CanvasEditor.get_canvas() docstring).
# ---------------------------------------------------------------------------

# A close approximation of real Fabric.js toJSON(["data"]) output: a rect and
# a textbox connected by a line, plus the triangle arrowhead Fabric adds as
# its own object (createConnector in CanvasEditor.tsx) — which must NOT be
# rendered a second time on top of the connector's own SVG <marker> arrowhead.
FULL_FIDELITY_CANVAS_JSON = {
    "version": "5.3.0",
    "objects": [
        {
            "type": "rect",
            "left": 50,
            "top": 60,
            "width": 120,
            "height": 80,
            "fill": "#eeeeee",
            "stroke": "#333333",
            "strokeWidth": 2,
            "scaleX": 1,
            "scaleY": 1,
            "opacity": 1,
            "data": {"id": "shape-1", "type": "rect"},
        },
        {
            "type": "textbox",
            "left": 300,
            "top": 60,
            "width": 160,
            "height": 20,
            "text": "Hello Shapes",
            "fontSize": 14,
            "fill": "#111111",
            "scaleX": 1,
            "scaleY": 1,
            "opacity": 1,
            "data": {"id": "text-1", "type": "text"},
        },
        {
            "type": "line",
            "x1": 170,
            "y1": 100,
            "x2": 300,
            "y2": 70,
            "stroke": "#4f6ef7",
            "strokeWidth": 2,
            "opacity": 1,
            "data": {
                "type": "connector",
                "id": "conn-1",
                "fromId": "shape-1",
                "toId": "text-1",
            },
        },
        {
            "type": "triangle",
            "left": 300,
            "top": 70,
            "width": 11,
            "height": 13,
            "fill": "#4f6ef7",
            "angle": 45,
            "data": {"type": "arrowHead", "connectorId": "conn-1"},
        },
    ],
    "background": "",
}


class TestGenerateSvgFromCanvasJson:
    """`_generate_svg(stroke_data, canvas_json=...)` full-fidelity path."""

    def test_rect_textbox_connector_all_render(self) -> None:
        svg = _generate_svg(
            {"strokes": [], "width": 800, "height": 600},
            canvas_json=FULL_FIDELITY_CANVAS_JSON,
        )
        root = ET.fromstring(svg)
        tags = {node.tag.rsplit("}", 1)[-1] for node in root.iter()}
        assert "rect" in tags
        assert "text" in tags
        assert "line" in tags
        assert "Hello Shapes" in svg
        # Not the historical bug: an empty stub with no drawable geometry.
        assert "<rect" in svg
        assert 'width="0"' not in svg

    def test_arrowhead_object_not_rendered_twice(self) -> None:
        """The triangle arrowHead object is redundant with the connector's
        own SVG <marker> arrowhead (marker-end) and must be skipped, not
        drawn as a second, unlabelled shape."""
        svg = _generate_svg({"strokes": []}, canvas_json=FULL_FIDELITY_CANVAS_JSON)
        root = ET.fromstring(svg)
        lines = [n for n in root.iter() if n.tag.rsplit("}", 1)[-1] == "line"]
        polygons_outside_defs = [
            n
            for n in root.iter()
            if n.tag.rsplit("}", 1)[-1] == "polygon"
        ]
        assert len(lines) == 1
        # Only the <marker><polygon> in <defs> — no second arrowhead shape.
        assert len(polygons_outside_defs) == 1
        assert "marker-end" in svg

    def test_canvas_json_none_falls_back_to_strokes(self) -> None:
        """Pre-existing rows with canvas_json=None keep rendering from the
        legacy `strokes` array unchanged."""
        svg = _generate_svg(VALID_CANVAS_STROKES, canvas_json=None)
        assert "<rect" in svg
        assert "Hello Canvas" in svg

    def test_ellipse_renders(self) -> None:
        canvas_json = {
            "objects": [
                {
                    "type": "ellipse",
                    "left": 10,
                    "top": 10,
                    "rx": 40,
                    "ry": 20,
                    "fill": "#ffffff",
                    "stroke": "#000000",
                    "data": {"id": "e1", "type": "ellipse"},
                }
            ]
        }
        svg = _generate_svg({"strokes": []}, canvas_json=canvas_json)
        assert "<ellipse" in svg

    def test_unrecognized_object_gets_explicit_fallback_not_silent(self) -> None:
        """Done-when criterion: never a silently empty shape."""
        canvas_json = {
            "objects": [
                {
                    "type": "group",
                    "left": 5,
                    "top": 5,
                    "data": {"id": "g1", "type": "future-fabric-object-kind"},
                }
            ]
        }
        svg = _generate_svg({"strokes": []}, canvas_json=canvas_json)
        assert "preview unavailable" in svg

    def test_freehand_pen_still_renders_alongside_shapes(self) -> None:
        """Genuine freehand strokes (the one case `strokes` was never lossy
        for) keep rendering when canvas_json also carries shapes."""
        stroke_data = {
            "strokes": [
                {
                    "id": "pen-1",
                    "type": "pen",
                    "points": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
                    "color": "#000000",
                },
                # Lossy placeholder for the rect below — must not duplicate it.
                {"id": "shape-1", "type": "pen", "points": []},
            ],
            "width": 800,
            "height": 600,
        }
        svg = _generate_svg(stroke_data, canvas_json=FULL_FIDELITY_CANVAS_JSON)
        assert "<path" in svg
        assert "<rect" in svg

    def test_connector_preview_object_skipped(self) -> None:
        """Transient drag-to-connect preview lines must never be persisted,
        but skip them defensively if one ever is."""
        canvas_json = {
            "objects": [
                {
                    "type": "line",
                    "x1": 0,
                    "y1": 0,
                    "x2": 10,
                    "y2": 10,
                    "data": {"type": "connectorPreview"},
                }
            ]
        }
        svg = _generate_svg({"strokes": []}, canvas_json=canvas_json)
        root = ET.fromstring(svg)
        lines = [n for n in root.iter() if n.tag.rsplit("}", 1)[-1] == "line"]
        assert len(lines) == 0


class TestGetCanvasUsesCanvasJson:
    """CanvasEditor.get_canvas() end-to-end: full fidelity via canvas_json."""

    def test_get_canvas_renders_shapes_from_canvas_json(
        self, canvas_editor, tenant_a, workspace_a
    ):
        stroke_data = {
            "strokes": [],
            "width": 800,
            "height": 600,
            "canvas_json": FULL_FIDELITY_CANVAS_JSON,
        }
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=stroke_data,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            result = canvas_editor.get_canvas(diagram.id)

        assert "<rect" in result.svg
        assert "Hello Shapes" in result.svg
        assert "<line" in result.svg

    def test_get_canvas_legacy_row_without_canvas_json_uses_strokes(
        self, canvas_editor, tenant_a, workspace_a
    ):
        """Pre-existing rows (canvas_json=None) keep the legacy rendering."""
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            result = canvas_editor.get_canvas(diagram.id)

        assert result.canvas_json is None
        assert "<rect" in result.svg
        assert "Hello Canvas" in result.svg


# ---------------------------------------------------------------------------
# Security: canvas_json code path — same XSS regression guard as PR #351
# (TestSVGAttributeInjection above), now exercised against the new source.
# Every value in _canvas_json_object_to_element flows through the same
# _num_attr/_escape_xml_attr primitives via _element_to_svg — this asserts
# that guarantee holds for canvas_json-originated elements too.
# ---------------------------------------------------------------------------

_CANVAS_JSON_NUMERIC_CASES: list[dict] = [
    {"type": "rect", "left": XSS_ATTR_PAYLOAD, "top": 0, "width": XSS_ATTR_PAYLOAD,
     "height": 10, "data": {"type": "rect"}},
    {"type": "rect", "left": 0, "top": 0, "width": 10, "height": 10,
     "scaleX": XSS_ATTR_PAYLOAD, "scaleY": XSS_ATTR_PAYLOAD, "data": {"type": "rect"}},
    {"type": "ellipse", "left": XSS_ATTR_PAYLOAD, "top": XSS_ATTR_PAYLOAD,
     "rx": XSS_ATTR_PAYLOAD, "ry": XSS_ATTR_PAYLOAD, "data": {"type": "ellipse"}},
    {"type": "textbox", "left": XSS_ATTR_PAYLOAD, "top": XSS_ATTR_PAYLOAD,
     "fontSize": XSS_ATTR_PAYLOAD, "text": "hi", "data": {"type": "text"}},
    {"type": "line", "x1": XSS_ATTR_PAYLOAD, "y1": XSS_ATTR_PAYLOAD,
     "x2": XSS_ATTR_PAYLOAD, "y2": XSS_ATTR_PAYLOAD,
     "strokeWidth": XSS_ATTR_PAYLOAD, "data": {"type": "connector"}},
    {"type": "rect", "left": 0, "top": 0, "width": 1, "height": 1,
     "opacity": XSS_ATTR_PAYLOAD, "data": {"type": "rect"}},
    # Non-string, non-numeric JSON types must not crash or leak either.
    {"type": "rect", "left": None, "top": [1, 2], "width": {"a": 1},
     "height": True, "data": {"type": "rect"}},
]


class TestCanvasJsonAttributeInjection:
    @pytest.mark.parametrize("obj", _CANVAS_JSON_NUMERIC_CASES)
    def test_numeric_fields_reject_attribute_injection(self, obj: dict) -> None:
        svg = _generate_svg(
            {"strokes": [], "width": 800, "height": 600},
            canvas_json={"objects": [obj]},
        )
        _assert_no_attribute_breakout(svg)
        assert "onload" not in svg.lower()

    def test_text_content_stays_escaped(self) -> None:
        obj = {
            "type": "textbox",
            "left": 1,
            "top": 2,
            "text": "</text><script>alert(1)</script>",
            "fill": XSS_ATTR_PAYLOAD,
            "data": {"type": "text"},
        }
        svg = _generate_svg({"strokes": []}, canvas_json={"objects": [obj]})
        _assert_no_attribute_breakout(svg)

    def test_malformed_canvas_json_objects_are_ignored(self) -> None:
        svg = _generate_svg(
            {"strokes": []}, canvas_json={"objects": ["not-a-dict", None, 42]}
        )
        _assert_no_attribute_breakout(svg)

    def test_fallback_placeholder_stays_escaped(self) -> None:
        """Even the "preview unavailable" fallback attributes (built from
        attacker-controlled left/top) must go through the same coercion."""
        obj = {
            "type": "mystery",
            "left": XSS_ATTR_PAYLOAD,
            "top": XSS_ATTR_PAYLOAD,
            "data": {"type": "mystery"},
        }
        svg = _generate_svg({"strokes": []}, canvas_json={"objects": [obj]})
        _assert_no_attribute_breakout(svg)
        assert "preview unavailable" in svg


# ---------------------------------------------------------------------------
# IF-DS-INT-006: TraceLink creation
# ---------------------------------------------------------------------------

class TestCanvasTraceLink:
    """REQ-L2-DS-006 AC5: TraceLink (type 'documents') creation."""

    def test_link_canvas_to_artifact(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

        with patch.object(
            canvas_editor._traceability,
            "create_document_link",
        ) as mock_link:
            mock_link.return_value = MagicMock()
            target_id = uuid.uuid4()

            canvas_editor.link_canvas_to_artifact(
                diagram_id=diagram.id,
                target_id=target_id,
            )

        mock_link.assert_called_once_with(
            diagram_id=diagram.id,
            target_id=target_id,
            created_by_id=None,
        )

    def test_create_with_target_id(self, canvas_editor, tenant_a, workspace_a):
        """Canvas created with target_id triggers TraceLink creation."""
        target_id = uuid.uuid4()

        with patch("diagram.manager.log_write"):
            with active_tenant(tenant_a):
                with patch.object(
                    canvas_editor._manager._traceability,
                    "create_document_link",
                ) as mock_link:
                    mock_link.return_value = MagicMock()

                    canvas_editor.handle_stroke_update(
                        diagram_id=None,
                        stroke_data=VALID_CANVAS_STROKES,
                        tenant=tenant_a,
                        target_id=target_id,
                        workspace_id=workspace_a.id,
                    )

        # The DiagramManager calls traceability internally on create
        # (via its own _traceability, not canvas_editor's)
        # This test verifies the target_id parameter is passed through


# ---------------------------------------------------------------------------
# IF-L1-060: get_canvas — retrieval + export
# ---------------------------------------------------------------------------

class TestGetCanvas:
    """REQ-L2-DS-006: get_canvas returns stroke data + SVG."""

    def test_get_canvas_returns_export_result(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            result = canvas_editor.get_canvas(diagram.id)

        assert isinstance(result, CanvasExportResult)
        assert result.diagram_id == diagram.id
        assert "strokes" in result.stroke_data
        assert "<svg" in result.svg

    def test_get_canvas_specific_version(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            canvas_editor.handle_stroke_update(
                diagram_id=diagram.id,
                stroke_data={"strokes": [], "width": 800, "height": 600},
                tenant=tenant_a,
            )
            result = canvas_editor.get_canvas(diagram.id, version_number=1)

        assert result.version.version_number == 1
        assert len(result.stroke_data.get("strokes", [])) == 3

    def test_get_canvas_nonexistent_raises(self, canvas_editor, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            with pytest.raises(Diagram.DoesNotExist):
                canvas_editor.get_canvas(uuid.uuid4())


# ---------------------------------------------------------------------------
# REQ-L2-CV-005: canvas_json — additive full-canvas persistence
# ---------------------------------------------------------------------------

SAMPLE_CANVAS_JSON = {
    "version": "5.3.0",
    "objects": [
        {"type": "rect", "left": 10, "top": 10, "width": 100, "height": 50},
        {"type": "circle", "left": 200, "top": 80, "radius": 25},
    ],
    "background": "#ffffff",
}


class TestCanvasJsonPersistence:
    """REQ-L2-CV-005: canvas_json is stored alongside strokes (backward-compatible)."""

    def test_backward_compat_strokes_only_leaves_canvas_json_null(
        self, canvas_editor, tenant_a, workspace_a
    ):
        """Old format (strokes only, no canvas_json) still works; field stays None."""
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

        assert diagram.canvas_json is None

    def test_canvas_json_populates_new_field(
        self, canvas_editor, tenant_a, workspace_a
    ):
        """canvas_json in the payload is persisted on the Diagram row."""
        stroke_data = {**VALID_CANVAS_STROKES, "canvas_json": SAMPLE_CANVAS_JSON}

        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=stroke_data,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

        assert diagram.canvas_json == SAMPLE_CANVAS_JSON

    def test_canvas_json_excluded_from_stroke_payload(
        self, canvas_editor, tenant_a, workspace_a
    ):
        """Stroke payload format stays stable — canvas_json is not embedded in it."""
        stroke_data = {**VALID_CANVAS_STROKES, "canvas_json": SAMPLE_CANVAS_JSON}

        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=stroke_data,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

        payload = json.loads(diagram.payload)
        assert "canvas_json" not in payload
        assert "strokes" in payload

    def test_get_canvas_returns_canvas_json(
        self, canvas_editor, tenant_a, workspace_a
    ):
        """get_canvas surfaces the stored canvas_json in the export result."""
        stroke_data = {**VALID_CANVAS_STROKES, "canvas_json": SAMPLE_CANVAS_JSON}

        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=stroke_data,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            result = canvas_editor.get_canvas(diagram.id)

        assert result.canvas_json == SAMPLE_CANVAS_JSON

    def test_get_canvas_canvas_json_none_for_legacy(
        self, canvas_editor, tenant_a, workspace_a
    ):
        """get_canvas returns canvas_json=None for versions created without it."""
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            result = canvas_editor.get_canvas(diagram.id)

        assert result.canvas_json is None

    def test_update_adds_canvas_json_new_version_only(
        self, canvas_editor, tenant_a, workspace_a
    ):
        """Updating with canvas_json stores it on the new revision; v1 stays None."""
        with active_tenant(tenant_a):
            diagram = canvas_editor.handle_stroke_update(
                diagram_id=None,
                stroke_data=VALID_CANVAS_STROKES,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            canvas_editor.handle_stroke_update(
                diagram_id=diagram.id,
                stroke_data={**VALID_CANVAS_STROKES, "canvas_json": SAMPLE_CANVAS_JSON},
                tenant=tenant_a,
            )

            v1 = _revision_payload(diagram, 1)
            v2 = _revision_payload(diagram, 2)
        assert v1["canvas_json"] is None
        assert v2["canvas_json"] == SAMPLE_CANVAS_JSON



def _revision_payload(diagram, revision: int) -> dict:
    """Return the recorded ArtifactVersion payload for *revision* (Task 28c-2)."""
    from persistence.models import ArtifactVersion

    return ArtifactVersion.unscoped.get(
        artifact_id=diagram.artifact_id, revision=revision
    ).payload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_element(elem_type: str) -> dict:
    """Create a minimal valid element for the given type."""
    base: dict = {"type": elem_type}
    if elem_type == "pen":
        base["points"] = [{"x": 0, "y": 0}, {"x": 10, "y": 10}]
    elif elem_type == "rect":
        base.update({"x": 0, "y": 0, "width": 100, "height": 50})
    elif elem_type == "circle":
        base.update({"cx": 50, "cy": 50, "r": 25})
    elif elem_type == "line":
        base.update({"x1": 0, "y1": 0, "x2": 100, "y2": 100})
    elif elem_type == "text":
        base.update({"x": 10, "y": 20, "content": "Test"})
    elif elem_type == "arrow":
        base.update({"x1": 0, "y1": 0, "x2": 100, "y2": 0})
    elif elem_type == "connector":
        base.update({"source_id": "a", "target_id": "b"})
    return base
