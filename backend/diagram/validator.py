"""
ARCH-L1-013 DiagramService — Diagram payload validator.

leaf_id: COMP-DS-002_DiagramValidator
req_id: REQ-L1-027, REQ-L2-DS-002, REQ-L3-DV-001, REQ-L3-DV-002

Internal interface:
  IF-DS-INT-001: validate_payload(diagram_type, payload_format, content) -> None

Validates the raw payload string/dict of a diagram against type-specific syntax
rules before it is persisted.  Raises DiagramValidationError on any violation.

Supported types  : block, flow, context  (DiagramType — REQ-L2-DS-002)
Supported formats: mermaid, plantuml, json

Design notes (ADR-DS-01):
  Validation is intentionally decoupled from rendering.  This module is a
  pure function boundary — it never touches the database.
"""
from __future__ import annotations

import json
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
}

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


__all__ = [
    "DiagramValidator",
    "DiagramValidationError",
]
