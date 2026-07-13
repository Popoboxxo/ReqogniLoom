"""
ARCH-L1-013 DiagramService — MCP artifact.get adapter.

leaf_id: COMP-DS-005_McpArtifactProvider
req_id: REQ-L1-027, REQ-L2-DS-005, REQ-L3-MAP-001

External interface (incoming):
  IF-L1-033: artifact.get from McpServer — handled by get_artifact()

Internal interface (outgoing):
  DiagramManager.get_diagram() — fetches the Diagram + RenderableDiagram

Adapts MCP 'artifact.get' tool calls for the diagram artefact type.
Returns a structured text/Markdown response that MCP clients (AI agents)
can parse to extract diagram source, type, version and render hint.

REQ-L3-MAP-001 acceptance criteria:
  - Valid diagram_id returns structured payload.
  - Non-existent diagram_id returns standardised MCP error dict.
  - Payload is returned as Markdown/plaintext.
"""
from __future__ import annotations

import uuid
from typing import Any


# ---------------------------------------------------------------------------
# MCP response helpers
# ---------------------------------------------------------------------------

def _ok_response(diagram_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Format a successful MCP artifact.get response."""
    return {
        "type": "artifact",
        "artifact_type": "diagram",
        "id": diagram_id,
        "payload": payload,
        "error": None,
    }


def _error_response(diagram_id: str, message: str) -> dict[str, Any]:
    """Format a standardised MCP error response (REQ-L3-MAP-001)."""
    return {
        "type": "error",
        "artifact_type": "diagram",
        "id": diagram_id,
        "payload": None,
        "error": {
            "code": "artifact_not_found",
            "message": message,
        },
    }


def _to_markdown(diagram_data: dict[str, Any]) -> str:
    """Serialise diagram data as a Markdown/plaintext string for MCP clients.

    REQ-L3-MAP-001: payload returned as Markdown/plaintext representation.
    """
    lines = [
        f"# Diagram: {diagram_data.get('name', 'Unnamed')}",
        f"- **ID:** {diagram_data.get('id')}",
        f"- **Type:** {diagram_data.get('diagram_type')}",
        f"- **Version:** {diagram_data.get('version_number')}",
        f"- **Format:** {diagram_data.get('payload_format')}",
        f"- **Render hint:** {diagram_data.get('render_hint')}",
        "",
        "## Payload",
        "```",
        diagram_data.get("content", ""),
        "```",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public interface — IF-L1-033
# ---------------------------------------------------------------------------

class McpArtifactProvider:
    """COMP-DS-005: Adapts MCP 'artifact.get' calls for diagram artefacts.

    req_id: REQ-L2-DS-005, REQ-L3-MAP-001
    leaf_id: COMP-DS-005_McpArtifactProvider

    Receives calls from McpServer (ARCH-L1-003) via IF-L1-033.
    Delegates data retrieval to DiagramManager (COMP-DS-001) internally.
    DiagramManager is injected to avoid circular imports and allow testing.
    """

    def __init__(self, diagram_manager: Any) -> None:
        """Inject DiagramManager instance (dependency injection).

        Args:
            diagram_manager: An instance of DiagramManager (COMP-DS-001).
                             Type is 'Any' to avoid circular import; callers
                             pass diagram.manager.DiagramManager().
        """
        self._manager = diagram_manager

    def get_artifact(
        self,
        diagram_id: str,
    ) -> dict[str, Any]:
        """Handle MCP 'artifact.get' call for a diagram artefact.

        IF-L1-033 entry point.

        Args:
            diagram_id: String UUID of the diagram to retrieve.

        Returns:
            dict with 'type', 'artifact_type', 'id', 'payload', 'error'.
            On success payload contains 'content' (Markdown string) and
            structured fields.  On failure 'error' is non-None.

        REQ-L3-MAP-001 acceptance criteria satisfied:
          - Valid ID → structured payload.
          - Non-existent ID → standardised MCP error dict.
          - Payload is Markdown representation.
        """
        try:
            parsed_id = uuid.UUID(str(diagram_id))
        except (ValueError, AttributeError):
            return _error_response(
                str(diagram_id),
                f"Invalid diagram_id format: '{diagram_id}' is not a valid UUID.",
            )

        try:
            result = self._manager.get_diagram(parsed_id)
        except Exception as exc:  # noqa: BLE001
            # Translate any manager-layer exception into a standardised MCP error.
            return _error_response(
                str(diagram_id),
                f"Diagram '{diagram_id}' not found or inaccessible: {exc}",
            )

        # result is a DiagramResult dataclass (see manager.py)
        diagram_data = {
            "id": str(result.diagram.id),
            "name": result.diagram.name,
            "diagram_type": result.diagram.diagram_type,
            "version_number": result.version.version_number if result.version else None,
            "payload_format": result.version.payload_format if result.version else None,
            "content": result.renderable.content if result.renderable else "",
            "render_hint": result.renderable.render_hint if result.renderable else "unknown",
        }

        markdown_payload = _to_markdown(diagram_data)

        return _ok_response(
            diagram_id=str(parsed_id),
            payload={
                "markdown": markdown_payload,
                **diagram_data,
            },
        )


__all__ = [
    "McpArtifactProvider",
]
