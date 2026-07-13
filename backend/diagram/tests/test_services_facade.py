"""
DiagramService public facade — smoke tests.

Verifies that the public import surface (diagram.services) wires correctly
to the underlying manager and that each function is callable.

Covers:
  REQ-L1-027, REQ-L2-DS-001 through REQ-L2-DS-005
  IF-L1-032: create_diagram, update_diagram, get_diagram, list_versions
  IF-L1-033: get_mcp_artifact
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from diagram.services import (
    create_diagram,
    get_diagram,
    get_mcp_artifact,
    list_versions,
    update_diagram,
)
from diagram.tests.conftest import VALID_MERMAID_BLOCK, VALID_MERMAID_FLOW, active_tenant

pytestmark = pytest.mark.django_db


class TestServiceFacadeCreate:
    """IF-L1-032: create_diagram facade."""

    def test_create_diagram_smoke(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = create_diagram(
                name="Facade Block",
                diagram_type="block",
                payload_format="mermaid",
                content=VALID_MERMAID_BLOCK,
                tenant=tenant_a,
            )

        assert diagram.id is not None
        assert diagram.name == "Facade Block"

    def test_create_returns_version_1(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = create_diagram(
                name="Facade Flow",
                diagram_type="flow",
                payload_format="mermaid",
                content=VALID_MERMAID_FLOW,
                tenant=tenant_a,
            )

        assert diagram.current_version.version_number == 1


class TestServiceFacadeUpdate:
    """IF-L1-032: update_diagram facade."""

    def test_update_diagram_smoke(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = create_diagram(
                name="Update Target",
                diagram_type="flow",
                payload_format="mermaid",
                content=VALID_MERMAID_FLOW,
                tenant=tenant_a,
            )
            new_version = update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="flowchart TD\n  Updated --> Flow",
            )

        assert new_version.version_number == 2


class TestServiceFacadeGet:
    """IF-L1-032: get_diagram facade."""

    def test_get_diagram_smoke(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = create_diagram(
                name="Get Target",
                diagram_type="context",
                payload_format="mermaid",
                content="flowchart LR\n  U-->S",
                tenant=tenant_a,
            )
            result = get_diagram(diagram.id)

        assert result.diagram.id == diagram.id
        assert result.renderable is not None


class TestServiceFacadeListVersions:
    """IF-L1-032: list_versions facade."""

    def test_list_versions_smoke(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = create_diagram(
                name="History Target",
                diagram_type="block",
                payload_format="mermaid",
                content=VALID_MERMAID_BLOCK,
                tenant=tenant_a,
            )
            update_diagram(
                diagram_id=diagram.id,
                payload_format="mermaid",
                content="block-beta\n  Updated[Node]",
            )
            versions = list_versions(diagram.id)

        assert len(versions) == 2
        assert versions[0].version_number == 1
        assert versions[1].version_number == 2


class TestServiceFacadeMcpArtifact:
    """IF-L1-033: get_mcp_artifact facade."""

    def test_valid_id_returns_ok(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            diagram = create_diagram(
                name="MCP Target",
                diagram_type="block",
                payload_format="mermaid",
                content=VALID_MERMAID_BLOCK,
                tenant=tenant_a,
            )
            response = get_mcp_artifact(str(diagram.id))

        assert response["type"] == "artifact"
        assert response["error"] is None

    def test_invalid_id_returns_error(self):
        response = get_mcp_artifact("invalid-uuid")
        assert response["type"] == "error"
        assert response["error"]["code"] == "artifact_not_found"
