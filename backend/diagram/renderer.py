"""
ARCH-L1-013 DiagramService — Diagram renderer.

leaf_id: COMP-DS-003_DiagramRenderer
req_id: REQ-L1-027, REQ-L2-DS-003, REQ-L3-DR-001

Internal interface:
  IF-DS-INT-002: prepare_renderable(diagram_type, payload_format, content) -> RenderableDiagram

Transforms a validated, persisted diagram payload into a RenderableDiagram
dataclass that the frontend (or MCP response) can consume directly.

PNG/SVG binary export is NOT implemented in this version (stub documented
below).  The frontend is expected to render Mermaid/PlantUML payloads
client-side using mermaid.js or PlantUML JavaScript SDKs.

Design notes (ADR-DS-01):
  Renderer is called on READ path only — validation happens on WRITE path.
  This class has no database dependencies.

Render-export stubs (PNG/SVG):
  Binary export via headless Chromium (Mermaid) or PlantUML server (PlantUML)
  is not implemented. These are declared as NotImplementedError stubs so the
  contract surface is explicit and the interface can be fulfilled in a later
  iteration without changing the caller (DiagramManager).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from diagram.models import DiagramType, PayloadFormat


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RenderableDiagram:
    """Output contract for IF-DS-INT-002.

    REQ-L3-DR-001: contains all information needed to render the diagram in
    the UI.  The frontend should inspect ``render_hint`` to decide which
    rendering library to invoke.

    Attributes:
        diagram_type:    One of DiagramType values (block/flow/context).
        payload_format:  One of PayloadFormat values (mermaid/plantuml/json).
        content:         The raw, validated payload string.
        render_hint:     Free-form hint for the frontend (e.g. 'mermaid.js',
                         'plantuml-js', 'custom-json').
        metadata:        Optional extra metadata (e.g. theme, direction).
    """

    diagram_type: str
    payload_format: str
    content: str
    render_hint: str
    metadata: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Render-hint mapping
# ---------------------------------------------------------------------------

_RENDER_HINTS: dict[tuple[str, str], str] = {
    (DiagramType.BLOCK, PayloadFormat.MERMAID): "mermaid.js",
    (DiagramType.BLOCK, PayloadFormat.PLANTUML): "plantuml-js",
    (DiagramType.BLOCK, PayloadFormat.JSON): "custom-json",
    (DiagramType.FLOW, PayloadFormat.MERMAID): "mermaid.js",
    (DiagramType.FLOW, PayloadFormat.PLANTUML): "plantuml-js",
    (DiagramType.FLOW, PayloadFormat.JSON): "custom-json",
    (DiagramType.CONTEXT, PayloadFormat.MERMAID): "mermaid.js",
    (DiagramType.CONTEXT, PayloadFormat.PLANTUML): "plantuml-js",
    (DiagramType.CONTEXT, PayloadFormat.JSON): "custom-json",
}


# ---------------------------------------------------------------------------
# Public interface — IF-DS-INT-002
# ---------------------------------------------------------------------------

class DiagramRenderer:
    """COMP-DS-003: Prepares a renderable representation of a diagram payload.

    req_id: REQ-L2-DS-003, REQ-L3-DR-001
    leaf_id: COMP-DS-003_DiagramRenderer

    Called exclusively by DiagramManager (COMP-DS-001) via IF-DS-INT-002 on
    the read path (get_diagram).  No database access.
    """

    def prepare_renderable(
        self,
        diagram_type: str,
        payload_format: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RenderableDiagram:
        """Transform a validated payload into a RenderableDiagram.

        IF-DS-INT-002 contract: prepare_renderable(type, content) -> RenderableDiagram

        Args:
            diagram_type:   One of DiagramType values.
            payload_format: One of PayloadFormat values.
            content:        The raw diagram payload string (already validated).
            metadata:       Optional caller-supplied metadata (theme etc.).

        Returns:
            RenderableDiagram with render_hint populated.

        REQ-L3-DR-001: API response contains all necessary information to
        render the diagram in the UI.
        """
        render_hint = _RENDER_HINTS.get(
            (diagram_type, payload_format),
            "unknown",
        )

        return RenderableDiagram(
            diagram_type=diagram_type,
            payload_format=payload_format,
            content=content,
            render_hint=render_hint,
            metadata=metadata or {},
        )

    def export_png(self, renderable: RenderableDiagram) -> bytes:
        """Stub: Export diagram as PNG via headless Chromium / PlantUML server.

        NOT IMPLEMENTED in v1.
        Requires: headless Chromium + @mermaid-js/mermaid-cli (Mermaid),
                  or a PlantUML server (PlantUML).

        Raises:
            NotImplementedError: Always. Binary export is deferred to v2.
        """
        raise NotImplementedError(
            "PNG export is not implemented in v1. "
            "Use the content field of RenderableDiagram for client-side rendering. "
            "See ADR-DS-01: rendering happens at the frontend tier."
        )

    def export_svg(self, renderable: RenderableDiagram) -> str:
        """Stub: Export diagram as SVG string.

        NOT IMPLEMENTED in v1.

        Raises:
            NotImplementedError: Always. SVG export is deferred to v2.
        """
        raise NotImplementedError(
            "SVG export is not implemented in v1. "
            "Use the content field of RenderableDiagram for client-side rendering."
        )


__all__ = [
    "DiagramRenderer",
    "RenderableDiagram",
]
