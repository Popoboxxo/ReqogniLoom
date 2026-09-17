"""
ARCH-L1-013 DiagramService — ``node_graph`` server-side SVG renderer.

GH-353 (Task 6): renders a ``node_graph`` payload dict (Task 1's schema,
:mod:`diagram.node_graph`) into a well-formed SVG string, exposed via
:meth:`diagram.renderer.DiagramRenderer.export_svg` and MCP's
``diagram.get(id, export_format="svg")``.

This module is the sole place ``node_graph`` content becomes markup, so it
carries the full XSS-hardening burden — mirrors the ``canvas_editor.py``
hardening from PR #351/#352, applied to a structurally different (typed
node/edge, not freehand-stroke) payload.

Security design (must be followed exactly — every value below is untrusted
JSON, even though it is expected to have already passed
:func:`diagram.node_graph.validate_node_graph`):

* ``style.accent`` / ``style.line`` are enums (:data:`diagram.node_graph.
  STYLE_ACCENTS` / ``EDGE_LINE_STYLES``). Each is mapped to a fixed SVG
  attribute string via a **literal Python dict** (:data:`_ACCENT_COLORS` /
  :data:`_LINE_DASH`) — the enum value itself is never string-interpolated
  into markup. An unmapped value raises :class:`NodeGraphRenderError`
  rather than silently falling back to a default (defense-in-depth: the
  validator already rejects unknown enum values at write time).
* ``position`` / ``size`` / ``viewport.zoom`` are the only numeric fields;
  every one is routed through the single :func:`_num_attr` coercion helper,
  which rejects non-finite values (``NaN``, ``inf``) by raising rather
  than substituting a default, and formats with fixed precision — never
  ``str(value)`` (or an f-string of the raw value) directly into markup.
* ``label`` (the only free-text field reaching this renderer) is emitted
  **only** as the text content of an SVG ``<text>`` element, XML-escaped
  via :func:`diagram.svg_safety.escape_xml_text`, never as an attribute
  value and never string-interpolated into a ``style=``/``d=``/``points=``
  attribute.
* Unknown ``node.type`` / ``edge.type`` values raise
  :class:`NodeGraphRenderError` — they do not fall through to a default
  shape silently. This should be unreachable for a payload that passed
  :func:`diagram.node_graph.validate_node_graph`, but this renderer trusts
  that contract only as a performance optimisation (it skips re-running
  full structural validation), not as a safety boundary: every
  security-critical primitive is independently re-checked here.

Design notes:
  This module is a PURE function boundary — like :mod:`diagram.node_graph`,
  it never touches the database and never imports Django/``rest_api``.
  Its only intra-app dependencies are :mod:`diagram.node_graph` (schema
  enum constants, reused for consistency-asserted enum maps below) and
  :mod:`diagram.svg_safety` (shared XML escaping — see that module's
  docstring for why numeric coercion is *not* also shared with
  :mod:`diagram.canvas_editor`, and why the escaping helper lives in its
  own leaf module rather than being imported from ``canvas_editor``
  directly: importing ``canvas_editor`` here would close an import cycle
  through ``diagram.manager`` -> ``diagram.renderer``).
"""
from __future__ import annotations

import math
from typing import Any, Optional

from diagram.node_graph import EDGE_LINE_STYLES, EDGE_TYPES, NODE_TYPES, STYLE_ACCENTS
from diagram.svg_safety import escape_xml_text


class NodeGraphRenderError(ValueError):
    """Raised when a ``node_graph`` payload cannot be safely rendered to SVG.

    Reached only if :func:`diagram.node_graph.validate_node_graph` was
    skipped, ignored, or somehow bypassed before reaching
    :func:`render_svg` — this is the render path's independent
    defense-in-depth backstop, not the primary validation gate.
    """


# ---------------------------------------------------------------------------
# Enum -> SVG attribute maps (literal dicts — the enum value itself is never
# string-interpolated into markup; only these pre-defined, safe strings are).
# ---------------------------------------------------------------------------

_ACCENT_COLORS: dict[str, str] = {
    "default": "#94a3b8",
    "primary": "#2563eb",
    "success": "#16a34a",
    "warning": "#d97706",
    "danger": "#dc2626",
    "muted": "#cbd5e1",
}

_LINE_DASH: dict[str, str] = {
    "solid": "",
    "dashed": "6,4",
}

# Every edge type maps to a fixed marker directive; "" means "no marker".
# Literal dict, same rationale as _ACCENT_COLORS/_LINE_DASH above.
_EDGE_TYPE_MARKER: dict[str, str] = {
    "flow": "arrow",
    "association": "",
    "dependency": "arrow",
    "containment": "diamond",
}

# Fixed shape renderers per node type — populated after the render
# functions are defined below (see _NODE_RENDERERS assignment). Declaring
# the type here documents the dispatch-table shape.
_NODE_RENDERERS: dict[str, Any]

# Consistency guards: every schema enum value from diagram.node_graph must
# have a mapping entry here, or a validator-accepted payload could still
# reach an "unmapped enum" raise below purely because this module's maps
# drifted out of sync with the schema. Fails fast at import time.
#
# Note: these are maintenance/CI guards, not the live security boundary --
# `assert` is stripped under `python -O`. The actual defense against a
# hostile/unmapped enum value is the per-call dict lookup + `except
# KeyError: raise NodeGraphRenderError(...)` in _accent_color/
# _line_dasharray/_render_edge below, which is not an `assert` and cannot
# be optimized away.
assert set(_ACCENT_COLORS) == STYLE_ACCENTS, "accent color map out of sync with STYLE_ACCENTS"
assert set(_LINE_DASH) == EDGE_LINE_STYLES, "line dash map out of sync with EDGE_LINE_STYLES"
assert set(_EDGE_TYPE_MARKER) == EDGE_TYPES, "edge marker map out of sync with EDGE_TYPES"

_DEFAULT_ACCENT = "default"
_DEFAULT_LINE = "solid"
_DEFAULT_NODE_WIDTH = 160.0
_DEFAULT_NODE_HEIGHT = 56.0
_NUMERIC_PRECISION = 2
_CANVAS_MARGIN = 40.0
_MIN_CANVAS_SIZE = 200.0
_EDGE_STROKE = "#475569"

_MISSING = object()


# ---------------------------------------------------------------------------
# Small internal helpers — the security-critical primitives.
# ---------------------------------------------------------------------------

def _finite_float(value: Any) -> float:
    """Coerce *value* to a finite float, or raise.

    Mirrors :func:`diagram.node_graph._is_finite_number`'s definition of
    "finite number" (int/float, excluding ``bool``, and ``math.isfinite``),
    but — unlike that validator-side helper, which only returns a bool for
    a yes/no check — this raises :class:`NodeGraphRenderError` immediately
    so every call site fails loudly instead of needing its own branch.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NodeGraphRenderError(f"Expected a finite number, got {value!r}.")
    number = float(value)
    if not math.isfinite(number):
        raise NodeGraphRenderError(f"Expected a finite number, got {value!r}.")
    return number


def _require_dict_or_none(value: Any, field_name: str) -> dict:
    """Return *value* if it's a dict, ``{}`` if it's ``None``/absent, else raise.

    Review fix (round 1): ``position``/``size``/``style`` were previously read
    via bare ``(value or {}).get(...)`` — correct for ``None``/absent, but a
    non-dict *truthy* value (a list, string, or number — exactly the
    "validation was bypassed" threat model this module's docstring calls
    out) made ``.get()`` raise an uncaught ``AttributeError`` instead of the
    intended :class:`NodeGraphRenderError`. Mirrors the ``isinstance``
    guard :func:`_viewport_attrs` already used for ``viewport`` — applied
    consistently here so every "should be an object" field fails the same
    way.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise NodeGraphRenderError(
            f"Expected {field_name!r} to be a JSON object, got {value!r}."
        )
    return value


def _num_attr(value: Any) -> str:
    """Render an untrusted numeric field as a safe, fixed-precision SVG value.

    Rejects non-finite values (``NaN``, ``inf``) by raising rather than
    substituting a default — this renderer's contract is to trust
    :func:`diagram.node_graph.validate_node_graph` already ran, so a
    non-finite number reaching here means that contract was violated and
    the safe response is to refuse to render, not guess a fallback.
    Never ``str(value)`` — always fixed precision, so the output can never
    contain characters an attribute-injection payload would need (quotes,
    angle brackets, letters).
    """
    return f"{_finite_float(value):.{_NUMERIC_PRECISION}f}"


def _accent_color(style: Any) -> str:
    """Map ``style.accent`` to a fixed SVG color via the literal dict above."""
    style = _require_dict_or_none(style, "style")
    accent = style.get("accent", _DEFAULT_ACCENT)
    try:
        return _ACCENT_COLORS[accent]
    except KeyError as exc:
        raise NodeGraphRenderError(f"Unknown style.accent value: {accent!r}.") from exc


def _line_dasharray(style: Any) -> str:
    """Map ``style.line`` to a fixed SVG dasharray via the literal dict above."""
    style = _require_dict_or_none(style, "style")
    line = style.get("line", _DEFAULT_LINE)
    try:
        return _LINE_DASH[line]
    except KeyError as exc:
        raise NodeGraphRenderError(f"Unknown style.line value: {line!r}.") from exc


def _label_text(label: Any, x: str, y: str) -> str:
    """Render *label* as escaped ``<text>`` element content (never an attribute).

    Args:
        label: The untrusted, free-text label value.
        x:     Pre-computed, already-safe SVG numeric string (from
               :func:`_num_attr`) — safe to interpolate directly since it
               can only contain digits, ``.`` and ``-``.
        y:     Same as *x*.
    """
    text = escape_xml_text("" if label is None else label)
    return (
        f'<text x="{x}" y="{y}" text-anchor="middle" '
        f'dominant-baseline="middle" font-size="12">{text}</text>'
    )


def _node_geometry_floats(node: dict) -> tuple[float, float, float, float]:
    """Return (x, y, width, height) as validated finite floats."""
    position = _require_dict_or_none(node.get("position"), "position")
    size = _require_dict_or_none(node.get("size"), "size")
    x = _finite_float(position.get("x"))
    y = _finite_float(position.get("y"))
    w = _finite_float(size.get("width", _DEFAULT_NODE_WIDTH))
    h = _finite_float(size.get("height", _DEFAULT_NODE_HEIGHT))
    return x, y, w, h


def _node_anchor(node: dict, handle: Optional[str]) -> tuple[float, float]:
    """Return the (x, y) point on *node*'s bounding box for a given handle.

    ``handle`` is one of :data:`diagram.node_graph.HANDLE_POSITIONS`
    (``top``/``right``/``bottom``/``left``) or ``None`` — an edge without an
    explicit handle anchors at the node's center.
    """
    x, y, w, h = _node_geometry_floats(node)
    if handle == "top":
        return x + w / 2, y
    if handle == "right":
        return x + w, y + h / 2
    if handle == "bottom":
        return x + w / 2, y + h
    if handle == "left":
        return x, y + h / 2
    return x + w / 2, y + h / 2


# ---------------------------------------------------------------------------
# Node shape rendering — dispatch dict; an unknown type raises, it does not
# fall through to a default shape (see module docstring).
# ---------------------------------------------------------------------------

def _render_box(x: float, y: float, w: float, h: float, accent: str) -> str:
    return (
        f'<rect x="{_num_attr(x)}" y="{_num_attr(y)}" '
        f'width="{_num_attr(w)}" height="{_num_attr(h)}" '
        f'fill="#ffffff" stroke="{accent}" stroke-width="1.5" />'
    )


def _render_rounded(x: float, y: float, w: float, h: float, accent: str) -> str:
    return (
        f'<rect x="{_num_attr(x)}" y="{_num_attr(y)}" '
        f'width="{_num_attr(w)}" height="{_num_attr(h)}" '
        f'rx="8" ry="8" fill="#ffffff" stroke="{accent}" stroke-width="1.5" />'
    )


def _render_ellipse(x: float, y: float, w: float, h: float, accent: str) -> str:
    return (
        f'<ellipse cx="{_num_attr(x + w / 2)}" cy="{_num_attr(y + h / 2)}" '
        f'rx="{_num_attr(w / 2)}" ry="{_num_attr(h / 2)}" '
        f'fill="#ffffff" stroke="{accent}" stroke-width="1.5" />'
    )


def _render_diamond(x: float, y: float, w: float, h: float, accent: str) -> str:
    corners = (
        (x + w / 2, y),
        (x + w, y + h / 2),
        (x + w / 2, y + h),
        (x, y + h / 2),
    )
    points = " ".join(f"{_num_attr(px)},{_num_attr(py)}" for px, py in corners)
    return f'<polygon points="{points}" fill="#ffffff" stroke="{accent}" stroke-width="1.5" />'


def _render_note(x: float, y: float, w: float, h: float, accent: str) -> str:
    fold_height = min(h, 16.0)  # capped header band
    body = (
        f'<rect x="{_num_attr(x)}" y="{_num_attr(y)}" '
        f'width="{_num_attr(w)}" height="{_num_attr(h)}" '
        f'fill="#fffbea" stroke="{accent}" stroke-width="1.5" />'
    )
    header = (
        f'<rect x="{_num_attr(x)}" y="{_num_attr(y)}" '
        f'width="{_num_attr(w)}" height="{_num_attr(fold_height)}" '
        f'fill="{accent}" opacity="0.35" />'
    )
    return body + header


def _render_group(x: float, y: float, w: float, h: float, accent: str) -> str:
    return (
        f'<rect x="{_num_attr(x)}" y="{_num_attr(y)}" '
        f'width="{_num_attr(w)}" height="{_num_attr(h)}" '
        f'fill="none" stroke="{accent}" stroke-width="1.5" stroke-dasharray="4,4" />'
    )


_NODE_RENDERERS = {
    "box": _render_box,
    "rounded": _render_rounded,
    "ellipse": _render_ellipse,
    "diamond": _render_diamond,
    "note": _render_note,
    "group": _render_group,
}
# Same maintenance/CI-guard caveat as the enum-map asserts above: the live
# defense against an unknown node.type is _render_node's `.get(node_type,
# _MISSING)` + explicit `is _MISSING` check below, not this assert.
assert set(_NODE_RENDERERS) == NODE_TYPES, "node renderer map out of sync with NODE_TYPES"


def _render_node(node: dict) -> str:
    node_type = node.get("type")
    renderer_fn = _NODE_RENDERERS.get(node_type, _MISSING)
    if renderer_fn is _MISSING:
        raise NodeGraphRenderError(f"Unknown node type: {node_type!r}.")

    node_id_attr = escape_xml_text(node.get("id", ""))
    accent = _accent_color(node.get("style"))
    x, y, w, h = _node_geometry_floats(node)

    shape_svg = renderer_fn(x, y, w, h, accent)
    # Group labels sit at the top of the bounding box (they annotate a
    # container, not a centered shape); every other node type centers its
    # label inside the shape.
    label_cy = y + 14.0 if node_type == "group" else y + h / 2
    label_svg = _label_text(node.get("label"), _num_attr(x + w / 2), _num_attr(label_cy))

    return f'<g id="{node_id_attr}">{shape_svg}{label_svg}</g>'


# ---------------------------------------------------------------------------
# Edge rendering.
# ---------------------------------------------------------------------------

_DEFS_BLOCK = (
    "  <defs>\n"
    '    <marker id="ng-arrow" markerWidth="10" markerHeight="8" '
    'refX="9" refY="4" orient="auto">\n'
    f'      <polygon points="0 0, 10 4, 0 8" fill="{_EDGE_STROKE}" />\n'
    "    </marker>\n"
    '    <marker id="ng-diamond" markerWidth="12" markerHeight="8" '
    'refX="1" refY="4" orient="auto">\n'
    f'      <polygon points="1 4, 6 0, 11 4, 6 8" fill="#ffffff" stroke="{_EDGE_STROKE}" />\n'
    "    </marker>\n"
    "  </defs>"
)


def _render_edge(edge: dict, node_index: dict[str, dict]) -> str:
    if not isinstance(edge, dict):
        raise NodeGraphRenderError(f"Malformed edge entry: {edge!r}.")

    edge_type = edge.get("type")
    marker = _EDGE_TYPE_MARKER.get(edge_type, _MISSING)
    if marker is _MISSING:
        raise NodeGraphRenderError(f"Unknown edge type: {edge_type!r}.")

    source_node = node_index.get(edge.get("source"))
    target_node = node_index.get(edge.get("target"))
    if source_node is None or target_node is None:
        raise NodeGraphRenderError(
            f"Edge {edge.get('id')!r} references an unknown node id "
            "(source/target — validation should have caught this)."
        )

    sx, sy = _node_anchor(source_node, edge.get("source_handle"))
    tx, ty = _node_anchor(target_node, edge.get("target_handle"))

    dasharray = _line_dasharray(edge.get("style"))
    dash_attr = f' stroke-dasharray="{dasharray}"' if dasharray else ""

    marker_attr = ""
    if marker == "arrow":
        marker_attr = ' marker-end="url(#ng-arrow)"'
    elif marker == "diamond":
        marker_attr = ' marker-start="url(#ng-diamond)"'

    edge_id_attr = escape_xml_text(edge.get("id", ""))
    x1, y1, x2, y2 = _num_attr(sx), _num_attr(sy), _num_attr(tx), _num_attr(ty)

    line_svg = (
        f'<line id="{edge_id_attr}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{_EDGE_STROKE}" stroke-width="1.5"{dash_attr}{marker_attr} />'
    )

    label = edge.get("label")
    if label:
        mx = _num_attr((sx + tx) / 2)
        my = _num_attr((sy + ty) / 2)
        return line_svg + _label_text(label, mx, my)
    return line_svg


# ---------------------------------------------------------------------------
# Canvas sizing + viewport metadata.
# ---------------------------------------------------------------------------

def _canvas_dimensions(nodes: list[dict]) -> tuple[str, str]:
    max_x = _MIN_CANVAS_SIZE
    max_y = _MIN_CANVAS_SIZE
    for node in nodes:
        x, y, w, h = _node_geometry_floats(node)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)
    return _num_attr(max_x + _CANVAS_MARGIN), _num_attr(max_y + _CANVAS_MARGIN)


def _viewport_attrs(viewport: Any) -> str:
    """Render optional ``viewport.{x,y,zoom}`` as ``data-*`` attributes.

    These are the only ``viewport`` numeric fields in the schema (see
    :mod:`diagram.node_graph`); each is routed through :func:`_num_attr`
    like every other numeric field, per the module's safety contract.
    """
    if not isinstance(viewport, dict):
        return ""
    parts: list[str] = []
    for key in ("x", "y", "zoom"):
        if key in viewport and viewport[key] is not None:
            parts.append(f'data-viewport-{key}="{_num_attr(viewport[key])}"')
    return (" " + " ".join(parts)) if parts else ""


# ---------------------------------------------------------------------------
# Public interface.
# ---------------------------------------------------------------------------

def render_svg(payload: dict) -> str:
    """Render a ``node_graph`` payload dict to a well-formed SVG string.

    Assumes *payload* has already passed
    :func:`diagram.node_graph.validate_node_graph` — this function does not
    re-run structural validation (required fields, id charset, dangling
    edge references, ...), it trusts the caller ran that first. It DOES
    independently re-check every security-critical primitive (finite
    numbers, known enum values, known node/edge types, escaped label text)
    regardless of that trust, since a caller could still hand it a payload
    that bypassed validation (see module docstring).

    Args:
        payload: A ``node_graph`` payload dict (``schema_version``/
            ``nodes``/``edges``/``viewport``).

    Returns:
        A well-formed SVG string.

    Raises:
        NodeGraphRenderError: If the payload is structurally unusable
            (missing ``nodes``/``edges`` lists, malformed entries), or a
            node/edge carries an unknown type/enum value, or a numeric
            field is non-finite — every one of these should be unreachable
            for a payload that passed ``validate_node_graph``, so reaching
            this exception signals the caller skipped validation.
    """
    if not isinstance(payload, dict):
        raise NodeGraphRenderError("node_graph payload must be a dict.")

    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list):
        raise NodeGraphRenderError("node_graph payload is missing a 'nodes' list.")
    if not isinstance(edges, list):
        raise NodeGraphRenderError("node_graph payload is missing an 'edges' list.")

    node_index: dict[str, dict] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise NodeGraphRenderError(f"Malformed node entry: {node!r}.")
        node_index[node["id"]] = node

    width, height = _canvas_dimensions(nodes)

    # Groups render first (background containers) so their bounding boxes
    # never visually cover sibling/child node shapes drawn on top.
    group_nodes = [n for n in nodes if n.get("type") == "group"]
    other_nodes = [n for n in nodes if n.get("type") != "group"]
    node_svg = [_render_node(n) for n in group_nodes] + [_render_node(n) for n in other_nodes]
    edge_svg = [_render_edge(e, node_index) for e in edges]

    body = "\n  ".join(node_svg + edge_svg)
    viewport_attrs = _viewport_attrs(payload.get("viewport"))

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"{viewport_attrs}>\n'
        f"{_DEFS_BLOCK}\n"
        f"  {body}\n"
        f"</svg>"
    )


__all__ = ["render_svg", "NodeGraphRenderError"]
