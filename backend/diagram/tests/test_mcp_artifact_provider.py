"""
COMP-DS-005 McpArtifactProvider — Unit tests.

Covers:
  REQ-L2-DS-005 / REQ-L3-MAP-001: MCP artifact.get adapter
    - Valid diagram_id returns structured payload
    - Non-existent ID returns standardised MCP error
    - Payload returned as Markdown/plaintext

IF-L1-033: get_artifact(diagram_id) entry point from McpServer
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from diagram.mcp_artifact_provider import McpArtifactProvider
from diagram.manager import DiagramResult
from diagram.renderer import RenderableDiagram
from diagram.models import Diagram, DiagramRevision


def _make_mock_manager(
    diagram_id: uuid.UUID,
    name: str = "Test Diagram",
    diagram_type: str = "block",
    version_number: int = 1,
    payload_format: str = "mermaid",
    content: str = "block-beta\n  A[X]",
    render_hint: str = "mermaid.js",
    raise_exc: Exception | None = None,
) -> MagicMock:
    """Build a mock DiagramManager that returns a plausible DiagramResult."""
    manager = MagicMock()

    if raise_exc is not None:
        manager.get_diagram.side_effect = raise_exc
        return manager

    mock_diagram = MagicMock(spec=Diagram)
    mock_diagram.id = diagram_id
    mock_diagram.name = name
    mock_diagram.diagram_type = diagram_type

    mock_version = MagicMock(spec=DiagramRevision)
    mock_version.version_number = version_number
    mock_version.payload_format = payload_format

    mock_renderable = MagicMock(spec=RenderableDiagram)
    mock_renderable.content = content
    mock_renderable.render_hint = render_hint

    result = DiagramResult(
        diagram=mock_diagram,
        version=mock_version,
        renderable=mock_renderable,
    )
    manager.get_diagram.return_value = result
    return manager


class TestGetArtifact:
    """REQ-L3-MAP-001: get_artifact contract."""

    def test_valid_id_returns_ok_response(self) -> None:
        diagram_id = uuid.uuid4()
        manager = _make_mock_manager(diagram_id)
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact(str(diagram_id))

        assert response["type"] == "artifact"
        assert response["artifact_type"] == "diagram"
        assert response["id"] == str(diagram_id)
        assert response["error"] is None

    def test_valid_id_returns_structured_payload(self) -> None:
        diagram_id = uuid.uuid4()
        manager = _make_mock_manager(diagram_id, name="Block A", render_hint="mermaid.js")
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact(str(diagram_id))

        payload = response["payload"]
        assert payload is not None
        assert payload["name"] == "Block A"
        assert payload["render_hint"] == "mermaid.js"
        assert payload["diagram_type"] == "block"

    def test_valid_id_returns_markdown_in_payload(self) -> None:
        """REQ-L3-MAP-001: Payload returned as Markdown/plaintext."""
        diagram_id = uuid.uuid4()
        manager = _make_mock_manager(diagram_id, content="block-beta\n  Node")
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact(str(diagram_id))

        assert "markdown" in response["payload"]
        markdown = response["payload"]["markdown"]
        assert "# Diagram:" in markdown
        assert "block-beta" in markdown

    def test_nonexistent_id_returns_error_response(self) -> None:
        """REQ-L3-MAP-001: Non-existent ID returns standardised MCP error."""
        diagram_id = uuid.uuid4()
        manager = _make_mock_manager(
            diagram_id,
            raise_exc=Exception("Diagram.DoesNotExist"),
        )
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact(str(diagram_id))

        assert response["type"] == "error"
        assert response["payload"] is None
        assert response["error"] is not None
        assert response["error"]["code"] == "artifact_not_found"

    def test_invalid_uuid_returns_error_response(self) -> None:
        """REQ-L3-MAP-001: Invalid UUID format returns standardised MCP error."""
        manager = _make_mock_manager(uuid.uuid4())
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact("not-a-valid-uuid")

        assert response["type"] == "error"
        assert response["error"]["code"] == "artifact_not_found"
        assert "not a valid UUID" in response["error"]["message"]

    def test_manager_called_with_parsed_uuid(self) -> None:
        """McpArtifactProvider passes parsed UUID to DiagramManager."""
        diagram_id = uuid.uuid4()
        manager = _make_mock_manager(diagram_id)
        provider = McpArtifactProvider(diagram_manager=manager)

        provider.get_artifact(str(diagram_id))

        manager.get_diagram.assert_called_once_with(diagram_id)

    def test_error_message_contains_diagram_id(self) -> None:
        """Error response message references the requested diagram_id."""
        diagram_id = uuid.uuid4()
        manager = _make_mock_manager(
            diagram_id,
            raise_exc=Exception("not found"),
        )
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact(str(diagram_id))

        assert str(diagram_id) in response["error"]["message"]

    def test_node_graph_format_renders_as_summary_table(self) -> None:
        """node_graph format is rendered as node/edge summary tables, not raw JSON."""
        diagram_id = uuid.uuid4()
        node_graph_content = """{
            "schema_version": 1,
            "nodes": [
                {
                    "id": "node1",
                    "type": "box",
                    "label": "Node A",
                    "position": {"x": 0, "y": 0}
                },
                {
                    "id": "node2",
                    "type": "rounded",
                    "label": "Node B",
                    "position": {"x": 100, "y": 100}
                }
            ],
            "edges": [
                {
                    "id": "edge1",
                    "source": "node1",
                    "target": "node2",
                    "type": "flow",
                    "label": "connects to"
                }
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }"""
        manager = _make_mock_manager(
            diagram_id,
            payload_format="node_graph",
            content=node_graph_content,
            render_hint="react-flow",
        )
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact(str(diagram_id))

        assert response["type"] == "artifact"
        assert response["error"] is None
        markdown = response["payload"]["markdown"]

        # Should contain node/edge tables instead of raw JSON
        assert "## Nodes" in markdown or "| ID | Type | Label |" in markdown
        assert "## Edges" in markdown or "| Source → Target |" in markdown
        # Should NOT contain raw JSON code block for node_graph
        assert "```json" not in markdown or node_graph_content not in markdown
        # Should contain node and edge data
        assert "node1" in markdown
        assert "node2" in markdown
        assert "edge1" in markdown
        assert "Node A" in markdown
        assert "Node B" in markdown

    def test_node_graph_with_artifact_refs(self) -> None:
        """node_graph nodes with artifact_ref are rendered in the summary table."""
        diagram_id = uuid.uuid4()
        requirement_id = uuid.uuid4()
        node_graph_content = f"""{{
            "schema_version": 1,
            "nodes": [
                {{
                    "id": "req_node",
                    "type": "box",
                    "label": "REQ-001",
                    "position": {{"x": 0, "y": 0}},
                    "artifact_ref": {{
                        "entity_type": "Requirement",
                        "id": "{requirement_id}"
                    }}
                }}
            ],
            "edges": [],
            "viewport": {{"x": 0, "y": 0, "zoom": 1}}
        }}"""
        manager = _make_mock_manager(
            diagram_id,
            payload_format="node_graph",
            content=node_graph_content,
        )
        provider = McpArtifactProvider(diagram_manager=manager)

        response = provider.get_artifact(str(diagram_id))

        markdown = response["payload"]["markdown"]
        # Should contain artifact reference
        assert "Requirement" in markdown
        assert str(requirement_id) in markdown
