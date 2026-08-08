"""
Node Graph payload format — unit tests (GH-353 Task 1).

Covers ``diagram.node_graph.validate_node_graph`` / ``extract_artifact_refs``
directly (pure functions, no database). Wiring into
``DiagramValidator.validate_payload`` is covered separately in
test_validator.py.
"""
from __future__ import annotations

import copy
import uuid

import pytest

from diagram.node_graph import extract_artifact_refs, validate_node_graph
from diagram.validator import ValidationResult

VALID_NODE_GRAPH: dict = {
    "schema_version": 1,
    "nodes": [
        {
            "id": "grp-1",
            "type": "group",
            "label": "Auth Subsystem",
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "n-7f3a2c",
            "type": "box",
            "label": "Auth Service",
            "position": {"x": 120, "y": 40},
            "size": {"width": 180, "height": 64},
            "style": {"accent": "primary"},
            "artifact_ref": {
                "entity_type": "ArchitectureElement",
                "id": str(uuid.uuid4()),
            },
            "parent_id": "grp-1",
        },
        {
            "id": "n-91bc4d",
            "type": "rounded",
            "label": "Token Store",
            "position": {"x": 320, "y": 40},
        },
    ],
    "edges": [
        {
            "id": "e-0b91",
            "source": "n-7f3a2c",
            "target": "n-91bc4d",
            "type": "flow",
            "label": "",
            "source_handle": "bottom",
            "target_handle": "top",
            "style": {"line": "solid"},
        },
    ],
    "viewport": {"x": 0, "y": 0, "zoom": 1},
}


def _graph(**overrides) -> dict:
    """Deep-copy the valid fixture and apply top-level overrides."""
    data = copy.deepcopy(VALID_NODE_GRAPH)
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_valid_graph_passes(self) -> None:
        result = validate_node_graph(VALID_NODE_GRAPH)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.error_msg == ""
        assert result.diagram_type == "node_graph"

    def test_minimal_empty_graph_passes(self) -> None:
        result = validate_node_graph({"schema_version": 1, "nodes": [], "edges": []})
        assert result.is_valid is True

    def test_viewport_is_optional(self) -> None:
        data = _graph()
        del data["viewport"]
        result = validate_node_graph(data)
        assert result.is_valid is True

    def test_node_without_optional_fields_passes(self) -> None:
        data = {
            "schema_version": 1,
            "nodes": [
                {
                    "id": "n-1",
                    "type": "box",
                    "label": "",
                    "position": {"x": 0, "y": 0},
                }
            ],
            "edges": [],
        }
        result = validate_node_graph(data)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Invariant 1: dangling edge endpoint
# ---------------------------------------------------------------------------

class TestDanglingEdgeEndpoint:
    def test_dangling_source_rejected(self) -> None:
        data = _graph()
        data["edges"][0]["source"] = "does-not-exist"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "source" in result.error_msg
        assert "does-not-exist" in result.error_msg

    def test_dangling_target_rejected(self) -> None:
        data = _graph()
        data["edges"][0]["target"] = "does-not-exist"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "target" in result.error_msg


# ---------------------------------------------------------------------------
# Unknown node type
# ---------------------------------------------------------------------------

class TestUnknownNodeType:
    def test_unknown_node_type_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["type"] = "hexagon"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "type" in result.error_msg

    def test_unknown_edge_type_rejected(self) -> None:
        data = _graph()
        data["edges"][0]["type"] = "teleports-to"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "type" in result.error_msg


# ---------------------------------------------------------------------------
# Invariant 2: non-group parent_id target
# ---------------------------------------------------------------------------

class TestParentIdInvariant:
    def test_non_group_parent_target_rejected(self) -> None:
        data = _graph()
        # Point node[1]'s parent_id at node[2], which is type='rounded' (not group).
        data["nodes"][1]["parent_id"] = "n-91bc4d"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "not a group" in result.error_msg

    def test_dangling_parent_id_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["parent_id"] = "does-not-exist"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "unknown node id" in result.error_msg

    def test_group_parent_target_accepted(self) -> None:
        # Sanity check the happy-path fixture already exercises this.
        data = _graph()
        assert data["nodes"][1]["parent_id"] == "grp-1"
        result = validate_node_graph(data)
        assert result.is_valid is True

    def test_null_parent_id_accepted(self) -> None:
        data = _graph()
        data["nodes"][1]["parent_id"] = None
        result = validate_node_graph(data)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Invariant 3: caps
# ---------------------------------------------------------------------------

class TestCaps:
    def test_over_cap_nodes_rejected(self) -> None:
        nodes = [
            {
                "id": f"n-{i}",
                "type": "box",
                "label": "",
                "position": {"x": i, "y": i},
            }
            for i in range(501)
        ]
        data = {"schema_version": 1, "nodes": nodes, "edges": []}
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "500" in result.error_msg

    def test_over_cap_edges_rejected(self) -> None:
        nodes = [
            {"id": "a", "type": "box", "label": "", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "box", "label": "", "position": {"x": 1, "y": 1}},
        ]
        edges = [
            {"id": f"e-{i}", "source": "a", "target": "b", "type": "flow"}
            for i in range(1001)
        ]
        data = {"schema_version": 1, "nodes": nodes, "edges": edges}
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "1000" in result.error_msg

    def test_label_over_max_length_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["label"] = "x" * 501
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "500" in result.error_msg

    def test_id_over_max_length_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["id"] = "x" * 65
        result = validate_node_graph(data)
        assert result.is_valid is False

    def test_duplicate_node_id_rejected(self) -> None:
        data = _graph()
        data["nodes"][2]["id"] = data["nodes"][0]["id"]
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "Duplicate node id" in result.error_msg

    def test_duplicate_edge_id_rejected(self) -> None:
        data = _graph()
        data["edges"].append(dict(data["edges"][0]))
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "Duplicate edge id" in result.error_msg


# ---------------------------------------------------------------------------
# Invariant 4: artifact_ref
# ---------------------------------------------------------------------------

class TestArtifactRef:
    def test_bad_entity_type_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["artifact_ref"]["entity_type"] = "NotARealType"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "entity_type" in result.error_msg

    def test_non_uuid_id_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["artifact_ref"]["id"] = "not-a-uuid"
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "artifact_ref.id" in result.error_msg

    @pytest.mark.parametrize(
        "entity_type",
        [
            "Requirement",
            "StakeholderNeed",
            "ArchitectureElement",
            "TestCase",
            "Adr",
            "Risk",
            "Issue",
            "GlossaryTerm",
            "Goal",
            "MainGoal",
        ],
    )
    def test_every_known_entity_type_accepted(self, entity_type: str) -> None:
        data = _graph()
        data["nodes"][1]["artifact_ref"] = {
            "entity_type": entity_type,
            "id": str(uuid.uuid4()),
        }
        result = validate_node_graph(data)
        assert result.is_valid is True

    def test_missing_entity_type_rejected(self) -> None:
        data = _graph()
        del data["nodes"][1]["artifact_ref"]["entity_type"]
        result = validate_node_graph(data)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# schema_version
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    def test_missing_schema_version_rejected(self) -> None:
        data = _graph()
        del data["schema_version"]
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "schema_version" in result.error_msg

    def test_wrong_schema_version_rejected(self) -> None:
        data = _graph(schema_version=2)
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "schema_version" in result.error_msg


# ---------------------------------------------------------------------------
# Structural type errors
# ---------------------------------------------------------------------------

class TestStructuralErrors:
    def test_non_dict_payload_rejected(self) -> None:
        result = validate_node_graph([])  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_nodes_not_list_rejected(self) -> None:
        data = _graph(nodes={"not": "a list"})
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "nodes" in result.error_msg

    def test_edges_not_list_rejected(self) -> None:
        data = _graph(edges="not-a-list")
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "edges" in result.error_msg

    def test_missing_position_rejected(self) -> None:
        data = _graph()
        del data["nodes"][1]["position"]
        result = validate_node_graph(data)
        assert result.is_valid is False
        assert "position" in result.error_msg

    def test_non_finite_position_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["position"] = {"x": float("inf"), "y": 0}
        result = validate_node_graph(data)
        assert result.is_valid is False

    def test_zero_size_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["size"] = {"width": 0, "height": 10}
        result = validate_node_graph(data)
        assert result.is_valid is False

    def test_style_with_extra_key_rejected(self) -> None:
        data = _graph()
        data["nodes"][1]["style"] = {"accent": "primary", "color": "#fff"}
        result = validate_node_graph(data)
        assert result.is_valid is False

    def test_invalid_handle_rejected(self) -> None:
        data = _graph()
        data["edges"][0]["source_handle"] = "north-by-northwest"
        result = validate_node_graph(data)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# extract_artifact_refs
# ---------------------------------------------------------------------------

class TestExtractArtifactRefs:
    def test_extracts_only_populated_refs(self) -> None:
        refs = extract_artifact_refs(VALID_NODE_GRAPH)
        assert len(refs) == 1
        node_id, artifact_ref = refs[0]
        assert node_id == "n-7f3a2c"
        assert artifact_ref["entity_type"] == "ArchitectureElement"

    def test_empty_graph_returns_empty_list(self) -> None:
        assert extract_artifact_refs({"schema_version": 1, "nodes": [], "edges": []}) == []

    def test_missing_nodes_key_returns_empty_list(self) -> None:
        assert extract_artifact_refs({}) == []

    def test_non_dict_payload_returns_empty_list(self) -> None:
        assert extract_artifact_refs([]) == []  # type: ignore[arg-type]
