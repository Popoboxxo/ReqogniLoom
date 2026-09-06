"""
ARCH-L1-013 DiagramService — canvas_json -> node_graph conversion (GH-353 Task 7).

Pure conversion of a Fabric.js ``canvas_json`` payload (the same per-object
``data.type`` discriminators ``CanvasEditor.tsx`` tags every shape with — see
``diagram/canvas_editor.py``'s ``_canvas_json_object_to_element``, the
SVG-preview sibling of this mapping, for the same object-tagging conventions)
into a ``node_graph`` v1 payload (:mod:`diagram.node_graph`).

Mirrors the "pure function boundary" convention of ``diagram/node_graph.py``:
this module never touches the database, never imports Django, and never
imports ``rest_api`` or any Ext-layer module. Its only caller is the
``convert_canvas_to_node_graph`` management command, which owns all
persistence (via ``DiagramManager``) and tenant-context handling.

Mapping rules (Task 7 brief):
  * ``data.type in {"rect", "ellipse", "circle"}`` -> a node_graph node.
    Position comes from Fabric's ``left``/``top``; size from
    ``width * scaleX`` / ``height * scaleY`` for rects, ``rx``/``ry`` (scaled,
    doubled) for ellipses/circles — mirroring
    ``canvas_editor._canvas_json_object_to_element``'s own rect/ellipse
    field reads.
  * ``data.type == "label"`` folds its text into the node named by
    ``data.labelFor``.
  * A standalone ``data.type == "text"`` (no ``labelFor`` companion, i.e. a
    freestanding textbox rather than a shape's label) becomes a
    ``note``-type node.
  * ``data.type == "connector"`` -> an edge with ``source = data.fromId``,
    ``target = data.toId``.
  * ``arrowHead`` and ``connectorPreview`` objects are skipped — derived
    render artifacts, never semantic content (mirrors
    ``canvas_editor._SKIPPED_CANVAS_JSON_DATA_TYPES``).
  * A genuine free-hand ``path``-type object (Fabric's own ``type == "path"``,
    untagged by ``data`` — the same discriminator
    ``canvas_editor._canvas_json_object_to_element`` uses to recognize a
    freehand pen stroke) has no node_graph equivalent: converting would
    silently drop data, so the WHOLE diagram is refused instead (reported by
    the caller, never partially converted).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from diagram.node_graph import MAX_LABEL_LENGTH, SCHEMA_VERSION

#: Fabric ``data.type`` discriminators that are derived render artifacts,
#: never semantic content — mirrors
#: ``diagram.canvas_editor._SKIPPED_CANVAS_JSON_DATA_TYPES`` (kept identical
#: intentionally: an object kind that must not become its own SVG element
#: must equally not become its own node/edge).
_SKIPPED_DATA_TYPES = frozenset({"arrowHead", "connectorPreview"})

#: ``data.type`` values that map to a node_graph *node* (shape objects).
_NODE_SHAPE_DATA_TYPES = frozenset({"rect", "ellipse", "circle"})

#: node_graph node ``type`` per shape ``data.type`` (see NODE_TYPES in
#: diagram.node_graph — "box" and "ellipse" are both valid enum values).
_NODE_TYPE_FOR_SHAPE = {"rect": "box", "ellipse": "ellipse", "circle": "ellipse"}

#: Fixed edge ``type`` for every converted connector — canvas connectors
#: carry no type discriminator of their own, "flow" is the closest generic
#: fit among node_graph's EDGE_TYPES.
_CONVERTED_EDGE_TYPE = "flow"


@dataclass(frozen=True)
class ConversionResult:
    """Outcome of converting one diagram's ``canvas_json`` to ``node_graph``.

    Attributes:
        ok:      True if a node_graph payload could be built.
        payload: The node_graph payload dict (only set when ``ok`` is True).
        reason:  Human-readable reason it was not convertible (only set when
            ``ok`` is False), e.g. why a free-hand path object caused a
            refusal.
    """

    ok: bool
    payload: Optional[dict] = None
    reason: Optional[str] = None


def _is_genuine_freehand_path(obj: Any) -> bool:
    """True if *obj* is a genuine Fabric freehand pen stroke.

    Mirrors ``canvas_editor._canvas_json_object_to_element``'s own check:
    Fabric's native ``type == "path"`` with no ``data`` tag at all. Every
    semantic shape this editor creates (rect/ellipse/text/label/connector) is
    tagged via ``data.type``; an untagged ``path`` object can only be a
    freehand pen stroke, which has no node_graph equivalent.
    """
    if not isinstance(obj, dict):
        return False
    data = obj.get("data")
    data_type = data.get("type") if isinstance(data, dict) else None
    return data_type is None and obj.get("type") == "path"


def _safe_number(value: Any, default: float = 0.0) -> float:
    """Coerce an untrusted JSON value to a finite number (never raises)."""
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clip_label(text: Any) -> str:
    """Coerce *text* to a string within node_graph's MAX_LABEL_LENGTH cap."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return text[:MAX_LABEL_LENGTH]


def convert_canvas_json_to_node_graph(canvas_json: dict) -> ConversionResult:
    """Convert one diagram's Fabric ``canvas_json`` to a ``node_graph`` v1 payload.

    Args:
        canvas_json: The ``Diagram.canvas_json`` dict of a
            ``canvas_stroke`` diagram's current version (never the lossy
            ``strokes`` payload — see Task 2's F2 finding for why ``strokes``
            drops every non-freehand shape).

    Returns:
        A :class:`ConversionResult`. ``ok=False`` (refusal, not partial
        conversion) when *canvas_json* is missing/malformed or contains a
        genuine free-hand ``path`` object; ``ok=True`` with a ``payload``
        dict otherwise (callers should still run
        :func:`diagram.node_graph.validate_node_graph` on it before
        persisting, as a final structural safety net).
    """
    if not isinstance(canvas_json, dict):
        return ConversionResult(ok=False, reason="canvas_json is missing or not a JSON object.")

    objects = canvas_json.get("objects")
    if not isinstance(objects, list):
        return ConversionResult(ok=False, reason="canvas_json has no 'objects' array.")

    freehand_count = sum(1 for obj in objects if _is_genuine_freehand_path(obj))
    if freehand_count:
        return ConversionResult(
            ok=False,
            reason=(
                f"contains {freehand_count} free-hand path object(s), which have no "
                "node_graph equivalent — refusing to convert (would silently drop data)."
            ),
        )

    # Pass 1: resolve every node (shapes + standalone text) and collect
    # label text + connector objects for pass 2 (both need the full node id
    # set resolved first).
    nodes: dict[str, dict] = {}
    labels_by_target: dict[str, str] = {}
    connectors: list[dict] = []

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        data = obj.get("data")
        data_type = data.get("type") if isinstance(data, dict) else None

        if data_type in _SKIPPED_DATA_TYPES:
            continue

        if data_type == "label":
            label_for = data.get("labelFor") if isinstance(data, dict) else None
            if isinstance(label_for, str) and label_for:
                labels_by_target[label_for] = obj.get("text", "")
            continue

        if data_type in _NODE_SHAPE_DATA_TYPES:
            node_id = data.get("id")
            if not isinstance(node_id, str) or not node_id:
                continue  # untagged/corrupted shape — nothing stable to key on
            scale_x = _safe_number(obj.get("scaleX", 1), 1)
            scale_y = _safe_number(obj.get("scaleY", 1), 1)
            left = _safe_number(obj.get("left", 0))
            top = _safe_number(obj.get("top", 0))

            if data_type == "rect":
                width = _safe_number(obj.get("width", 0)) * scale_x
                height = _safe_number(obj.get("height", 0)) * scale_y
            else:  # ellipse / circle — mirrors canvas_editor's rx/ry read
                width = _safe_number(obj.get("rx", 0)) * scale_x * 2
                height = _safe_number(obj.get("ry", 0)) * scale_y * 2

            node: dict[str, Any] = {
                "id": node_id,
                "type": _NODE_TYPE_FOR_SHAPE[data_type],
                "label": "",  # folded in from labels_by_target below
                "position": {"x": left, "y": top},
            }
            if width > 0 and height > 0:
                node["size"] = {"width": width, "height": height}

            # Forward-compatible passthrough: canvas shapes have no
            # first-class artifact-linking UI yet, but if a caller-supplied
            # canvas_json object already carries a well-formed
            # ``data.artifact_ref`` (e.g. produced by a future canvas
            # artifact-drop feature, or hand-authored for migration), it is
            # copied through so DiagramManager's Task 4 reconciler picks it
            # up on write like any other node_graph artifact_ref.
            artifact_ref = data.get("artifact_ref")
            if isinstance(artifact_ref, dict) and artifact_ref:
                node["artifact_ref"] = artifact_ref

            nodes[node_id] = node
            continue

        if data_type == "text":
            # Standalone textbox (no labelFor companion) -> a note node.
            node_id = data.get("id")
            if not isinstance(node_id, str) or not node_id:
                continue
            left = _safe_number(obj.get("left", 0))
            top = _safe_number(obj.get("top", 0))
            nodes[node_id] = {
                "id": node_id,
                "type": "note",
                "label": _clip_label(obj.get("text", "")),
                "position": {"x": left, "y": top},
            }
            continue

        if data_type == "connector":
            connectors.append(obj)
            continue

        # Untagged Fabric object with no `data` (freehand `path` objects were
        # already refused above, so this is not one of those) or an
        # unrecognized `data.type`: not semantic graph content for any of
        # today's canvas tools — skip defensively rather than fabricate a
        # node from an unknown shape kind.
        continue

    # Fold label text onto its target node now both passes are done. A label
    # whose `labelFor` no longer resolves (anchor shape removed) is dropped —
    # mirrors the frontend's own orphaned-label cleanup on shape delete.
    for target_id, text in labels_by_target.items():
        node = nodes.get(target_id)
        if node is not None:
            node["label"] = _clip_label(text)

    # Pass 2: connectors -> edges. A connector whose anchor shape no longer
    # resolves (dangling fromId/toId) is dropped rather than emitting an
    # edge the node_graph validator would reject as dangling — mirrors the
    # frontend's own orphaned-connector cleanup on shape delete.
    edges: list[dict] = []
    for obj in connectors:
        data = obj.get("data") or {}
        edge_id = data.get("id")
        source = data.get("fromId")
        target = data.get("toId")
        if not isinstance(edge_id, str) or not edge_id:
            continue
        if source not in nodes or target not in nodes:
            continue
        edges.append({
            "id": edge_id,
            "type": _CONVERTED_EDGE_TYPE,
            "source": source,
            "target": target,
        })

    payload = {
        "schema_version": SCHEMA_VERSION,
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    return ConversionResult(ok=True, payload=payload)


__all__ = [
    "ConversionResult",
    "convert_canvas_json_to_node_graph",
]
