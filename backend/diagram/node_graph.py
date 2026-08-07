"""
ARCH-L1-013 DiagramService — Node Graph payload format (payload_format=node_graph).

GH-353 (Task 1): a strictly-typed node/edge diagram format, independent of
the existing freehand ``canvas_stroke`` format. Where ``canvas_stroke`` is
pixel-level pen/shape data, ``node_graph`` is a structured graph of typed
``Node``/``Edge`` records suitable for a React-Flow-style editor and for
linking directly into the artifact model via ``Node.artifact_ref``.

Envelope::

    {
      "schema_version": 1,
      "nodes": [ ... ],
      "edges": [ ... ],
      "viewport": {"x": 0, "y": 0, "zoom": 1}
    }

Design notes (mirrors ADR-DS-01 for the rest of ``diagram/``):
  This module is a PURE function boundary — it never touches the database,
  never imports Django, and never imports ``rest_api`` or any Ext-layer
  module (dependency direction is always ``rest_api`` -> ``diagram``, never
  the reverse). Its only intra-app dependency is :mod:`diagram.validator`,
  reused for the shared, already-frozen ``ValidationResult`` return type
  (no new error-surfacing plumbing, per the Task 1 brief).
"""
from __future__ import annotations

import json
import math
import re
import uuid
from typing import Any

from diagram.validator import ValidationResult

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

#: The only accepted ``schema_version`` value for this format's v1 contract.
SCHEMA_VERSION = 1

NODE_TYPES: frozenset[str] = frozenset({
    "box", "rounded", "ellipse", "diamond", "note", "group",
})

EDGE_TYPES: frozenset[str] = frozenset({
    "flow", "association", "dependency", "containment",
})

STYLE_ACCENTS: frozenset[str] = frozenset({
    "default", "primary", "success", "warning", "danger", "muted",
})

EDGE_LINE_STYLES: frozenset[str] = frozenset({"solid", "dashed"})

HANDLE_POSITIONS: frozenset[str] = frozenset({"top", "right", "bottom", "left"})

#: Known artifact entity types referenceable from a node's ``artifact_ref``.
#: Mirrors the artifact type names used elsewhere in the codebase (see e.g.
#: ``traceability.types.SE_CORE_ARTIFACT_TYPES`` for the SE-core subset)
#: plus the remaining domain artifact kinds. Existence of the referenced
#: entity is intentionally NOT verified here — that happens in Task 3's
#: reconciler, at write time, inside the transaction.
KNOWN_ARTIFACT_ENTITY_TYPES: frozenset[str] = frozenset({
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
})

#: Shared id charset for both node and edge ids.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Caps (mirror CANVAS_MAX_ELEMENTS / _MAX_MERMAID_SOURCE_SIZE conventions
# already established in diagram/validator.py).
MAX_NODES: int = 500
MAX_EDGES: int = 1000
MAX_LABEL_LENGTH: int = 500
MAX_ID_LENGTH: int = 64
MAX_PAYLOAD_BYTES: int = 1_048_576

#: The diagram_type value ValidationResult is stamped with for this format.
_RESULT_DIAGRAM_TYPE = "node_graph"


# ---------------------------------------------------------------------------
# Small internal helpers
# ---------------------------------------------------------------------------

def _is_finite_number(value: Any) -> bool:
    """True if *value* is an int/float (not bool) and finite."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _invalid(error_msg: str, line_number: int = 0) -> ValidationResult:
    """Build a failing ValidationResult for this format."""
    return ValidationResult(
        is_valid=False,
        error_msg=error_msg,
        line_number=line_number,
        diagram_type=_RESULT_DIAGRAM_TYPE,
    )


def _valid() -> ValidationResult:
    """Build a passing ValidationResult for this format."""
    return ValidationResult(
        is_valid=True,
        error_msg="",
        line_number=0,
        diagram_type=_RESULT_DIAGRAM_TYPE,
    )


def _is_valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_PATTERN.match(value))


def _is_valid_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


# ---------------------------------------------------------------------------
# Node / edge field validation
# ---------------------------------------------------------------------------

def _validate_style(style: Any, allowed_key: str, allowed_values: frozenset[str]) -> str | None:
    """Validate a ``{allowed_key: <enum>}`` style object.

    Returns an error message, or ``None`` if valid.
    """
    if not isinstance(style, dict):
        return "'style' must be a JSON object."
    extra_keys = [k for k in style if k != allowed_key]
    if extra_keys:
        return f"'style' must only contain '{allowed_key}'; got extra key(s): {sorted(extra_keys)!r}."
    if allowed_key in style and style[allowed_key] not in allowed_values:
        return (
            f"'style.{allowed_key}' has invalid value {style[allowed_key]!r}; "
            f"expected one of {sorted(allowed_values)!r}."
        )
    return None


def _validate_artifact_ref(artifact_ref: Any) -> str | None:
    """Validate a node's ``artifact_ref`` field. Returns an error message or None."""
    if not isinstance(artifact_ref, dict):
        return "'artifact_ref' must be a JSON object."
    entity_type = artifact_ref.get("entity_type")
    ref_id = artifact_ref.get("id")
    if not entity_type or not isinstance(entity_type, str):
        return "'artifact_ref.entity_type' is required and must be a string."
    if entity_type not in KNOWN_ARTIFACT_ENTITY_TYPES:
        return (
            f"'artifact_ref.entity_type' has unknown value '{entity_type}'; "
            f"expected one of {sorted(KNOWN_ARTIFACT_ENTITY_TYPES)!r}."
        )
    if not _is_valid_uuid(ref_id):
        return f"'artifact_ref.id' must be a UUID string; got {ref_id!r}."
    return None


def _validate_node(node: Any, idx: int) -> tuple[str | None, str | None, bool]:
    """Validate a single node.

    Returns (error_msg, node_id, is_group). ``node_id``/``is_group`` are
    best-effort (populated even on some failures) so the caller can still
    build the id index for cross-reference checks where possible.
    """
    if not isinstance(node, dict):
        return f"Node at index {idx} must be a JSON object (dict).", None, False

    node_id = node.get("id")
    if not _is_valid_id(node_id):
        return (
            f"Node at index {idx} has invalid or missing 'id' "
            f"(must match ^[A-Za-z0-9_-]{{1,64}}$); got {node_id!r}.",
            node_id if isinstance(node_id, str) else None,
            False,
        )

    node_type = node.get("type")
    if node_type not in NODE_TYPES:
        return (
            f"Node '{node_id}' at index {idx} has invalid 'type' {node_type!r}; "
            f"expected one of {sorted(NODE_TYPES)!r}.",
            node_id,
            False,
        )
    is_group = node_type == "group"

    label = node.get("label")
    if not isinstance(label, str):
        return f"Node '{node_id}' at index {idx} is missing required string 'label'.", node_id, is_group
    if len(label) > MAX_LABEL_LENGTH:
        return (
            f"Node '{node_id}' at index {idx} has 'label' longer than "
            f"{MAX_LABEL_LENGTH} characters.",
            node_id,
            is_group,
        )

    position = node.get("position")
    if not isinstance(position, dict) or not _is_finite_number(position.get("x")) or not _is_finite_number(
        position.get("y")
    ):
        return (
            f"Node '{node_id}' at index {idx} has invalid or missing "
            f"'position' (must be {{x, y}} finite numbers).",
            node_id,
            is_group,
        )

    if "size" in node and node["size"] is not None:
        size = node["size"]
        if (
            not isinstance(size, dict)
            or not _is_finite_number(size.get("width"))
            or not _is_finite_number(size.get("height"))
            or size.get("width") <= 0
            or size.get("height") <= 0
        ):
            return (
                f"Node '{node_id}' at index {idx} has invalid 'size' "
                f"(must be {{width, height}} finite numbers > 0).",
                node_id,
                is_group,
            )

    if "style" in node and node["style"] is not None:
        style_err = _validate_style(node["style"], "accent", STYLE_ACCENTS)
        if style_err:
            return f"Node '{node_id}' at index {idx}: {style_err}", node_id, is_group

    if "artifact_ref" in node and node["artifact_ref"] is not None:
        ref_err = _validate_artifact_ref(node["artifact_ref"])
        if ref_err:
            return f"Node '{node_id}' at index {idx}: {ref_err}", node_id, is_group

    parent_id = node.get("parent_id")
    if parent_id is not None and not _is_valid_id(parent_id):
        return (
            f"Node '{node_id}' at index {idx} has invalid 'parent_id' {parent_id!r}.",
            node_id,
            is_group,
        )

    return None, node_id, is_group


def _validate_edge(edge: Any, idx: int, node_ids: set[str]) -> tuple[str | None, str | None]:
    """Validate a single edge. Returns (error_msg, edge_id)."""
    if not isinstance(edge, dict):
        return f"Edge at index {idx} must be a JSON object (dict).", None

    edge_id = edge.get("id")
    if not _is_valid_id(edge_id):
        return (
            f"Edge at index {idx} has invalid or missing 'id' "
            f"(must match ^[A-Za-z0-9_-]{{1,64}}$); got {edge_id!r}.",
            edge_id if isinstance(edge_id, str) else None,
        )

    source = edge.get("source")
    target = edge.get("target")
    if source not in node_ids:
        return f"Edge '{edge_id}' at index {idx} has dangling 'source' node id {source!r}.", edge_id
    if target not in node_ids:
        return f"Edge '{edge_id}' at index {idx} has dangling 'target' node id {target!r}.", edge_id

    edge_type = edge.get("type")
    if edge_type not in EDGE_TYPES:
        return (
            f"Edge '{edge_id}' at index {idx} has invalid 'type' {edge_type!r}; "
            f"expected one of {sorted(EDGE_TYPES)!r}.",
            edge_id,
        )

    if "label" in edge and edge["label"] is not None:
        label = edge["label"]
        if not isinstance(label, str):
            return f"Edge '{edge_id}' at index {idx} has non-string 'label'.", edge_id
        if len(label) > MAX_LABEL_LENGTH:
            return (
                f"Edge '{edge_id}' at index {idx} has 'label' longer than "
                f"{MAX_LABEL_LENGTH} characters.",
                edge_id,
            )

    for handle_field in ("source_handle", "target_handle"):
        if handle_field in edge and edge[handle_field] is not None:
            if edge[handle_field] not in HANDLE_POSITIONS:
                return (
                    f"Edge '{edge_id}' at index {idx} has invalid "
                    f"'{handle_field}' {edge[handle_field]!r}; expected one of "
                    f"{sorted(HANDLE_POSITIONS)!r} or null.",
                    edge_id,
                )

    if "style" in edge and edge["style"] is not None:
        style_err = _validate_style(edge["style"], "line", EDGE_LINE_STYLES)
        if style_err:
            return f"Edge '{edge_id}' at index {idx}: {style_err}", edge_id

    return None, edge_id


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def validate_node_graph(data: dict) -> ValidationResult:
    """Validate a ``node_graph`` payload dict against the v1 schema.

    Checks (per the Task 1 brief):
      1. ``schema_version`` is present and equals 1.
      2. ``nodes``/``edges`` are lists within their caps (500 / 1000).
      3. Every node/edge id matches the shared charset and is unique within
         its own collection; labels stay within the length cap.
      4. Every ``edge.source``/``edge.target`` names an existing node id.
      5. Every ``node.parent_id`` names a node whose ``type == "group"``.
      6. ``artifact_ref.entity_type`` (when present) is a known artifact
         type and ``artifact_ref.id`` parses as a UUID.
      7. The total serialized payload stays within the 1 MB cap.

    Args:
        data: The parsed JSON payload (already ``json.loads``-ed by the
            caller — this function never touches the database or the raw
            request).

    Returns:
        ValidationResult (reused from :mod:`diagram.validator`): ``is_valid``,
        ``error_msg``, ``line_number`` (node/edge index when applicable),
        ``diagram_type='node_graph'``.
    """
    if not isinstance(data, dict):
        return _invalid("Node graph payload must be a JSON object (dict).")

    # Cap 7: total serialized payload size.
    try:
        encoded_size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        return _invalid(f"Node graph payload is not JSON-serializable: {exc}.")
    if encoded_size > MAX_PAYLOAD_BYTES:
        return _invalid(
            f"Node graph payload is {encoded_size} bytes, exceeding the maximum "
            f"of {MAX_PAYLOAD_BYTES} bytes (1 MB)."
        )

    # Check 1: schema_version.
    if data.get("schema_version") != SCHEMA_VERSION:
        return _invalid(
            f"'schema_version' must equal {SCHEMA_VERSION}; got {data.get('schema_version')!r}."
        )

    # Check 2: nodes/edges presence + type + caps.
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return _invalid("'nodes' is required and must be a JSON array.")
    if len(nodes) > MAX_NODES:
        return _invalid(f"Node graph contains {len(nodes)} nodes, exceeding maximum of {MAX_NODES}.")

    edges = data.get("edges")
    if not isinstance(edges, list):
        return _invalid("'edges' is required and must be a JSON array.")
    if len(edges) > MAX_EDGES:
        return _invalid(f"Node graph contains {len(edges)} edges, exceeding maximum of {MAX_EDGES}.")

    # Check: optional viewport.
    viewport = data.get("viewport")
    if viewport is not None:
        if not isinstance(viewport, dict):
            return _invalid("'viewport' must be a JSON object.")
        for key in ("x", "y", "zoom"):
            if key in viewport and not _is_finite_number(viewport[key]):
                return _invalid(f"'viewport.{key}' must be a finite number.")

    # Check 3-6 (nodes): validate each node, collect ids + group membership.
    node_ids: set[str] = set()
    group_ids: set[str] = set()
    parent_refs: list[tuple[str, str, int]] = []  # (node_id, parent_id, idx)

    for idx, node in enumerate(nodes):
        error_msg, node_id, is_group = _validate_node(node, idx)
        if error_msg:
            return _invalid(error_msg, line_number=idx)
        if node_id in node_ids:
            return _invalid(f"Duplicate node id '{node_id}' at index {idx}.", line_number=idx)
        node_ids.add(node_id)
        if is_group:
            group_ids.add(node_id)
        parent_id = node.get("parent_id")
        if parent_id is not None:
            parent_refs.append((node_id, parent_id, idx))

    # Check 5: parent_id must reference an existing group node.
    for node_id, parent_id, idx in parent_refs:
        if parent_id not in node_ids:
            return _invalid(
                f"Node '{node_id}' at index {idx} has 'parent_id' referencing "
                f"unknown node id '{parent_id}'.",
                line_number=idx,
            )
        if parent_id not in group_ids:
            return _invalid(
                f"Node '{node_id}' at index {idx} has 'parent_id' referencing "
                f"'{parent_id}', which is not a group-type node.",
                line_number=idx,
            )

    # Check 3-4 (edges): validate each edge, collect/uniqueness-check ids.
    edge_ids: set[str] = set()
    for idx, edge in enumerate(edges):
        error_msg, edge_id = _validate_edge(edge, idx, node_ids)
        if error_msg:
            return _invalid(error_msg, line_number=idx)
        if edge_id in edge_ids:
            return _invalid(f"Duplicate edge id '{edge_id}' at index {idx}.", line_number=idx)
        edge_ids.add(edge_id)

    return _valid()


def extract_artifact_refs(payload: dict) -> list[tuple[str, dict]]:
    """Return ``(node_id, artifact_ref)`` pairs for every node with a populated ref.

    Shared walk used by Task 3's reconciler (write-time artifact-link sync)
    and Task 7's canvas->node_graph conversion command — neither should
    duplicate this traversal.

    Args:
        payload: A ``node_graph`` payload dict (assumed structurally valid;
            this function does not itself validate — call
            :func:`validate_node_graph` first).

    Returns:
        A list of ``(node_id, artifact_ref)`` tuples, in node order. Nodes
        without an ``id`` or without a populated ``artifact_ref`` dict are
        skipped.
    """
    refs: list[tuple[str, dict]] = []
    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(nodes, list):
        return refs
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        artifact_ref = node.get("artifact_ref")
        if isinstance(node_id, str) and isinstance(artifact_ref, dict) and artifact_ref:
            refs.append((node_id, artifact_ref))
    return refs


__all__ = [
    "SCHEMA_VERSION",
    "NODE_TYPES",
    "EDGE_TYPES",
    "STYLE_ACCENTS",
    "EDGE_LINE_STYLES",
    "HANDLE_POSITIONS",
    "KNOWN_ARTIFACT_ENTITY_TYPES",
    "MAX_NODES",
    "MAX_EDGES",
    "MAX_LABEL_LENGTH",
    "MAX_ID_LENGTH",
    "MAX_PAYLOAD_BYTES",
    "validate_node_graph",
    "extract_artifact_refs",
]
