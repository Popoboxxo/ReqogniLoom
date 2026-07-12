"""
ARCH-L1-013 DiagramService — Diagram payload validator.

leaf_id: COMP-DS-002_DiagramValidator, COMP-DS-006_CanvasEditor,
         COMP-DS-007_MermaidLiveRenderer
req_id: REQ-L1-027, REQ-L2-DS-002, REQ-L3-DV-001, REQ-L3-DV-002,
        REQ-L1-056, REQ-L2-DS-006, REQ-L1-057, REQ-L2-DS-007

Internal interface:
  IF-DS-INT-001: validate_payload(diagram_type, payload_format, content) -> None
  IF-DS-INT-004: validate_canvas_strokes(stroke_data) -> ValidationResult
  IF-DS-INT-010: validate_mermaid_source(source, diagram_type) -> ValidationResult

Validates the raw payload string/dict of a diagram against type-specific syntax
rules before it is persisted.  Raises DiagramValidationError on any violation.

Supported types  : block, flow, context, canvas, mermaid  (DiagramType — REQ-L2-DS-002)
Supported formats: mermaid, plantuml, json, canvas_stroke

COMP-DS-006 CanvasEditor uses validate_canvas_strokes() for JSON stroke data.
COMP-DS-007 MermaidLiveRenderer uses validate_mermaid_source() for the 5 Mermaid
diagram types (flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram).

Design notes (ADR-DS-01):
  Validation is intentionally decoupled from rendering.  This module is a
  pure function boundary — it never touches the database.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from diagram.models import DiagramType, PayloadFormat


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DiagramValidationError(ValueError):
    """Raised when a diagram payload fails type-specific validation.

    REQ-L3-DV-001: message contains the concrete reason (syntax error, missing
    key, unsupported type …).
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Mermaid diagram-type directive keywords per diagram_type.
# Validation checks that the payload starts with the expected keyword so that
# mis-typed diagrams are caught early without pulling in a full Mermaid parser.
_MERMAID_REQUIRED_PREFIX: dict[str, list[str]] = {
    DiagramType.BLOCK: ["block-beta", "graph", "flowchart"],
    DiagramType.FLOW: ["flowchart", "graph"],
    DiagramType.CONTEXT: ["C4Context", "graph", "flowchart", "block-beta"],
    DiagramType.MERMAID: [
        "flowchart", "graph",
        "sequenceDiagram",
        "classDiagram",
        "stateDiagram",
        "erDiagram",
    ],
}

# Maximum Mermaid source size in bytes (1 MB) — REQ-L2-DS-007
_MAX_MERMAID_SOURCE_SIZE = 1_048_576

# ---------------------------------------------------------------------------
# Canvas stroke validation constants — IF-DS-INT-004, REQ-L2-DS-006
# ---------------------------------------------------------------------------

# Valid element types for canvas stroke data
CANVAS_VALID_ELEMENT_TYPES: frozenset[str] = frozenset({
    "pen", "rect", "circle", "line", "text", "arrow", "connector",
})

# Maximum number of elements in a single canvas (REQ-L2-DS-006: 500 strokes + 100 shapes)
CANVAS_MAX_ELEMENTS: int = 1000

# Maximum number of points in a single pen stroke
CANVAS_MAX_STROKE_POINTS: int = 10_000


# ---------------------------------------------------------------------------
# ValidationResult data class — IF-DS-INT-010
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationResult:
    """Result of a Mermaid source validation (REQ-L2-DS-007).

    Attributes:
        is_valid:    True if the source passed all checks.
        error_msg:   Human-readable error description (empty when valid).
        line_number: 1-based line number where the error was detected (0 if N/A).
        diagram_type: Detected or declared Mermaid diagram type.
    """

    is_valid: bool
    error_msg: str = ""
    line_number: int = 0
    diagram_type: str = ""

# PlantUML diagram-type directive keywords per diagram_type.
_PLANTUML_REQUIRED_START: dict[str, list[str]] = {
    DiagramType.BLOCK: ["@startuml", "@startblock"],
    DiagramType.FLOW: ["@startuml", "@startflow"],
    DiagramType.CONTEXT: ["@startuml", "@startcontext"],
}

# Required top-level JSON keys per diagram_type.
_JSON_REQUIRED_KEYS: dict[str, list[str]] = {
    DiagramType.BLOCK: ["nodes"],
    DiagramType.FLOW: ["nodes", "edges"],
    DiagramType.CONTEXT: ["nodes"],
}


def _validate_mermaid(diagram_type: str, content: str) -> None:
    """Check that a Mermaid source string matches the declared diagram_type.

    REQ-L3-DV-001: returns normally on success; raises DiagramValidationError
    with the concrete reason on failure.
    """
    if not content or not content.strip():
        raise DiagramValidationError("Mermaid payload must not be empty.")

    first_token = content.strip().split()[0].lower()
    allowed_prefixes = [p.lower() for p in _MERMAID_REQUIRED_PREFIX.get(diagram_type, [])]

    if allowed_prefixes and first_token not in allowed_prefixes:
        raise DiagramValidationError(
            f"Mermaid payload for diagram_type='{diagram_type}' must start with one of "
            f"{_MERMAID_REQUIRED_PREFIX[diagram_type]!r}; got '{first_token}'."
        )


def _validate_plantuml(diagram_type: str, content: str) -> None:
    """Check that a PlantUML source string starts with a recognised directive.

    REQ-L3-DV-001: raises DiagramValidationError on syntax violation.
    """
    if not content or not content.strip():
        raise DiagramValidationError("PlantUML payload must not be empty.")

    first_line = content.strip().splitlines()[0].strip().lower()
    allowed = [s.lower() for s in _PLANTUML_REQUIRED_START.get(diagram_type, ["@startuml"])]

    if not any(first_line.startswith(s) for s in allowed):
        raise DiagramValidationError(
            f"PlantUML payload for diagram_type='{diagram_type}' must start with one of "
            f"{_PLANTUML_REQUIRED_START.get(diagram_type, ['@startuml'])!r}; "
            f"got '{content.strip().splitlines()[0]}'."
        )

    if "@enduml" not in content.lower() and "@endblock" not in content.lower() and "@endflow" not in content.lower():
        raise DiagramValidationError(
            "PlantUML payload is missing a closing @end directive."
        )


def _validate_json(diagram_type: str, content: str) -> None:
    """Check that a JSON payload can be parsed and contains required top-level keys.

    REQ-L3-DV-001: raises DiagramValidationError on parse or schema failure.
    """
    if not content or not content.strip():
        raise DiagramValidationError("JSON payload must not be empty.")

    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DiagramValidationError(
            f"JSON payload is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}."
        ) from exc

    if not isinstance(data, dict):
        raise DiagramValidationError("JSON payload must be a JSON object (dict).")

    required_keys = _JSON_REQUIRED_KEYS.get(diagram_type, [])
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise DiagramValidationError(
            f"JSON payload for diagram_type='{diagram_type}' is missing required key(s): {missing!r}."
        )


# ---------------------------------------------------------------------------
# Public interface — IF-DS-INT-001
# ---------------------------------------------------------------------------

class DiagramValidator:
    """COMP-DS-002: Validates diagram payloads against type-specific rules.

    req_id: REQ-L2-DS-002, REQ-L3-DV-001, REQ-L3-DV-002
    leaf_id: COMP-DS-002_DiagramValidator

    Called exclusively by DiagramManager (COMP-DS-001) via IF-DS-INT-001.
    This class has no database dependencies.
    """

    # Supported type values for REQ-L3-DV-002 type-check
    _SUPPORTED_TYPES: frozenset[str] = frozenset(DiagramType.values)
    _SUPPORTED_FORMATS: frozenset[str] = frozenset(PayloadFormat.values)

    def validate_payload(
        self,
        diagram_type: str,
        payload_format: str,
        content: str,
    ) -> None:
        """Validate *content* against type-specific rules.

        IF-DS-INT-001 contract: validate_payload(type, content) -> bool
        (raises DiagramValidationError instead of returning False, so callers
        get a descriptive message without an extra boolean branch).

        Args:
            diagram_type:    One of DiagramType values (block/flow/context).
            payload_format:  One of PayloadFormat values (mermaid/plantuml/json).
            content:         Raw diagram payload string.

        Returns:
            None on success.

        Raises:
            DiagramValidationError: If the payload is invalid or the type is
                not supported (REQ-L3-DV-002).
        """
        # REQ-L3-DV-002: reject unsupported diagram types
        if diagram_type not in self._SUPPORTED_TYPES:
            raise DiagramValidationError(
                f"Unsupported diagram_type='{diagram_type}'. "
                f"Supported: {sorted(self._SUPPORTED_TYPES)!r}."
            )

        # REQ-L3-DV-002: reject unsupported payload formats
        if payload_format not in self._SUPPORTED_FORMATS:
            raise DiagramValidationError(
                f"Unsupported payload_format='{payload_format}'. "
                f"Supported: {sorted(self._SUPPORTED_FORMATS)!r}."
            )

        # REQ-L3-DV-001: route to format-specific validator
        if payload_format == PayloadFormat.MERMAID:
            _validate_mermaid(diagram_type, content)
        elif payload_format == PayloadFormat.PLANTUML:
            _validate_plantuml(diagram_type, content)
        elif payload_format == PayloadFormat.JSON:
            _validate_json(diagram_type, content)
        elif payload_format == PayloadFormat.CANVAS_STROKE:
            # Empty content is valid for canvas — treated as empty canvas
            if not content or not content.strip():
                return
            # Parse JSON content and validate as canvas stroke data
            try:
                stroke_data = json.loads(content) if isinstance(content, str) else content
            except json.JSONDecodeError as exc:
                raise DiagramValidationError(
                    f"Canvas stroke payload is not valid JSON: {exc.msg} at line {exc.lineno}."
                ) from exc
            result = _validate_canvas_strokes(stroke_data)
            if not result.is_valid:
                raise DiagramValidationError(
                    f"Canvas stroke validation failed: {result.error_msg}"
                )

    # ------------------------------------------------------------------
    # IF-DS-INT-010: validate_mermaid_source — COMP-DS-007
    # REQ-L2-DS-007
    # ------------------------------------------------------------------

    def validate_mermaid_source(
        self,
        source: str,
        diagram_type: str = "",
    ) -> ValidationResult:
        """Validate Mermaid source code for the 5 supported Mermaid types.

        IF-DS-INT-010 contract: validate_mermaid_source(source, diagram_type) -> ValidationResult

        Checks:
          1. Source is not empty.
          2. Source size <= 1 MB (REQ-L2-DS-007).
          3. First token matches one of the 5 Mermaid diagram types:
             flowchart/graph, sequenceDiagram, classDiagram, stateDiagram, erDiagram.
          4. If diagram_type is provided, it must match the detected type.

        Args:
            source:       Raw Mermaid source code string.
            diagram_type: Optional declared diagram type for cross-check.

        Returns:
            ValidationResult with is_valid, error_msg, line_number, diagram_type.

        REQ-L2-DS-007, REQ-L1-057
        """
        return _validate_mermaid_source(source, diagram_type)

    # ------------------------------------------------------------------
    # IF-DS-INT-004: validate_canvas_strokes — COMP-DS-006
    # REQ-L2-DS-006
    # ------------------------------------------------------------------

    def validate_canvas_strokes(
        self,
        stroke_data: dict,
    ) -> ValidationResult:
        """Validate canvas stroke data structure and constraints.

        IF-DS-INT-004 contract: validate_canvas_strokes(stroke_data: dict) -> ValidationResult

        Checks:
          1. stroke_data is a dict with a 'strokes' key containing a list.
          2. Each element has a valid 'type' (pen, rect, circle, line, text, arrow, connector).
          3. Total element count <= CANVAS_MAX_ELEMENTS (1000).
          4. Pen strokes have 'points' list with <= CANVAS_MAX_STROKE_POINTS (10000) points.
          5. Each element has required fields for its type.

        Args:
            stroke_data: Canvas stroke data as a dict with 'strokes' key.

        Returns:
            ValidationResult with is_valid, error_msg, line_number (element index),
            diagram_type='canvas'.

        REQ-L2-DS-006, REQ-L1-056
        """
        return _validate_canvas_strokes(stroke_data)


# ---------------------------------------------------------------------------
# Mermaid source validation — IF-DS-INT-010
# ---------------------------------------------------------------------------

# Mapping of Mermaid start keywords to canonical type names
_MERMAID_TYPE_KEYWORDS: dict[str, str] = {
    "flowchart": "flowchart",
    "graph": "flowchart",
    "sequencediagram": "sequenceDiagram",
    "classdiagram": "classDiagram",
    "statediagram": "stateDiagram",
    "erdiagram": "erDiagram",
}


def _validate_mermaid_source(source: str, diagram_type: str = "") -> ValidationResult:
    """Validate Mermaid source code (internal implementation).

    REQ-L2-DS-007: Validates the 5 Mermaid diagram types with line-number
    reporting for error locations.
    """
    # Check 1: Empty source
    if not source or not source.strip():
        return ValidationResult(
            is_valid=False,
            error_msg="Mermaid source must not be empty.",
            line_number=0,
            diagram_type=diagram_type,
        )

    # Check 2: Size limit (1 MB)
    source_bytes = source.encode("utf-8")
    if len(source_bytes) > _MAX_MERMAID_SOURCE_SIZE:
        return ValidationResult(
            is_valid=False,
            error_msg=f"Mermaid source exceeds maximum size of 1 MB ({len(source_bytes)} bytes).",
            line_number=0,
            diagram_type=diagram_type,
        )

    # Check 3: First token must be a valid Mermaid diagram type keyword
    lines = source.strip().splitlines()
    first_line = lines[0].strip() if lines else ""
    first_token = first_line.split()[0] if first_line else ""
    first_token_lower = first_token.lower()

    if first_token_lower not in _MERMAID_TYPE_KEYWORDS:
        return ValidationResult(
            is_valid=False,
            error_msg=(
                f"Mermaid source must start with a valid diagram type keyword "
                f"(flowchart, graph, sequenceDiagram, classDiagram, stateDiagram, erDiagram); "
                f"got '{first_token}'."
            ),
            line_number=1,
            diagram_type=diagram_type,
        )

    detected_type = _MERMAID_TYPE_KEYWORDS[first_token_lower]

    # Check 4: Cross-check with declared diagram_type if provided
    if diagram_type and diagram_type.lower() != detected_type.lower():
        # Allow "flowchart" and "graph" as aliases
        if not (
            diagram_type.lower() in ("flowchart", "graph")
            and detected_type == "flowchart"
        ):
            return ValidationResult(
                is_valid=False,
                error_msg=(
                    f"Declared diagram_type='{diagram_type}' does not match "
                    f"detected type '{detected_type}' from source."
                ),
                line_number=1,
                diagram_type=diagram_type,
            )

    return ValidationResult(
        is_valid=True,
        error_msg="",
        line_number=0,
        diagram_type=detected_type,
    )


# ---------------------------------------------------------------------------
# Canvas stroke validation — IF-DS-INT-004, REQ-L2-DS-006
# ---------------------------------------------------------------------------

# Required fields per element type
_CANVAS_ELEMENT_REQUIRED_FIELDS: dict[str, list[str]] = {
    "pen": ["points"],
    "rect": ["x", "y", "width", "height"],
    "circle": ["cx", "cy", "r"],
    "line": ["x1", "y1", "x2", "y2"],
    "text": ["x", "y", "content"],
    "arrow": ["x1", "y1", "x2", "y2"],
    "connector": ["source_id", "target_id"],
}


def _validate_canvas_strokes(stroke_data: dict) -> ValidationResult:
    """Validate canvas stroke data (internal implementation).

    REQ-L2-DS-006: Validates JSON stroke data structure, element types,
    element count limits, and per-element required fields.
    """
    # Check 1: stroke_data must be a dict
    if not isinstance(stroke_data, dict):
        return ValidationResult(
            is_valid=False,
            error_msg="Canvas stroke data must be a JSON object (dict).",
            line_number=0,
            diagram_type="canvas",
        )

    # Check 2: 'strokes' key must exist and be a list
    strokes = stroke_data.get("strokes")
    if strokes is None:
        return ValidationResult(
            is_valid=False,
            error_msg="Canvas stroke data must contain a 'strokes' key.",
            line_number=0,
            diagram_type="canvas",
        )

    if not isinstance(strokes, list):
        return ValidationResult(
            is_valid=False,
            error_msg="'strokes' must be a JSON array.",
            line_number=0,
            diagram_type="canvas",
        )

    # Check 3: Element count limit
    if len(strokes) > CANVAS_MAX_ELEMENTS:
        return ValidationResult(
            is_valid=False,
            error_msg=(
                f"Canvas contains {len(strokes)} elements, "
                f"exceeding maximum of {CANVAS_MAX_ELEMENTS}."
            ),
            line_number=0,
            diagram_type="canvas",
        )

    # Check 4: Validate each element
    for idx, element in enumerate(strokes):
        if not isinstance(element, dict):
            return ValidationResult(
                is_valid=False,
                error_msg=f"Element at index {idx} must be a JSON object (dict).",
                line_number=idx,
                diagram_type="canvas",
            )

        # Check 4a: Element must have a 'type' field
        elem_type = element.get("type")
        if not elem_type:
            return ValidationResult(
                is_valid=False,
                error_msg=f"Element at index {idx} is missing required 'type' field.",
                line_number=idx,
                diagram_type="canvas",
            )

        # Check 4b: Element type must be valid
        if elem_type not in CANVAS_VALID_ELEMENT_TYPES:
            return ValidationResult(
                is_valid=False,
                error_msg=(
                    f"Element at index {idx} has invalid type '{elem_type}'. "
                    f"Valid types: {sorted(CANVAS_VALID_ELEMENT_TYPES)!r}."
                ),
                line_number=idx,
                diagram_type="canvas",
            )

        # Check 4c: Required fields for the element type
        required_fields = _CANVAS_ELEMENT_REQUIRED_FIELDS.get(elem_type, [])
        missing_fields = [f for f in required_fields if f not in element]
        if missing_fields:
            return ValidationResult(
                is_valid=False,
                error_msg=(
                    f"Element at index {idx} (type='{elem_type}') is missing "
                    f"required field(s): {missing_fields!r}."
                ),
                line_number=idx,
                diagram_type="canvas",
            )

        # Check 4d: Pen stroke point count limit
        if elem_type == "pen":
            points = element.get("points", [])
            if isinstance(points, list) and len(points) > CANVAS_MAX_STROKE_POINTS:
                return ValidationResult(
                    is_valid=False,
                    error_msg=(
                        f"Pen stroke at index {idx} has {len(points)} points, "
                        f"exceeding maximum of {CANVAS_MAX_STROKE_POINTS}."
                    ),
                    line_number=idx,
                    diagram_type="canvas",
                )

    return ValidationResult(
        is_valid=True,
        error_msg="",
        line_number=0,
        diagram_type="canvas",
    )


__all__ = [
    "DiagramValidator",
    "DiagramValidationError",
    "ValidationResult",
]
