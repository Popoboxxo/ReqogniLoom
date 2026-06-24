"""
COMP-DS-001 DiagramManager — Integration tests.

Covers:
  REQ-L2-DS-001 / REQ-L3-DM-001: Diagram CRUD and Version 1 creation
  REQ-L2-DS-001 / REQ-L3-DM-002: Immutable versioning (N+1), old versions intact
  REQ-L2-DS-001 / REQ-L3-DM-003: get_diagram with renderable enrichment
  REQ-L2-DS-001 / REQ-L3-DM-004: list_versions chronological order
  REQ-L2-DS-001:                  Tenant isolation

Requires database (pytest.mark.django_db).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from diagram.manager import DiagramManager, DiagramResult
from diagram.models import Diagram, DiagramVersion
from diagram.validator import DiagramValidationError
from diagram.tests.conftest import active_tenant, VALID_MERMAID_BLOCK, VALID_MERMAID_FLOW

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager() -> DiagramManager:
    return DiagramManager()


# ---------------------------------------------------------------------------
# REQ-L3-DM-001: create_diagram
# ---------------------------------------------------------------------------

class TestCreateDiagram:
    """REQ-L3-DM-001: Creation yields UUID, Version 1 and audit entry."""

    def test_create_returns_diagram_with_uuid(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Test Block Diagram",
                diagram_type="block",
                payload_format="mermaid",
                content=VALID_MERMAID_BLOCK,
                tenant=tenant_a,
            )

        assert diagram.id is not None
        assert isinstance(diagram.id, uuid.UUID)
        assert diagram.name == "Test Block Diagram"

    def test_create_generates_version_1(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Flow Diagram",
                diagram_type="flow",
                payload_format="mermaid",
                content=VALID_MERMAID_FLOW,
                tenant=tenant_a,
            )

        assert diagram.current_version is not None
        assert diagram.current_version.version_number == 1

    def test_create_persists_version_payload(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Context Diagram",
                diagram_type="context",
                payload_format="mermaid",
                content="flowchart LR\n  U-->S",
                tenant=tenant_a,
            )

        assert diagram.current_version.payload == "flowchart LR\n  U-->S"
        assert diagram.current_version.payload_format == "mermaid"

    def test_create_invalid_payload_raises(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            with pytest.raises(DiagramValidationError):
                manager.create_diagram(
                    name="Bad Diagram",
                    diagram_type="block",
                    payload_format="mermaid",
                    content="",  # empty — invalid
                    tenant=tenant_a,
                )

    def test_create_unsupported_type_raises(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            with pytest.raises(DiagramValidationError, match="Unsupported diagram_type"):
                manager.create_diagram(
                    name="Bad Diagram",
                    diagram_type="sequence",  # not supported
                    payload_format="mermaid",
                    content="sequenceDiagram\n  A->>B: Hi",
                    tenant=tenant_a,
                )

    def test_create_writes_audit_log(self, manager, tenant_a, workspace_a):
        with patch("diagram.manager.log_write") as mock_log:
            with active_tenant(tenant_a):
                manager.create_diagram(
                    name="Audited Diagram",
                    diagram_type="block",
                    payload_format="mermaid",
                    content=VALID_MERMAID_BLOCK,
                    tenant=tenant_a,
                )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["operation"] == "create"
        assert call_kwargs["entity_type"] == "Diagram"


# ---------------------------------------------------------------------------
# REQ-L3-DM-002: update_diagram — immutable versioning
# ---------------------------------------------------------------------------

class TestUpdateDiagram:
    """REQ-L3-DM-002: Update creates N+1; old versions remain unchanged."""

    def _make_diagram(self, manager, tenant_a):
        return manager.create_diagram(
            name="Versioned Diagram",
            diagram_type="flow",
            payload_format="mermaid",
            content=VALID_MERMAID_FLOW,
            tenant=tenant_a,
        )

    def test_update_creates_version_n_plus_1(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_diagram(manager, tenant_a)
            new_version = manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  X --> Y",
            )

        assert new_version.version_number == 2

    def test_update_old_version_unchanged(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_diagram(manager, tenant_a)
            original_payload = diagram.current_version.payload

            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  New --> Flow",
            )

        # Re-fetch the old version from DB using unscoped manager
        old_version = DiagramVersion.unscoped.get(
            diagram_id=diagram.id, version_number=1
        )
        assert old_version.payload == original_payload

    def test_multiple_updates_increment_monotonically(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_diagram(manager, tenant_a)
            v2 = manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  A-->B",
            )
            v3 = manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  B-->C",
            )

        assert v2.version_number == 2
        assert v3.version_number == 3

    def test_update_current_version_pointer_updated(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_diagram(manager, tenant_a)
            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  Z-->W",
            )

        diagram.refresh_from_db()
        assert diagram.current_version.version_number == 2

    def test_update_invalid_payload_raises(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_diagram(manager, tenant_a)
            with pytest.raises(DiagramValidationError):
                manager.update_diagram(
                    diagram_id=diagram.id,
                    payload_format="mermaid",
                    content="",  # invalid
                )

    def test_update_writes_audit_log(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = self._make_diagram(manager, tenant_a)

        with patch("diagram.manager.log_write") as mock_log:
            with active_tenant(tenant_a):
                manager.update_diagram(
                    diagram_id=diagram.id,
                    payload_format="mermaid",
                    content="flowchart TD\n  Updated --> Flow",
                )

        mock_log.assert_called_once()
        assert mock_log.call_args.kwargs["operation"] == "update"


# ---------------------------------------------------------------------------
# REQ-L3-DM-003: get_diagram
# ---------------------------------------------------------------------------

class TestGetDiagram:
    """REQ-L3-DM-003: get_diagram returns DiagramResult with renderable."""

    def test_get_returns_diagram_result(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Renderable Diagram",
                diagram_type="block",
                payload_format="mermaid",
                content=VALID_MERMAID_BLOCK,
                tenant=tenant_a,
            )
            result = manager.get_diagram(diagram.id)

        assert isinstance(result, DiagramResult)
        assert result.diagram.id == diagram.id

    def test_get_includes_renderable(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="With Renderable",
                diagram_type="flow",
                payload_format="mermaid",
                content=VALID_MERMAID_FLOW,
                tenant=tenant_a,
            )
            result = manager.get_diagram(diagram.id)

        assert result.renderable is not None
        assert result.renderable.render_hint == "mermaid.js"
        assert result.renderable.content == VALID_MERMAID_FLOW

    def test_get_specific_version(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Multi-version Diagram",
                diagram_type="flow",
                payload_format="mermaid",
                content=VALID_MERMAID_FLOW,
                tenant=tenant_a,
            )
            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  V2 --> Node",
            )
            # Request old version explicitly
            result = manager.get_diagram(diagram.id, version_number=1)

        assert result.version.version_number == 1
        assert result.version.payload == VALID_MERMAID_FLOW

    def test_get_nonexistent_raises(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            with pytest.raises(Diagram.DoesNotExist):
                manager.get_diagram(uuid.uuid4())


# ---------------------------------------------------------------------------
# REQ-L3-DM-004: list_versions
# ---------------------------------------------------------------------------

class TestListVersions:
    """REQ-L3-DM-004: list_versions returns chronological version history."""

    def test_list_versions_single(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="History Test",
                diagram_type="context",
                payload_format="mermaid",
                content="flowchart LR\n  U-->S",
                tenant=tenant_a,
            )
            versions = manager.list_versions(diagram.id)

        assert len(versions) == 1
        assert versions[0].version_number == 1

    def test_list_versions_multiple_ordered(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Multi-version History",
                diagram_type="flow",
                payload_format="mermaid",
                content=VALID_MERMAID_FLOW,
                tenant=tenant_a,
            )
            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  A-->B",
            )
            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  B-->C",
            )
            versions = manager.list_versions(diagram.id)

        assert len(versions) == 3
        assert [v.version_number for v in versions] == [1, 2, 3]

    def test_list_versions_includes_timestamps(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = manager.create_diagram(
                name="Timestamp Test",
                diagram_type="block",
                payload_format="mermaid",
                content=VALID_MERMAID_BLOCK,
                tenant=tenant_a,
            )
            versions = manager.list_versions(diagram.id)

        assert versions[0].created_at is not None


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """REQ-L2-DS-001: Diagrams are isolated by tenant."""

    def test_tenant_a_cannot_see_tenant_b_diagram(
        self, manager, tenant_a, tenant_b, workspace_a, workspace_b
    ):
        # Create diagram under tenant_b
        with active_tenant(tenant_b):
            diagram_b = manager.create_diagram(
                name="Tenant B Diagram",
                diagram_type="block",
                payload_format="mermaid",
                content=VALID_MERMAID_BLOCK,
                tenant=tenant_b,
            )

        # Tenant A should not be able to retrieve it
        with active_tenant(tenant_a):
            with pytest.raises(Diagram.DoesNotExist):
                manager.get_diagram(diagram_b.id)

    def test_list_versions_scoped_to_tenant(
        self, manager, tenant_a, tenant_b, workspace_a, workspace_b
    ):
        with active_tenant(tenant_b):
            diagram_b = manager.create_diagram(
                name="Tenant B Only",
                diagram_type="flow",
                payload_format="mermaid",
                content=VALID_MERMAID_FLOW,
                tenant=tenant_b,
            )

        with active_tenant(tenant_a):
            # tenant_a cannot even see tenant_b's diagram
            with pytest.raises(Diagram.DoesNotExist):
                manager.list_versions(diagram_b.id)
