"""
ARCH-L1-013 DiagramService — Diagram renderer.

leaf_id: COMP-DS-003_DiagramRenderer, COMP-DS-007_MermaidLiveRenderer
req_id: REQ-L1-027, REQ-L2-DS-003, REQ-L3-DR-001, REQ-L1-057, REQ-L2-DS-007

Internal interface:
  IF-DS-INT-002: prepare_renderable(diagram_type, payload_format, content) -> RenderableDiagram
  IF-DS-INT-008: get_render_hints(diagram_type, payload_format) -> RenderHints

Transforms a validated, persisted diagram payload into a RenderableDiagram
dataclass that the frontend (or MCP response) can consume directly.

PNG/SVG binary export is NOT implemented in this version (stub documented
below).  The frontend is expected to render Mermaid/PlantUML payloads
client-side using mermaid.js or PlantUML JavaScript SDKs.

COMP-DS-007 MermaidLiveRenderer uses get_render_hints() to retrieve rendering
metadata for the 5 Mermaid diagram types (flowchart, sequenceDiagram,
classDiagram, stateDiagram, erDiagram).

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

import json
from dataclasses import dataclass
from typing import Any, Optional

from diagram.models import DiagramType, PayloadFormat
from diagram.node_graph_renderer import NodeGraphRenderError
from diagram.node_graph_renderer import render_svg as _render_node_graph_svg


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
        diagram_type:    One of DiagramType values (block/flow/context/mermaid).
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


@dataclass(frozen=True)
class RenderHints:
    """Output contract for IF-DS-INT-008 — COMP-DS-007.

    REQ-L2-DS-007: Contains rendering metadata for Mermaid diagram types.
    Used by MermaidLiveRenderer to provide live-preview configuration.

    Attributes:
        render_hint:     Library hint for the frontend (e.g. 'mermaid.js').
        diagram_type:    The Mermaid diagram type (e.g. 'flowchart', 'sequenceDiagram').
        supported_types: List of all supported Mermaid diagram types.
        client_side:     True if rendering happens client-side (ADR-DS-03).
    """

    render_hint: str
    diagram_type: str
    supported_types: list[str]
    client_side: bool = True


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
    (DiagramType.MERMAID, PayloadFormat.MERMAID): "mermaid.js",
    # GH-353 (Task 1): node_graph is a strictly-typed node/edge format,
    # rendered client-side via React Flow — additive only, every DiagramType
    # may carry a node_graph version. Unmapped combinations already fall
    # back to "unknown" without raising, so this cannot break existing hints.
    (DiagramType.BLOCK, PayloadFormat.NODE_GRAPH): "react-flow",
    (DiagramType.FLOW, PayloadFormat.NODE_GRAPH): "react-flow",
    (DiagramType.CONTEXT, PayloadFormat.NODE_GRAPH): "react-flow",
    (DiagramType.CANVAS, PayloadFormat.NODE_GRAPH): "react-flow",
    (DiagramType.MERMAID, PayloadFormat.NODE_GRAPH): "react-flow",
}

# Supported Mermaid diagram types for COMP-DS-007 — REQ-L2-DS-007
_MERMAID_SUPPORTED_TYPES: list[str] = [
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
]


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
        """Export a diagram as an SVG string.

        GH-353 (Task 6): implemented for ``node_graph`` payloads only —
        delegates to :func:`diagram.node_graph_renderer.render_svg`, the
        module carrying the XSS-hardening burden for that format. Every
        other ``payload_format`` (mermaid, plantuml, json, canvas_stroke)
        stays a documented ``NotImplementedError`` stub, per the Task 6
        brief and ADR-DS-01 scoping — ``canvas_stroke`` already has its own
        SVG export via :meth:`diagram.canvas_editor.CanvasEditor.export_svg`
        (a different call path, not this one).

        Args:
            renderable: A :class:`RenderableDiagram` as returned by
                :meth:`prepare_renderable` (or ``DiagramManager.get_diagram``
                via its ``renderable`` field).

        Returns:
            A well-formed SVG string, for ``payload_format == "node_graph"``.

        Raises:
            NotImplementedError: For every ``payload_format`` other than
                ``node_graph``.
            diagram.node_graph_renderer.NodeGraphRenderError: If the
                ``node_graph`` payload cannot be safely rendered — either
                because the persisted content is not valid JSON (review fix
                round 1: previously an uncaught ``json.JSONDecodeError``),
                or because :func:`diagram.node_graph_renderer.render_svg`
                itself refuses it (see that module — should be unreachable
                for a payload that already passed
                :func:`diagram.node_graph.validate_node_graph`).
        """
        if renderable.payload_format != PayloadFormat.NODE_GRAPH:
            raise NotImplementedError(
                "SVG export is only implemented for the 'node_graph' payload "
                f"format in v1 (got {renderable.payload_format!r}). "
                "Use the content field of RenderableDiagram for client-side "
                "rendering of other formats."
            )
        try:
            payload = json.loads(renderable.content)
        except json.JSONDecodeError as exc:
            raise NodeGraphRenderError(
                f"node_graph diagram content is not valid JSON: {exc}."
            ) from exc
        return _render_node_graph_svg(payload)

    # ------------------------------------------------------------------
    # IF-DS-INT-008: get_render_hints — COMP-DS-007
    # REQ-L2-DS-007
    # ------------------------------------------------------------------

    def get_render_hints(
        self,
        diagram_type: str,
        payload_format: str,
    ) -> RenderHints:
        """Retrieve rendering metadata for a diagram type/format combination.

        IF-DS-INT-008 contract: get_render_hints(diagram_type, payload_format) -> RenderHints

        Used by COMP-DS-007 MermaidLiveRenderer to provide live-preview
        configuration for the 5 Mermaid diagram types.

        Args:
            diagram_type:   One of DiagramType values (block/flow/context/mermaid).
            payload_format: One of PayloadFormat values (mermaid/plantuml/json).

        Returns:
            RenderHints with render_hint, diagram_type, supported_types, client_side.

        REQ-L2-DS-007, REQ-L1-057
        """
        render_hint = _RENDER_HINTS.get(
            (diagram_type, payload_format),
            "unknown",
        )

        # For Mermaid diagrams, provide the list of supported types
        supported = _MERMAID_SUPPORTED_TYPES if diagram_type == DiagramType.MERMAID else []

        return RenderHints(
            render_hint=render_hint,
            diagram_type=diagram_type,
            supported_types=supported,
            client_side=True,  # ADR-DS-03: client-side rendering
        )


__all__ = [
    "DiagramRenderer",
    "RenderableDiagram",
    "RenderHints",
]
