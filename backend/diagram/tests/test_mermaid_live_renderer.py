"""
COMP-DS-007 MermaidLiveRenderer — Unit tests.

Covers:
  REQ-L1-057: Mermaid-Code-Editor mit Live-Preview
  REQ-L2-DS-007: 5 Mermaid-Typen, Fallback, Performance

Tests:
  - Source-Update-Persistenz (via DiagramManager Mock)
  - 5 Mermaid-Typen validieren
  - Invalide Mermaid-Syntax ablehnen (mit Zeilennummer)
  - Render-Hints korrekt (via DiagramRenderer Mock)
  - Fallback bei Renderer-Fehler

IF-L1-059: handle_source_update
IF-DS-INT-010: validate_mermaid_source
IF-L1-061: get_live_preview_data
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from diagram.manager import DiagramManager, DiagramResult
from diagram.mermaid_live_renderer import MermaidLiveRenderer, LivePreviewData
from diagram.models import Diagram, DiagramType, DiagramVersion, PayloadFormat
from diagram.renderer import DiagramRenderer, RenderHints
from diagram.validator import DiagramValidator, DiagramValidationError, ValidationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_manager() -> MagicMock:
    """Mock DiagramManager for isolated testing."""
    return MagicMock(spec=DiagramManager)


@pytest.fixture
def mock_validator() -> MagicMock:
    """Mock DiagramValidator for isolated testing."""
    return MagicMock(spec=DiagramValidator)


@pytest.fixture
def mock_renderer() -> MagicMock:
    """Mock DiagramRenderer for isolated testing."""
    return MagicMock(spec=DiagramRenderer)


@pytest.fixture
def mermaid_renderer(
    mock_manager: MagicMock,
    mock_validator: MagicMock,
    mock_renderer: MagicMock,
) -> MermaidLiveRenderer:
    """MermaidLiveRenderer with mocked collaborators."""
    return MermaidLiveRenderer(
        manager=mock_manager,
        validator=mock_validator,
        renderer=mock_renderer,
    )


@pytest.fixture
def sample_diagram() -> MagicMock:
    """Mock Diagram object."""
    diagram = MagicMock(spec=Diagram)
    diagram.id = uuid.uuid4()
    diagram.diagram_type = DiagramType.MERMAID
    diagram.name = "Test Mermaid Diagram"
    return diagram


@pytest.fixture
def sample_version() -> MagicMock:
    """Mock DiagramVersion object."""
    version = MagicMock(spec=DiagramVersion)
    version.version_number = 1
    version.payload_format = PayloadFormat.MERMAID
    version.payload = "flowchart TD\n  A --> B"
    return version


# ---------------------------------------------------------------------------
# REQ-L2-DS-007: 5 Mermaid-Typen validieren
# ---------------------------------------------------------------------------

class TestMermaidTypeValidation:
    """REQ-L2-DS-007: Validate all 5 Mermaid diagram types."""

    def test_validate_flowchart(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """flowchart type is valid."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=True,
            diagram_type="flowchart",
        )
        result = mermaid_renderer.validate_mermaid_source("flowchart TD\n  A --> B")
        assert result.is_valid
        assert result.diagram_type == "flowchart"

    def test_validate_sequence_diagram(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """sequenceDiagram type is valid."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=True,
            diagram_type="sequenceDiagram",
        )
        result = mermaid_renderer.validate_mermaid_source(
            "sequenceDiagram\n  Alice->>Bob: Hello"
        )
        assert result.is_valid
        assert result.diagram_type == "sequenceDiagram"

    def test_validate_class_diagram(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """classDiagram type is valid."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=True,
            diagram_type="classDiagram",
        )
        result = mermaid_renderer.validate_mermaid_source(
            "classDiagram\n  class Animal"
        )
        assert result.is_valid
        assert result.diagram_type == "classDiagram"

    def test_validate_state_diagram(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """stateDiagram type is valid."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=True,
            diagram_type="stateDiagram",
        )
        result = mermaid_renderer.validate_mermaid_source(
            "stateDiagram\n  [*] --> Active"
        )
        assert result.is_valid
        assert result.diagram_type == "stateDiagram"

    def test_validate_er_diagram(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """erDiagram type is valid."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=True,
            diagram_type="erDiagram",
        )
        result = mermaid_renderer.validate_mermaid_source(
            "erDiagram\n  CUSTOMER ||--o{ ORDER : places"
        )
        assert result.is_valid
        assert result.diagram_type == "erDiagram"


# ---------------------------------------------------------------------------
# REQ-L2-DS-007: Invalide Mermaid-Syntax ablehnen
# ---------------------------------------------------------------------------

class TestInvalidMermaidSyntax:
    """REQ-L2-DS-007: Reject invalid Mermaid syntax with line numbers."""

    def test_empty_source_rejected(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """Empty source is rejected."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=False,
            error_msg="Mermaid source must not be empty.",
            line_number=0,
        )
        result = mermaid_renderer.validate_mermaid_source("")
        assert not result.is_valid
        assert "empty" in result.error_msg.lower()

    def test_invalid_keyword_rejected(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """Invalid keyword is rejected with line number."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=False,
            error_msg="Mermaid source must start with a valid diagram type keyword; got 'invalid'.",
            line_number=1,
        )
        result = mermaid_renderer.validate_mermaid_source("invalid\n  A --> B")
        assert not result.is_valid
        assert result.line_number == 1

    def test_oversized_source_rejected(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """Source exceeding 1 MB is rejected."""
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=False,
            error_msg="Mermaid source exceeds maximum size of 1 MB (2000000 bytes).",
            line_number=0,
        )
        # Create a 2 MB source
        large_source = "flowchart TD\n" + "A --> B\n" * 200000
        result = mermaid_renderer.validate_mermaid_source(large_source)
        assert not result.is_valid
        assert "size" in result.error_msg.lower()


# ---------------------------------------------------------------------------
# IF-L1-059: Source-Update-Persistenz
# ---------------------------------------------------------------------------

class TestSourceUpdate:
    """IF-L1-059: handle_source_update persists via DiagramManager."""

    def test_handle_source_update_valid(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_manager: MagicMock,
        mock_validator: MagicMock,
        sample_diagram: MagicMock,
    ) -> None:
        """Valid source update is persisted."""
        diagram_id = sample_diagram.id
        source = "flowchart TD\n  A --> B"
        tenant = MagicMock()
        user = MagicMock()

        # Mock validation to succeed
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=True,
            diagram_type="flowchart",
        )

        # Mock manager.update_diagram to return the diagram
        mock_manager.update_diagram.return_value = sample_diagram

        result = mermaid_renderer.handle_source_update(
            diagram_id=diagram_id,
            source=source,
            tenant=tenant,
            user=user,
        )

        assert result == sample_diagram
        mock_manager.update_diagram.assert_called_once_with(
            diagram_id=diagram_id,
            payload_format=PayloadFormat.MERMAID,
            content=source,
            modified_by=user,
        )

    def test_handle_source_update_invalid_raises(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_validator: MagicMock,
    ) -> None:
        """Invalid source raises DiagramValidationError."""
        diagram_id = uuid.uuid4()
        source = "invalid\n  A --> B"
        tenant = MagicMock()

        # Mock validation to fail
        mock_validator.validate_mermaid_source.return_value = ValidationResult(
            is_valid=False,
            error_msg="Invalid keyword",
            line_number=1,
        )

        with pytest.raises(DiagramValidationError, match="validation failed"):
            mermaid_renderer.handle_source_update(
                diagram_id=diagram_id,
                source=source,
                tenant=tenant,
            )


# ---------------------------------------------------------------------------
# IF-L1-061: Render-Hints korrekt
# ---------------------------------------------------------------------------

class TestRenderHints:
    """IF-L1-061: get_live_preview_data returns correct render hints."""

    def test_get_live_preview_data_success(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_manager: MagicMock,
        mock_renderer: MagicMock,
        sample_diagram: MagicMock,
        sample_version: MagicMock,
    ) -> None:
        """Successful preview data retrieval."""
        diagram_id = sample_diagram.id

        # Mock manager.get_diagram
        mock_manager.get_diagram.return_value = DiagramResult(
            diagram=sample_diagram,
            version=sample_version,
            renderable=None,
        )

        # Mock renderer.get_render_hints
        mock_renderer.get_render_hints.return_value = RenderHints(
            render_hint="mermaid.js",
            diagram_type=DiagramType.MERMAID,
            supported_types=["flowchart", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram"],
            client_side=True,
        )

        result = mermaid_renderer.get_live_preview_data(diagram_id)

        assert isinstance(result, LivePreviewData)
        assert result.diagram_id == diagram_id
        assert result.source == sample_version.payload
        assert result.diagram_type == "flowchart"
        assert result.render_hints is not None
        assert result.render_hints.render_hint == "mermaid.js"
        assert not result.fallback_mode

    def test_get_live_preview_data_no_version(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_manager: MagicMock,
        sample_diagram: MagicMock,
    ) -> None:
        """Preview data with no version activates fallback."""
        diagram_id = sample_diagram.id

        mock_manager.get_diagram.return_value = DiagramResult(
            diagram=sample_diagram,
            version=None,
            renderable=None,
        )

        result = mermaid_renderer.get_live_preview_data(diagram_id)

        assert result.fallback_mode
        assert "No version available" in result.error_message


# ---------------------------------------------------------------------------
# REQ-L2-DS-007 AC5/AC9: Fallback bei Renderer-Fehler
# ---------------------------------------------------------------------------

class TestRendererFallback:
    """REQ-L2-DS-007 AC5/AC9: Fallback on renderer failure."""

    def test_fallback_on_renderer_exception(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_manager: MagicMock,
        mock_renderer: MagicMock,
        sample_diagram: MagicMock,
        sample_version: MagicMock,
    ) -> None:
        """Renderer exception activates fallback mode."""
        diagram_id = sample_diagram.id

        mock_manager.get_diagram.return_value = DiagramResult(
            diagram=sample_diagram,
            version=sample_version,
            renderable=None,
        )

        # Mock renderer to raise an exception
        mock_renderer.get_render_hints.side_effect = Exception("Renderer load error")

        result = mermaid_renderer.get_live_preview_data(diagram_id)

        assert result.fallback_mode
        assert result.source == sample_version.payload
        assert "Renderer error" in result.error_message
        assert result.render_hints is None

    def test_fallback_on_unexpected_error(
        self,
        mermaid_renderer: MermaidLiveRenderer,
        mock_manager: MagicMock,
    ) -> None:
        """Unexpected error activates fallback mode."""
        diagram_id = uuid.uuid4()

        # Mock manager to raise an exception
        mock_manager.get_diagram.side_effect = Exception("Database connection failed")

        result = mermaid_renderer.get_live_preview_data(diagram_id)

        assert result.fallback_mode
        assert "Unexpected error" in result.error_message


# ---------------------------------------------------------------------------
# IF-DS-INT-009: register_mermaid_mcp_type
# ---------------------------------------------------------------------------

class TestMcpRegistration:
    """IF-DS-INT-009: register_mermaid_mcp_type is a no-op in v1."""

    def test_register_mermaid_mcp_type_noop(
        self,
        mermaid_renderer: MermaidLiveRenderer,
    ) -> None:
        """register_mermaid_mcp_type completes without error."""
        # Should not raise
        mermaid_renderer.register_mermaid_mcp_type()


# ---------------------------------------------------------------------------
# Integration: Type detection
# ---------------------------------------------------------------------------

class TestTypeDetection:
    """Internal helper: _detect_mermaid_type."""

    def test_detect_flowchart(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("flowchart TD\n  A --> B") == "flowchart"

    def test_detect_graph_alias(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("graph LR\n  A --> B") == "flowchart"

    def test_detect_sequence(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("sequenceDiagram\n  A->>B") == "sequenceDiagram"

    def test_detect_class(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("classDiagram\n  class A") == "classDiagram"

    def test_detect_state(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("stateDiagram\n  [*] --> A") == "stateDiagram"

    def test_detect_er(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("erDiagram\n  A ||--o{ B") == "erDiagram"

    def test_detect_empty(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("") == ""

    def test_detect_invalid(self, mermaid_renderer: MermaidLiveRenderer) -> None:
        assert mermaid_renderer._detect_mermaid_type("invalid\n  A --> B") == ""
