"""
COMP-DS-004 TraceabilityConnector — Unit and integration tests.

Covers:
  REQ-L2-DS-004 / REQ-L3-TC-001: 'documents' TraceLink creation
  REQ-L3-TC-001: Errors from TraceabilityEngine propagated transparently
  REQ-L2-DS-004: TraceLink can bind a Diagram to a Requirement/Architecture

IF-DS-INT-003: create_document_link(diagram_id, target_id)
IF-L1-034: delegates to traceability.services.create_trace_link

TestCreateDocumentLink: pure unit tests (no DB) — use mocks only.
TestCreateDocumentLinkWithManagerIntegration: requires Django DB.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from diagram.traceability_connector import TraceabilityConnector
from traceability.exceptions import TargetNotFoundError


# TestCreateDocumentLink uses only mocks — no DB marker needed.


@pytest.fixture
def connector() -> TraceabilityConnector:
    return TraceabilityConnector()


class TestCreateDocumentLink:
    """REQ-L3-TC-001: create_document_link delegates to TraceabilityEngine."""

    def test_link_type_is_documents(self, connector: TraceabilityConnector) -> None:
        """The link_type is hard-coded to 'documents' (REQ-L3-TC-001)."""
        assert connector.LINK_TYPE == "documents"

    def test_delegates_to_create_trace_link(self, connector: TraceabilityConnector) -> None:
        diagram_id = uuid.uuid4()
        target_id = uuid.uuid4()
        mock_link = MagicMock()

        with patch(
            "diagram.traceability_connector.create_trace_link",
            return_value=mock_link,
        ) as mock_create:
            result = connector.create_document_link(
                diagram_id=diagram_id,
                target_id=target_id,
            )

        mock_create.assert_called_once_with(
            source_id=diagram_id,
            target_id=target_id,
            link_type="documents",
            created_by_id=None,
        )
        assert result is mock_link

    def test_propagates_created_by_id(self, connector: TraceabilityConnector) -> None:
        diagram_id = uuid.uuid4()
        target_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        with patch(
            "diagram.traceability_connector.create_trace_link",
            return_value=MagicMock(),
        ) as mock_create:
            connector.create_document_link(
                diagram_id=diagram_id,
                target_id=target_id,
                created_by_id=actor_id,
            )

        assert mock_create.call_args.kwargs["created_by_id"] == actor_id

    def test_propagates_traceability_engine_errors(
        self, connector: TraceabilityConnector
    ) -> None:
        """REQ-L3-TC-001: errors from TraceabilityEngine are propagated transparently."""
        with patch(
            "diagram.traceability_connector.create_trace_link",
            side_effect=TargetNotFoundError("Target not found"),
        ):
            with pytest.raises(TargetNotFoundError, match="Target not found"):
                connector.create_document_link(
                    diagram_id=uuid.uuid4(),
                    target_id=uuid.uuid4(),
                )


@pytest.mark.django_db
class TestCreateDocumentLinkWithManagerIntegration:
    """REQ-L2-DS-004: Documents TraceLink created when target_id provided."""

    def test_create_diagram_with_trace_link(
        self, tenant_a, workspace_a
    ) -> None:
        """Creating a diagram with target_id triggers documents TraceLink."""
        from diagram.manager import DiagramManager
        from diagram.tests.conftest import active_tenant, VALID_MERMAID_BLOCK

        manager = DiagramManager()
        target_id = uuid.uuid4()

        with patch("diagram.traceability_connector.create_trace_link") as mock_create:
            with active_tenant(tenant_a):
                manager.create_diagram(
                    name="Diagram with TraceLink",
                    diagram_type="block",
                    payload_format="mermaid",
                    content=VALID_MERMAID_BLOCK,
                    tenant=tenant_a,
                    target_id=target_id,
                )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["link_type"] == "documents"
        assert call_kwargs["target_id"] == target_id


