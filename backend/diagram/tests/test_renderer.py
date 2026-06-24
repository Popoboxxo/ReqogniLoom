"""
COMP-DS-003 DiagramRenderer — Unit tests.

Covers:
  REQ-L2-DS-003: Renderable representation returned for each diagram type
  REQ-L3-DR-001: RenderableDiagram contains type, content and render_hint

IF-DS-INT-002: prepare_renderable(diagram_type, payload_format, content)
"""
from __future__ import annotations

import pytest

from diagram.renderer import DiagramRenderer, RenderableDiagram


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
