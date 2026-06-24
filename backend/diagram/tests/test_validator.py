"""
COMP-DS-002 DiagramValidator — Unit tests.

Covers:
  REQ-L2-DS-002: Payload validation per type (min. 3 types)
  REQ-L3-DV-001: Type-specific syntax validation with error detail
  REQ-L3-DV-002: Rejection of unsupported diagram types

IF-DS-INT-001: validate_payload(diagram_type, payload_format, content)
"""
from __future__ import annotations

import pytest

from diagram.validator import DiagramValidator, DiagramValidationError


@pytest.fixture
def validator() -> DiagramValidator:
    return DiagramValidator()


# ---------------------------------------------------------------------------
# REQ-L3-DV-002: Unsupported type rejection
# ---------------------------------------------------------------------------

class TestUnsupportedType:
    """REQ-L3-DV-002: Unknown types are rejected."""

    def test_unknown_diagram_type_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="Unsupported diagram_type"):
            validator.validate_payload(
                diagram_type="unknown_type",
                payload_format="mermaid",
                content="flowchart TD\n  A-->B",
            )

    def test_unknown_payload_format_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="Unsupported payload_format"):
            validator.validate_payload(
                diagram_type="block",
                payload_format="xml",
                content="<diagram/>",
            )


# ---------------------------------------------------------------------------
# REQ-L3-DV-001: Mermaid validation for all 3 diagram types
# ---------------------------------------------------------------------------

class TestMermaidValidation:
    """REQ-L3-DV-001, REQ-L2-DS-002: Mermaid payloads for block/flow/context."""

    def test_valid_mermaid_block(self, validator: DiagramValidator) -> None:
        # block-beta keyword accepted for block diagrams
        validator.validate_payload("block", "mermaid", "block-beta\n  A[Block]")

    def test_valid_mermaid_flow(self, validator: DiagramValidator) -> None:
        validator.validate_payload("flow", "mermaid", "flowchart TD\n  A --> B")

    def test_valid_mermaid_context(self, validator: DiagramValidator) -> None:
        validator.validate_payload("context", "mermaid", "flowchart LR\n  User --> Sys")

    def test_invalid_mermaid_wrong_keyword(self, validator: DiagramValidator) -> None:
        """Flow diagram must start with flowchart/graph, not block-beta."""
        with pytest.raises(DiagramValidationError, match="must start with"):
            validator.validate_payload("flow", "mermaid", "block-beta\n  A[X]")

    def test_empty_mermaid_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="must not be empty"):
            validator.validate_payload("block", "mermaid", "")

    def test_whitespace_only_mermaid_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="must not be empty"):
            validator.validate_payload("flow", "mermaid", "   ")


# ---------------------------------------------------------------------------
# REQ-L3-DV-001: PlantUML validation for all 3 diagram types
# ---------------------------------------------------------------------------

class TestPlantUMLValidation:
    """REQ-L3-DV-001, REQ-L2-DS-002: PlantUML payloads for block/flow/context."""

    def test_valid_plantuml_block(self, validator: DiagramValidator) -> None:
        validator.validate_payload("block", "plantuml", "@startuml\nrectangle A\n@enduml")

    def test_valid_plantuml_flow(self, validator: DiagramValidator) -> None:
        validator.validate_payload("flow", "plantuml", "@startuml\nA --> B\n@enduml")

    def test_valid_plantuml_context(self, validator: DiagramValidator) -> None:
        validator.validate_payload("context", "plantuml", "@startuml\nrectangle S\n@enduml")

    def test_missing_end_directive_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="closing @end"):
            validator.validate_payload("block", "plantuml", "@startuml\nrectangle A")

    def test_wrong_start_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="must start with"):
            validator.validate_payload("block", "plantuml", "rectangle A\n@enduml")

    def test_empty_plantuml_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="must not be empty"):
            validator.validate_payload("flow", "plantuml", "")


# ---------------------------------------------------------------------------
# REQ-L3-DV-001: JSON validation for all 3 diagram types
# ---------------------------------------------------------------------------

class TestJSONValidation:
    """REQ-L3-DV-001, REQ-L2-DS-002: JSON payloads for block/flow/context."""

    def test_valid_json_block(self, validator: DiagramValidator) -> None:
        validator.validate_payload("block", "json", '{"nodes": []}')

    def test_valid_json_flow(self, validator: DiagramValidator) -> None:
        validator.validate_payload("flow", "json", '{"nodes": [], "edges": []}')

    def test_valid_json_context(self, validator: DiagramValidator) -> None:
        validator.validate_payload("context", "json", '{"nodes": [{"id": "S"}]}')

    def test_invalid_json_syntax_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="not valid JSON"):
            validator.validate_payload("block", "json", "{invalid}")

    def test_missing_required_key_raises(self, validator: DiagramValidator) -> None:
        """Flow diagram JSON must have 'edges' key."""
        with pytest.raises(DiagramValidationError, match="missing required key"):
            validator.validate_payload("flow", "json", '{"nodes": []}')

    def test_json_must_be_object_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="must be a JSON object"):
            validator.validate_payload("block", "json", '"a string"')

    def test_empty_json_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="must not be empty"):
            validator.validate_payload("context", "json", "")
