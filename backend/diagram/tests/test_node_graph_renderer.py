"""
``node_graph`` server-side SVG renderer — unit tests (GH-353 Task 6).

Covers:
  - Happy path: every node type / every edge type renders parseable SVG.
  - Golden-file test: a known-good payload's rendered SVG matches a
    checked-in expected string exactly.
  - Adversarial / security tests: hostile ``style.accent``, hostile
    ``label``, non-finite ``position.x``, unknown node/edge type — all must
    be rejected/escaped by the renderer independently of
    ``node_graph.validate_node_graph`` (defense-in-depth backstop).

No database access — :func:`diagram.node_graph_renderer.render_svg` is a
pure function.
"""
from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

import pytest

from diagram.node_graph import EDGE_TYPES, NODE_TYPES
from diagram.node_graph_renderer import NodeGraphRenderError, render_svg

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_NODE_GRAPH: dict = {
    "schema_version": 1,
    "nodes": [
        {
            "id": "grp-1",
            "type": "group",
            "label": "Auth Subsystem",
            "position": {"x": 0, "y": 0},
            "size": {"width": 300, "height": 160},
        },
        {
            "id": "n-box",
            "type": "box",
            "label": "Auth Service",
            "position": {"x": 20, "y": 40},
            "size": {"width": 120, "height": 50},
            "style": {"accent": "primary"},
            "parent_id": "grp-1",
        },
        {
            "id": "n-rounded",
            "type": "rounded",
            "label": "Token Store",
            "position": {"x": 160, "y": 40},
        },
    ],
    "edges": [
        {
            "id": "e-1",
            "source": "n-box",
            "target": "n-rounded",
            "type": "flow",
            "label": "issues",
            "source_handle": "right",
            "target_handle": "left",
            "style": {"line": "solid"},
        },
    ],
    "viewport": {"x": 0, "y": 0, "zoom": 1},
}


def _graph(**overrides) -> dict:
    data = copy.deepcopy(VALID_NODE_GRAPH)
    data.update(overrides)
    return data


def _assert_parseable(svg: str) -> ET.Element:
    """Parse *svg* and fail with the SVG body on any XML error."""
    try:
        return ET.fromstring(svg)
    except ET.ParseError as exc:  # pragma: no cover - failure path only
        pytest.fail(f"Rendered SVG is not well-formed XML: {exc}\n---\n{svg}")


def _assert_no_attribute_breakout(svg: str) -> None:
    """Fail if the SVG contains an injected element/attribute.

    Mirrors ``test_canvas_editor._assert_no_attribute_breakout`` — parsing
    is the authoritative check: a payload that broke out of its attribute
    quotes shows up as an additional parsed attribute (or an extra
    element), whereas a properly escaped payload stays a single inert
    attribute value no matter what characters it contains.
    """
    assert "<!DOCTYPE" not in svg
    assert "<!ENTITY" not in svg
    root = _assert_parseable(svg)
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        assert tag != "script", f"injected <script> element: {svg}"
        for name, value in node.attrib.items():
            assert not name.lower().startswith("on"), (
                f"injected event handler attribute {name!r}: {svg}"
            )
            assert not value.strip().lower().startswith("javascript:"), (
                f"injected javascript: URL in {name!r}: {svg}"
            )


# ---------------------------------------------------------------------------
# Golden-file test
# ---------------------------------------------------------------------------

GOLDEN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="360.00" height="240.00" '
    'viewBox="0 0 360.00 240.00" data-viewport-x="0.00" data-viewport-y="0.00" '
    'data-viewport-zoom="1.00">\n'
    "  <defs>\n"
    '    <marker id="ng-arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">\n'
    '      <polygon points="0 0, 10 4, 0 8" fill="#475569" />\n'
    "    </marker>\n"
    '    <marker id="ng-diamond" markerWidth="12" markerHeight="8" refX="1" refY="4" orient="auto">\n'
    '      <polygon points="1 4, 6 0, 11 4, 6 8" fill="#ffffff" stroke="#475569" />\n'
    "    </marker>\n"
    "  </defs>\n"
    '  <g id="grp-1"><rect x="0.00" y="0.00" width="300.00" height="160.00" '
    'fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,4" />'
    '<text x="150.00" y="14.00" text-anchor="middle" dominant-baseline="middle" '
    'font-size="12">Auth Subsystem</text></g>\n'
    '  <g id="n-box"><rect x="20.00" y="40.00" width="120.00" height="50.00" '
    'fill="#ffffff" stroke="#2563eb" stroke-width="1.5" />'
    '<text x="80.00" y="65.00" text-anchor="middle" dominant-baseline="middle" '
    'font-size="12">Auth Service</text></g>\n'
    '  <g id="n-rounded"><rect x="160.00" y="40.00" width="160.00" height="56.00" '
    'rx="8" ry="8" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5" />'
    '<text x="240.00" y="68.00" text-anchor="middle" dominant-baseline="middle" '
    'font-size="12">Token Store</text></g>\n'
    '  <line id="e-1" x1="140.00" y1="65.00" x2="160.00" y2="68.00" '
    'stroke="#475569" stroke-width="1.5" marker-end="url(#ng-arrow)" />'
    '<text x="150.00" y="66.50" text-anchor="middle" dominant-baseline="middle" '
    'font-size="12">issues</text>\n'
    "</svg>"
)


class TestGoldenFile:
    def test_known_good_payload_matches_expected_svg(self) -> None:
        svg = render_svg(VALID_NODE_GRAPH)
        assert svg == GOLDEN_SVG

    def test_golden_svg_is_well_formed(self) -> None:
        _assert_parseable(GOLDEN_SVG)


# ---------------------------------------------------------------------------
# Happy path: every node type / every edge type renders parseable SVG.
# ---------------------------------------------------------------------------

class TestEveryNodeType:
    @pytest.mark.parametrize("node_type", sorted(NODE_TYPES))
    def test_node_type_renders_parseable_svg(self, node_type: str) -> None:
        payload = {
            "schema_version": 1,
            "nodes": [
                {
                    "id": "n-1",
                    "type": node_type,
                    "label": f"A {node_type} node",
                    "position": {"x": 10, "y": 10},
                    "size": {"width": 100, "height": 60},
                }
            ],
            "edges": [],
        }
        svg = render_svg(payload)
        _assert_parseable(svg)
        assert f"A {node_type} node" in svg

    def test_all_node_types_covered_by_schema(self) -> None:
        """Guards against NODE_TYPES growing without a matching test case."""
        assert NODE_TYPES == {"box", "rounded", "ellipse", "diamond", "note", "group"}


class TestEveryEdgeType:
    @pytest.mark.parametrize("edge_type", sorted(EDGE_TYPES))
    def test_edge_type_renders_parseable_svg(self, edge_type: str) -> None:
        payload = {
            "schema_version": 1,
            "nodes": [
                {"id": "a", "type": "box", "label": "A", "position": {"x": 0, "y": 0}},
                {"id": "b", "type": "box", "label": "B", "position": {"x": 200, "y": 0}},
            ],
            "edges": [
                {"id": "e-1", "source": "a", "target": "b", "type": edge_type, "label": "rel"}
            ],
        }
        svg = render_svg(payload)
        _assert_parseable(svg)

    def test_all_edge_types_covered_by_schema(self) -> None:
        assert EDGE_TYPES == {"flow", "association", "dependency", "containment"}


class TestEmptyGraph:
    def test_empty_nodes_and_edges_renders_parseable_svg(self) -> None:
        svg = render_svg({"schema_version": 1, "nodes": [], "edges": []})
        _assert_parseable(svg)
        assert "<svg" in svg and "</svg>" in svg


# ---------------------------------------------------------------------------
# Adversarial: hostile accent value.
# ---------------------------------------------------------------------------

class TestHostileAccent:
    """Defense-in-depth: the validator already rejects unknown accents, but
    the renderer must independently refuse too (never fall back silently)."""

    def test_hostile_node_accent_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["style"] = {"accent": '0" onload="alert(1)'}
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_hostile_edge_line_style_raises(self) -> None:
        payload = _graph()
        payload["edges"][0]["style"] = {"line": '"><script>alert(1)</script>'}
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_unknown_but_plausible_accent_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["style"] = {"accent": "info"}  # not a real enum value
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)


# ---------------------------------------------------------------------------
# Adversarial: hostile label.
# ---------------------------------------------------------------------------

class TestHostileLabel:
    HOSTILE_LABEL = '</text><script>alert(1)</script><text>'

    def test_hostile_node_label_is_escaped_not_broken_out(self) -> None:
        payload = _graph()
        payload["nodes"][1]["label"] = self.HOSTILE_LABEL
        svg = render_svg(payload)
        _assert_no_attribute_breakout(svg)
        # No unescaped '<', '>' or bare '&' reach the emitted <text> content.
        assert "<script>" not in svg
        assert "</script>" not in svg
        assert "&lt;script&gt;" in svg

    def test_hostile_edge_label_is_escaped_not_broken_out(self) -> None:
        payload = _graph()
        payload["edges"][0]["label"] = self.HOSTILE_LABEL
        svg = render_svg(payload)
        _assert_no_attribute_breakout(svg)
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg

    def test_label_with_quotes_and_ampersand_is_escaped(self) -> None:
        payload = _graph()
        payload["nodes"][1]["label"] = 'A & B "quoted" \'single\''
        svg = render_svg(payload)
        _assert_parseable(svg)
        assert "&amp;" in svg
        assert "&quot;" in svg
        assert "&apos;" in svg

    def test_attribute_breakout_payload_in_label_stays_inert(self) -> None:
        """The same payload that breaks out of an *attribute* must not do
        so when it lands in <text> content instead.

        The literal word "onload" is expected to survive as inert, escaped
        text content (only the quote characters need escaping in text
        content) -- what matters, and what ``_assert_no_attribute_breakout``
        verifies via XML parsing, is that it never becomes a live
        ``onload=`` *attribute*.
        """
        payload = _graph()
        payload["nodes"][1]["label"] = '0" onload="alert(1)'
        svg = render_svg(payload)
        _assert_no_attribute_breakout(svg)
        assert '0&quot; onload=&quot;alert(1)' in svg


# ---------------------------------------------------------------------------
# Adversarial: non-finite numeric fields.
# ---------------------------------------------------------------------------

class TestNonFiniteNumbers:
    """Reachable only if validate_node_graph was bypassed — the renderer's
    own defense must still refuse rather than emit NaN/Infinity into SVG."""

    @pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
    def test_non_finite_position_x_raises(self, bad_value: float) -> None:
        payload = _graph()
        payload["nodes"][1]["position"]["x"] = bad_value
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    @pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
    def test_non_finite_position_y_raises(self, bad_value: float) -> None:
        payload = _graph()
        payload["nodes"][1]["position"]["y"] = bad_value
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_non_finite_size_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["size"] = {"width": math.nan, "height": 10}
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_non_finite_viewport_zoom_raises(self) -> None:
        payload = _graph()
        payload["viewport"]["zoom"] = math.inf
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_string_masquerading_as_number_raises(self) -> None:
        """A string value in a numeric-role field must never reach a raw
        f-string/str() call — this is the exact class of bug PR #351 fixed
        for canvas_editor; node_graph_renderer must refuse the same way."""
        payload = _graph()
        payload["nodes"][1]["position"]["x"] = '0" onload="alert(1)'
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_bool_in_numeric_field_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["position"]["x"] = True
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_none_in_numeric_field_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["position"]["x"] = None
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)


# ---------------------------------------------------------------------------
# Adversarial: unknown node/edge type — must raise, not fall through.
# ---------------------------------------------------------------------------

class TestUnknownTypes:
    def test_unknown_node_type_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["type"] = "hexagon"  # not in NODE_TYPES
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_unknown_edge_type_raises(self) -> None:
        payload = _graph()
        payload["edges"][0]["type"] = "teleports_to"  # not in EDGE_TYPES
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_empty_string_node_type_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["type"] = ""
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)

    def test_none_node_type_raises(self) -> None:
        payload = _graph()
        payload["nodes"][1]["type"] = None
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)


# ---------------------------------------------------------------------------
# Structural defense: malformed payload shapes.
# ---------------------------------------------------------------------------

class TestMalformedPayload:
    def test_non_dict_payload_raises(self) -> None:
        with pytest.raises(NodeGraphRenderError):
            render_svg("not a dict")  # type: ignore[arg-type]

    def test_missing_nodes_key_raises(self) -> None:
        with pytest.raises(NodeGraphRenderError):
            render_svg({"schema_version": 1, "edges": []})

    def test_missing_edges_key_raises(self) -> None:
        with pytest.raises(NodeGraphRenderError):
            render_svg({"schema_version": 1, "nodes": []})

    def test_edge_referencing_unknown_node_id_raises(self) -> None:
        """Reachable only if validation (which checks dangling refs) was
        bypassed -- the renderer independently refuses to guess."""
        payload = {
            "schema_version": 1,
            "nodes": [{"id": "a", "type": "box", "label": "A", "position": {"x": 0, "y": 0}}],
            "edges": [{"id": "e-1", "source": "a", "target": "ghost", "type": "flow"}],
        }
        with pytest.raises(NodeGraphRenderError):
            render_svg(payload)


# ---------------------------------------------------------------------------
# Whole-graph XSS regression sweep (mirrors test_canvas_editor's parametrized
# attribute-injection matrix, adapted to the node_graph schema).
# ---------------------------------------------------------------------------

_XSS_ATTR_PAYLOAD = '0" onload="alert(1)'

_HOSTILE_NODE_FIELD_CASES: list[dict] = [
    {"position": {"x": _XSS_ATTR_PAYLOAD, "y": 0}},
    {"position": {"x": 0, "y": _XSS_ATTR_PAYLOAD}},
    {"size": {"width": _XSS_ATTR_PAYLOAD, "height": 10}},
    {"size": {"width": 10, "height": _XSS_ATTR_PAYLOAD}},
    {"label": _XSS_ATTR_PAYLOAD},
    {"style": {"accent": _XSS_ATTR_PAYLOAD}},
]


class TestNodeFieldAttributeInjectionSweep:
    @pytest.mark.parametrize("overrides", _HOSTILE_NODE_FIELD_CASES)
    def test_hostile_field_never_breaks_out_or_renders_silently(self, overrides: dict) -> None:
        payload = _graph()
        node = payload["nodes"][1]
        for key, value in overrides.items():
            if isinstance(node.get(key), dict) and isinstance(value, dict):
                node[key].update(value)
            else:
                node[key] = value

        if "label" in overrides:
            # Label injection must be escaped, not rejected -- render
            # succeeds, and the escaped literal text is inert (see
            # TestHostileLabel.test_attribute_breakout_payload_in_label_stays_inert
            # for why the bare word "onload" surviving as text is expected).
            svg = render_svg(payload)
            _assert_no_attribute_breakout(svg)
            assert '0&quot; onload=&quot;alert(1)' in svg
        else:
            # Every other numeric/enum field must be rejected outright.
            with pytest.raises(NodeGraphRenderError):
                render_svg(payload)
