"""
canvas_json -> node_graph pure conversion — unit tests (GH-353 Task 7).

Covers ``diagram.canvas_to_node_graph.convert_canvas_json_to_node_graph``
directly (pure function, no database). The management command's
target-discovery + persistence wiring is covered separately in
test_convert_canvas_to_node_graph_command.py.
"""
from __future__ import annotations

from diagram.canvas_to_node_graph import convert_canvas_json_to_node_graph
from diagram.node_graph import validate_node_graph

# ---------------------------------------------------------------------------
# Fixtures: rects + a connector + a label
# ---------------------------------------------------------------------------

_TWO_RECTS_AND_CONNECTOR = {
    "objects": [
        {
            "type": "rect",
            "left": 10.0,
            "top": 20.0,
            "width": 100.0,
            "height": 50.0,
            "scaleX": 1.0,
            "scaleY": 1.0,
            "data": {"id": "shape-a", "type": "rect"},
        },
        {
            "type": "textbox",
            "left": 30.0,
            "top": 40.0,
            "text": "Shape A",
            "data": {"id": "label-a", "type": "label", "labelFor": "shape-a"},
        },
        {
            "type": "rect",
            "left": 300.0,
            "top": 20.0,
            "width": 80.0,
            "height": 40.0,
            "scaleX": 2.0,
            "scaleY": 1.5,
            "data": {"id": "shape-b", "type": "rect"},
        },
        {
            "type": "line",
            "x1": 110.0,
            "y1": 45.0,
            "x2": 300.0,
            "y2": 40.0,
            "data": {"id": "conn-1", "type": "connector", "fromId": "shape-a", "toId": "shape-b"},
        },
        {
            "type": "triangle",
            "data": {"type": "arrowHead", "connectorId": "conn-1"},
        },
    ]
}

_WITH_ELLIPSE = {
    "objects": [
        {
            "type": "ellipse",
            "left": 5.0,
            "top": 5.0,
            "rx": 25.0,
            "ry": 15.0,
            "scaleX": 1.0,
            "scaleY": 1.0,
            "data": {"id": "shape-e", "type": "ellipse"},
        },
    ]
}

_STANDALONE_TEXT = {
    "objects": [
        {
            "type": "textbox",
            "left": 1.0,
            "top": 2.0,
            "text": "A free note",
            "data": {"id": "note-1", "type": "text"},
        },
    ]
}

_WITH_FREEHAND_PATH = {
    "objects": [
        {
            "type": "rect",
            "left": 0.0,
            "top": 0.0,
            "width": 10.0,
            "height": 10.0,
            "data": {"id": "shape-a", "type": "rect"},
        },
        {
            "type": "path",
            "path": [["M", 0, 0], ["L", 10, 10]],
            # No `data` tag — genuine Fabric freehand pen stroke.
        },
    ]
}

_DANGLING_CONNECTOR = {
    "objects": [
        {
            "type": "rect",
            "left": 0.0,
            "top": 0.0,
            "width": 10.0,
            "height": 10.0,
            "data": {"id": "shape-a", "type": "rect"},
        },
        {
            "type": "line",
            "data": {"id": "conn-1", "type": "connector", "fromId": "shape-a", "toId": "missing-shape"},
        },
    ]
}

_WITH_ARTIFACT_REF = {
    "objects": [
        {
            "type": "rect",
            "left": 0.0,
            "top": 0.0,
            "width": 10.0,
            "height": 10.0,
            "data": {
                "id": "shape-a",
                "type": "rect",
                "artifact_ref": {"entity_type": "Requirement", "id": "11111111-1111-1111-1111-111111111111"},
            },
        },
    ]
}


# ---------------------------------------------------------------------------
# Happy path: rects + connector
# ---------------------------------------------------------------------------

class TestConvertRectsAndConnector:
    def test_converts_to_valid_node_graph(self) -> None:
        result = convert_canvas_json_to_node_graph(_TWO_RECTS_AND_CONNECTOR)

        assert result.ok is True
        assert result.payload is not None
        validation = validate_node_graph(result.payload)
        assert validation.is_valid, validation.error_msg

    def test_node_fields_mapped_from_fabric_geometry(self) -> None:
        result = convert_canvas_json_to_node_graph(_TWO_RECTS_AND_CONNECTOR)
        nodes = {n["id"]: n for n in result.payload["nodes"]}

        assert nodes["shape-a"]["type"] == "box"
        assert nodes["shape-a"]["position"] == {"x": 10.0, "y": 20.0}
        assert nodes["shape-a"]["size"] == {"width": 100.0, "height": 50.0}
        assert nodes["shape-a"]["label"] == "Shape A"  # folded from the label object

        # scaleX/scaleY applied to width/height.
        assert nodes["shape-b"]["size"] == {"width": 160.0, "height": 60.0}
        assert nodes["shape-b"]["label"] == ""  # no matching label object

    def test_arrowhead_is_skipped_not_a_node_or_edge(self) -> None:
        result = convert_canvas_json_to_node_graph(_TWO_RECTS_AND_CONNECTOR)
        assert len(result.payload["nodes"]) == 2
        assert len(result.payload["edges"]) == 1

    def test_connector_becomes_edge_with_source_and_target(self) -> None:
        result = convert_canvas_json_to_node_graph(_TWO_RECTS_AND_CONNECTOR)
        edge = result.payload["edges"][0]
        assert edge["id"] == "conn-1"
        assert edge["source"] == "shape-a"
        assert edge["target"] == "shape-b"


# ---------------------------------------------------------------------------
# Ellipse geometry
# ---------------------------------------------------------------------------

class TestConvertEllipse:
    def test_ellipse_maps_to_ellipse_node_from_rx_ry(self) -> None:
        result = convert_canvas_json_to_node_graph(_WITH_ELLIPSE)
        assert result.ok is True
        node = result.payload["nodes"][0]
        assert node["type"] == "ellipse"
        assert node["position"] == {"x": 5.0, "y": 5.0}
        assert node["size"] == {"width": 50.0, "height": 30.0}


# ---------------------------------------------------------------------------
# Standalone text -> note node
# ---------------------------------------------------------------------------

class TestConvertStandaloneText:
    def test_standalone_text_becomes_note_node(self) -> None:
        result = convert_canvas_json_to_node_graph(_STANDALONE_TEXT)
        assert result.ok is True
        node = result.payload["nodes"][0]
        assert node["type"] == "note"
        assert node["label"] == "A free note"


# ---------------------------------------------------------------------------
# Refusal: free-hand path objects
# ---------------------------------------------------------------------------

class TestRefusesFreehandPath:
    def test_refuses_diagram_with_freehand_path(self) -> None:
        result = convert_canvas_json_to_node_graph(_WITH_FREEHAND_PATH)
        assert result.ok is False
        assert result.payload is None
        assert "free-hand path" in result.reason

    def test_missing_objects_array_is_not_convertible(self) -> None:
        result = convert_canvas_json_to_node_graph({})
        assert result.ok is False

    def test_non_dict_input_is_not_convertible(self) -> None:
        result = convert_canvas_json_to_node_graph(None)  # type: ignore[arg-type]
        assert result.ok is False


# ---------------------------------------------------------------------------
# Dangling connector is dropped, not a hard refusal
# ---------------------------------------------------------------------------

class TestDanglingConnector:
    def test_dangling_connector_is_dropped_but_diagram_still_converts(self) -> None:
        result = convert_canvas_json_to_node_graph(_DANGLING_CONNECTOR)
        assert result.ok is True
        assert len(result.payload["nodes"]) == 1
        assert result.payload["edges"] == []


# ---------------------------------------------------------------------------
# artifact_ref passthrough (feeds Task 4's reconciler on write)
# ---------------------------------------------------------------------------

class TestArtifactRefPassthrough:
    def test_data_artifact_ref_is_copied_onto_the_node(self) -> None:
        result = convert_canvas_json_to_node_graph(_WITH_ARTIFACT_REF)
        assert result.ok is True
        node = result.payload["nodes"][0]
        assert node["artifact_ref"] == {
            "entity_type": "Requirement",
            "id": "11111111-1111-1111-1111-111111111111",
        }
        validation = validate_node_graph(result.payload)
        assert validation.is_valid, validation.error_msg
