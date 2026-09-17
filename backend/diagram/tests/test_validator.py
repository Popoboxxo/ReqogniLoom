"""
COMP-DS-002 DiagramValidator — Unit tests.

Covers:
  REQ-L2-DS-002: Payload validation per type (min. 3 types)
  REQ-L3-DV-001: Type-specific syntax validation with error detail
  REQ-L3-DV-002: Rejection of unsupported diagram types
  REQ-L2-DS-007: Mermaid source validation for 5 types

IF-DS-INT-001: validate_payload(diagram_type, payload_format, content)
IF-DS-INT-010: validate_mermaid_source(source, diagram_type) -> ValidationResult
"""
from __future__ import annotations

import pytest

from diagram.validator import DiagramValidator, DiagramValidationError, ValidationResult


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

    def test_valid_mermaid_diagram_type(self, validator: DiagramValidator) -> None:
        """CR-05 regression: diagram_type='mermaid' with payload_format='mermaid'.

        Must validate cleanly regardless of the caller's rigor preset — this
        validator has no preset awareness at all (see docs/
        ANALYSE_SYSENG20_TESTBERICHT_FIXLISTE.md CR-05).
        """
        validator.validate_payload("mermaid", "mermaid", "flowchart TD\n  A --> B")


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

    def test_mermaid_type_non_json_content_raises_clean_error(
        self, validator: DiagramValidator
    ) -> None:
        """CR-05 regression: diagram_type='mermaid' with the default
        payload_format='json' and raw Mermaid text as content (i.e. a caller
        that omits payload_format) must raise DiagramValidationError — not an
        unhandled json.JSONDecodeError bubbling up as HTTP 500.

        This is the underlying cause behind CR-05's "500 JSON-Parse-Error"
        symptom (see docs/ANALYSE_SYSENG20_TESTBERICHT_FIXLISTE.md). It is
        identical for every rigor preset because DiagramValidator never reads
        preset/tier information — confirmed by manual reproduction against
        both 'standard' and 'extended' workspaces, which now both return a
        clean 400 (fixed together with CR-02, commit dcce2ad6).
        """
        with pytest.raises(DiagramValidationError, match="not valid JSON"):
            validator.validate_payload(
                "mermaid", "json", "flowchart TD\n  A --> B"
            )


# ---------------------------------------------------------------------------
# REQ-L2-DS-007: Mermaid source validation for 5 types
# IF-DS-INT-010: validate_mermaid_source
# ---------------------------------------------------------------------------

class TestMermaidSourceValidation:
    """REQ-L2-DS-007: validate_mermaid_source for 5 Mermaid diagram types."""

    def test_valid_flowchart(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("flowchart TD\n  A --> B")
        assert result.is_valid
        assert result.diagram_type == "flowchart"

    def test_valid_graph_alias(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("graph LR\n  A --> B")
        assert result.is_valid
        assert result.diagram_type == "flowchart"

    def test_valid_sequence_diagram(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("sequenceDiagram\n  Alice->>Bob: Hello")
        assert result.is_valid
        assert result.diagram_type == "sequenceDiagram"

    def test_valid_class_diagram(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("classDiagram\n  class Animal")
        assert result.is_valid
        assert result.diagram_type == "classDiagram"

    def test_valid_state_diagram(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("stateDiagram\n  [*] --> Active")
        assert result.is_valid
        assert result.diagram_type == "stateDiagram"

    def test_valid_er_diagram(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("erDiagram\n  CUSTOMER ||--o{ ORDER")
        assert result.is_valid
        assert result.diagram_type == "erDiagram"

    def test_empty_source_invalid(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("")
        assert not result.is_valid
        assert "empty" in result.error_msg.lower()

    def test_whitespace_only_invalid(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("   \n  ")
        assert not result.is_valid
        assert "empty" in result.error_msg.lower()

    def test_invalid_keyword(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source("invalid\n  A --> B")
        assert not result.is_valid
        assert result.line_number == 1
        assert "must start with" in result.error_msg

    def test_oversized_source(self, validator: DiagramValidator) -> None:
        # Create a source > 1 MB
        large_source = "flowchart TD\n" + "A --> B\n" * 200000
        result = validator.validate_mermaid_source(large_source)
        assert not result.is_valid
        assert "size" in result.error_msg.lower()

    def test_type_mismatch(self, validator: DiagramValidator) -> None:
        # Declare flowchart but source is sequenceDiagram
        result = validator.validate_mermaid_source(
            "sequenceDiagram\n  A->>B",
            diagram_type="flowchart",
        )
        assert not result.is_valid
        assert "does not match" in result.error_msg

    def test_type_match_succeeds(self, validator: DiagramValidator) -> None:
        result = validator.validate_mermaid_source(
            "flowchart TD\n  A --> B",
            diagram_type="flowchart",
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# GH-353 (Task 1): validate_payload() routes payload_format=node_graph to
# diagram.node_graph.validate_node_graph — deep invariant coverage lives in
# test_node_graph.py; this class only exercises the wiring itself.
# ---------------------------------------------------------------------------

class TestNodeGraphWiring:
    """DiagramValidator.validate_payload() — node_graph branch."""

    _VALID_CONTENT = (
        '{"schema_version": 1, "nodes": [{"id": "n-1", "type": "box", '
        '"label": "A", "position": {"x": 0, "y": 0}}], "edges": []}'
    )

    def test_valid_node_graph_passes(self, validator: DiagramValidator) -> None:
        # Any diagram_type is accepted for node_graph (mirrors canvas_stroke,
        # which is likewise not diagram_type-restricted).
        validator.validate_payload("block", "node_graph", self._VALID_CONTENT)

    def test_empty_content_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="must not be empty"):
            validator.validate_payload("block", "node_graph", "")

    def test_malformed_json_raises(self, validator: DiagramValidator) -> None:
        with pytest.raises(DiagramValidationError, match="not valid JSON"):
            validator.validate_payload("block", "node_graph", "{not json")

    def test_invariant_violation_raises(self, validator: DiagramValidator) -> None:
        content = (
            '{"schema_version": 1, "nodes": [{"id": "n-1", "type": "box", '
            '"label": "A", "position": {"x": 0, "y": 0}}], '
            '"edges": [{"id": "e-1", "source": "n-1", "target": "does-not-exist", '
            '"type": "flow"}]}'
        )
        with pytest.raises(DiagramValidationError, match="Node graph validation failed"):
            validator.validate_payload("block", "node_graph", content)
