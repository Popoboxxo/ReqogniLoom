"""
COMP-DS-003 DiagramRenderer — Unit tests.

Covers:
  REQ-L2-DS-003: Renderable representation returned for each diagram type
  REQ-L3-DR-001: RenderableDiagram contains type, content and render_hint
  REQ-L2-DS-007: RenderHints for Mermaid diagram types

IF-DS-INT-002: prepare_renderable(diagram_type, payload_format, content)
IF-DS-INT-008: get_render_hints(diagram_type, payload_format) -> RenderHints
"""
from __future__ import annotations

import json

import pytest

from diagram.node_graph_renderer import NodeGraphRenderError
from diagram.renderer import DiagramRenderer, RenderableDiagram, RenderHints


@pytest.fixture
def renderer() -> DiagramRenderer:
    return DiagramRenderer()


class TestPrepareRenderable:
    """REQ-L3-DR-001: prepare_renderable returns complete RenderableDiagram."""

    def test_mermaid_block_returns_renderable(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("block", "mermaid", "block-beta\n  A[X]")
        assert isinstance(r, RenderableDiagram)
        assert r.diagram_type == "block"
        assert r.payload_format == "mermaid"
        assert r.content == "block-beta\n  A[X]"
        assert r.render_hint == "mermaid.js"

    def test_mermaid_flow_render_hint(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("flow", "mermaid", "flowchart TD\n  A-->B")
        assert r.render_hint == "mermaid.js"

    def test_mermaid_context_render_hint(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("context", "mermaid", "flowchart LR\n  U-->S")
        assert r.render_hint == "mermaid.js"

    def test_plantuml_render_hint(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("block", "plantuml", "@startuml\nA\n@enduml")
        assert r.render_hint == "plantuml-js"

    def test_json_render_hint(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("flow", "json", '{"nodes":[],"edges":[]}')
        assert r.render_hint == "custom-json"

    def test_metadata_passed_through(self, renderer: DiagramRenderer) -> None:
        meta = {"theme": "dark", "direction": "LR"}
        r = renderer.prepare_renderable("context", "mermaid", "flowchart LR", metadata=meta)
        assert r.metadata == meta

    def test_metadata_defaults_to_empty_dict(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("block", "mermaid", "block-beta\n  A[X]")
        assert r.metadata == {}

    def test_unknown_type_format_returns_unknown_hint(self, renderer: DiagramRenderer) -> None:
        """Renderer does not validate — that is DiagramValidator's job."""
        r = renderer.prepare_renderable("anything", "anything", "content")
        assert r.render_hint == "unknown"


class TestExportStubs:
    """PNG/SVG export stubs raise NotImplementedError (documented in v1)."""

    def test_export_png_raises_not_implemented(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("block", "mermaid", "block-beta\n  A[X]")
        with pytest.raises(NotImplementedError):
            renderer.export_png(r)

    def test_export_svg_raises_not_implemented(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable("flow", "mermaid", "flowchart TD\n  A-->B")
        with pytest.raises(NotImplementedError):
            renderer.export_svg(r)


# ---------------------------------------------------------------------------
# GH-353 (Task 6): export_svg dispatch — node_graph implemented, every other
# format stays a documented NotImplementedError stub.
# ---------------------------------------------------------------------------

_NODE_GRAPH_PAYLOAD: dict = {
    "schema_version": 1,
    "nodes": [
        {"id": "n-1", "type": "box", "label": "A", "position": {"x": 0, "y": 0}},
    ],
    "edges": [],
}


class TestExportSvgNodeGraphDispatch:
    def test_node_graph_export_svg_returns_svg_string(self, renderer: DiagramRenderer) -> None:
        r = renderer.prepare_renderable(
            "block", "node_graph", json.dumps(_NODE_GRAPH_PAYLOAD)
        )
        svg = renderer.export_svg(r)
        assert svg.startswith("<svg")
        assert svg.rstrip().endswith("</svg>")
        assert "A" in svg

    @pytest.mark.parametrize(
        "diagram_type,payload_format,content",
        [
            ("block", "mermaid", "block-beta\n  A[X]"),
            ("flow", "mermaid", "flowchart TD\n  A-->B"),
            ("block", "plantuml", "@startuml\nA\n@enduml"),
            ("flow", "json", '{"nodes":[],"edges":[]}'),
            ("canvas", "canvas_stroke", '{"strokes":[]}'),
        ],
    )
    def test_non_node_graph_formats_still_raise_not_implemented(
        self, renderer: DiagramRenderer, diagram_type: str, payload_format: str, content: str
    ) -> None:
        r = renderer.prepare_renderable(diagram_type, payload_format, content)
        with pytest.raises(NotImplementedError):
            renderer.export_svg(r)

    def test_node_graph_export_svg_propagates_render_errors(
        self, renderer: DiagramRenderer
    ) -> None:
        """Defense-in-depth: a node_graph payload that bypassed validation
        (here, an unknown node type) must surface as a render error, not a
        silently-wrong SVG or an unrelated crash."""
        hostile_payload = {
            "schema_version": 1,
            "nodes": [
                {"id": "n-1", "type": "hexagon", "label": "A", "position": {"x": 0, "y": 0}}
            ],
            "edges": [],
        }
        r = renderer.prepare_renderable(
            "block", "node_graph", json.dumps(hostile_payload)
        )
        with pytest.raises(NodeGraphRenderError):
            renderer.export_svg(r)


# ---------------------------------------------------------------------------
# REQ-L2-DS-007: RenderHints for Mermaid diagram types
# IF-DS-INT-008: get_render_hints
# ---------------------------------------------------------------------------

class TestGetRenderHints:
    """REQ-L2-DS-007: get_render_hints returns correct metadata for Mermaid types."""

    def test_mermaid_type_returns_hints(self, renderer: DiagramRenderer) -> None:
        hints = renderer.get_render_hints("mermaid", "mermaid")
        assert isinstance(hints, RenderHints)
        assert hints.render_hint == "mermaid.js"
        assert hints.client_side is True
        assert len(hints.supported_types) == 5

    def test_mermaid_supported_types(self, renderer: DiagramRenderer) -> None:
        hints = renderer.get_render_hints("mermaid", "mermaid")
        expected_types = ["flowchart", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram"]
        assert hints.supported_types == expected_types

    def test_non_mermaid_type_empty_supported(self, renderer: DiagramRenderer) -> None:
        hints = renderer.get_render_hints("block", "mermaid")
        assert hints.supported_types == []
        assert hints.render_hint == "mermaid.js"

    def test_unknown_type_returns_unknown_hint(self, renderer: DiagramRenderer) -> None:
        hints = renderer.get_render_hints("unknown", "unknown")
        assert hints.render_hint == "unknown"
        assert hints.supported_types == []
