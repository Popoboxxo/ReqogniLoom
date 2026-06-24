"""
ARCH-L1-013 DiagramService — Public service facade.

leaf_id: COMP-DS-001 (DiagramManager)
req_id: REQ-L1-027, REQ-L2-DS-001 through REQ-L2-DS-005

This module is the single public import surface for downstream consumers
(ApplicationService IF-L1-032, McpServer IF-L1-033).  All DiagramService
operations are accessed through these functions.

Public import paths:
    from diagram.services import (
        create_diagram,
        update_diagram,
        get_diagram,
        list_versions,
        get_mcp_artifact,
    )

Architecture:
    docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/
    L2_DiagramServiceSystem_Architecture.md
"""
from __future__ import annotations

import uuid
from typing import Optional

from diagram.manager import DiagramManager, DiagramResult, DiagramValidationError  # noqa: F401
from diagram.models import Diagram, DiagramVersion  # noqa: F401
from diagram.mcp_artifact_provider import McpArtifactProvider

# ---------------------------------------------------------------------------
# Module-level singletons (lazy-initialised, stateless)
# ---------------------------------------------------------------------------

_manager = DiagramManager()
_mcp_provider = McpArtifactProvider(diagram_manager=_manager)


# ---------------------------------------------------------------------------
# IF-L1-032: ApplicationService → DiagramManager CRUD
# ---------------------------------------------------------------------------

def create_diagram(
    *,
    name: str,
    diagram_type: str,
    payload_format: str,
    content: str,
    tenant: object,
    description: str = "",
    created_by: Optional[object] = None,
    target_id: Optional[uuid.UUID] = None,
) -> Diagram:
    """Create a new Diagram and its initial DiagramVersion (v1).

    IF-L1-032 entry point for ApplicationService.

    Args:
        name:           Human-readable diagram name.
        diagram_type:   One of 'block' | 'flow' | 'context'.
        payload_format: One of 'mermaid' | 'plantuml' | 'json'.
        content:        Raw diagram payload string.
        tenant:         Active Tenant ORM object.
        description:    Optional description.
        created_by:     Optional User ORM object for audit.
        target_id:      Optional target Artifact UUID for a 'documents' TraceLink.

    Returns:
        The created Diagram ORM object.

    Raises:
        DiagramValidationError: If the payload fails type-specific validation.

    REQ-L2-DS-001, REQ-L3-DM-001
    """
    return _manager.create_diagram(
        name=name,
        diagram_type=diagram_type,
        payload_format=payload_format,
        content=content,
        tenant=tenant,
        description=description,
        created_by=created_by,
        target_id=target_id,
    )


def update_diagram(
    *,
    diagram_id: uuid.UUID,
    payload_format: str,
    content: str,
    modified_by: Optional[object] = None,
    target_id: Optional[uuid.UUID] = None,
) -> DiagramVersion:
    """Update a Diagram by creating a new immutable DiagramVersion (N+1).

    IF-L1-032 entry point for ApplicationService.

    Args:
        diagram_id:     UUID of the Diagram to update.
        payload_format: New payload format.
        content:        New diagram payload string.
        modified_by:    Optional User ORM object for audit.
        target_id:      Optional target Artifact UUID for additional TraceLink.

    Returns:
        The newly created DiagramVersion ORM object.

    Raises:
        Diagram.DoesNotExist:   If diagram_id not found (tenant-scoped).
        DiagramValidationError: If the new payload is invalid.

    REQ-L2-DS-001, REQ-L3-DM-002
    """
    return _manager.update_diagram(
        diagram_id=diagram_id,
        payload_format=payload_format,
        content=content,
        modified_by=modified_by,
        target_id=target_id,
    )


def get_diagram(
    diagram_id: uuid.UUID,
    version_number: Optional[int] = None,
) -> DiagramResult:
    """Retrieve a Diagram enriched with render information.

    IF-L1-032 entry point for ApplicationService.

    Args:
        diagram_id:     UUID of the Diagram to retrieve.
        version_number: Optional specific version number. Defaults to current.

    Returns:
        DiagramResult(diagram, version, renderable).

    Raises:
        Diagram.DoesNotExist: If diagram_id not found.

    REQ-L2-DS-001, REQ-L2-DS-003, REQ-L3-DM-003
    """
    return _manager.get_diagram(
        diagram_id=diagram_id,
        version_number=version_number,
    )


def list_versions(diagram_id: uuid.UUID) -> list[DiagramVersion]:
    """Return all DiagramVersions for a Diagram, sorted by version_number.

    IF-L1-032 entry point for ApplicationService.

    Args:
        diagram_id: UUID of the parent Diagram.

    Returns:
        List of DiagramVersion objects, version_number ascending.

    Raises:
        Diagram.DoesNotExist: If diagram_id not found.

    REQ-L2-DS-001, REQ-L3-DM-004
    """
    return _manager.list_versions(diagram_id=diagram_id)


# ---------------------------------------------------------------------------
# IF-L1-033: McpServer → McpArtifactProvider
# ---------------------------------------------------------------------------

def get_mcp_artifact(diagram_id: str) -> dict:
    """Handle MCP 'artifact.get' call for a diagram artefact.

    IF-L1-033 entry point for McpServer.

    Args:
        diagram_id: String UUID of the diagram.

    Returns:
        MCP response dict (see McpArtifactProvider.get_artifact).

    REQ-L2-DS-005, REQ-L3-MAP-001
    """
    return _mcp_provider.get_artifact(diagram_id=diagram_id)


# ---------------------------------------------------------------------------
# Re-exports for downstream consumers
# ---------------------------------------------------------------------------

__all__ = [
    "create_diagram",
    "update_diagram",
    "get_diagram",
    "list_versions",
    "get_mcp_artifact",
    # DTOs
    "DiagramResult",
    "DiagramValidationError",
    # ORM types
    "Diagram",
    "DiagramVersion",
]
