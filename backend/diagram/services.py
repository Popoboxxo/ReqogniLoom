"""
ARCH-L1-013 DiagramService — Public service facade.

leaf_id: COMP-DS-001 (DiagramManager), COMP-DS-006 (CanvasEditor),
         COMP-DS-007 (MermaidLiveRenderer)
req_id: REQ-L1-027, REQ-L2-DS-001 through REQ-L2-DS-007,
        REQ-L1-056, REQ-L1-057

This module is the single public import surface for downstream consumers
(ApplicationService IF-L1-032, McpServer IF-L1-033).  All DiagramService
operations are accessed through these functions.

Public import paths:
    from diagram.services import (
        create_diagram,
        update_diagram,
        get_diagram,
        list_versions,
        list_diagrams,
        get_mcp_artifact,
        canvas_auto_save,
        get_canvas_diagram,
        update_mermaid_source,
        get_mermaid_preview,
    )

Architecture:
    docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/
    L2_DiagramServiceSystem_Architecture.md
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from diagram.canvas_editor import CanvasEditor, CanvasExportResult  # noqa: F401
from diagram.manager import DiagramManager, DiagramResult, DiagramValidationError  # noqa: F401
from diagram.mermaid_live_renderer import MermaidLiveRenderer, LivePreviewData  # noqa: F401
from diagram.models import Diagram, DiagramVersion  # noqa: F401
from diagram.mcp_artifact_provider import McpArtifactProvider

if TYPE_CHECKING:
    from auth_tenancy.context import AuthContext

# ---------------------------------------------------------------------------
# Module-level singletons (lazy-initialised, stateless)
# ---------------------------------------------------------------------------

_manager = DiagramManager()
_mcp_provider = McpArtifactProvider(diagram_manager=_manager)
_mermaid_renderer = MermaidLiveRenderer(manager=_manager)
_canvas_editor = CanvasEditor(manager=_manager)


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
    workspace_id: Optional[uuid.UUID] = None,
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
        workspace_id:   Optional owning workspace UUID (REQ-173).

    Returns:
        The created Diagram ORM object.

    Raises:
        DiagramValidationError: If the payload fails type-specific validation.

    REQ-L2-DS-001, REQ-L3-DM-001, REQ-173
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
        workspace_id=workspace_id,
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


def get_diagram_header(diagram_id: uuid.UUID, tenant_id: uuid.UUID) -> Diagram:
    """Return a single tenant-scoped Diagram header by id (REQ-066, REQ-173).

    Encapsulates the tenant-scoped ORM lookup so REST views stay ORM-free.
    Unlike ``get_diagram``, this returns the bare Diagram header (no version /
    render enrichment) — used by DiagramViewSet._resolve_workflow_target to
    read workspace_id without pulling in DiagramManager's render pipeline.

    Args:
        diagram_id: UUID of the target Diagram.
        tenant_id:  Active tenant primary key (isolation boundary).

    Returns:
        The matching :class:`Diagram` instance.

    Raises:
        Diagram.DoesNotExist: When no Diagram with the given id exists for
            the tenant.

    req_id: REQ-066, REQ-173, REQ-L2-DS-001
    """
    return Diagram.objects.get(id=diagram_id, tenant_id=tenant_id)


def delete_diagram(diagram_id: uuid.UUID, tenant_id: uuid.UUID, ctx: "AuthContext") -> None:
    """Soft-delete a tenant-scoped Diagram via the workflow engine's outdate()
    (REQ-066, REQ-006/Phase 0).

    Encapsulates the tenant-scoped ORM lookup so REST views stay ORM-free.
    Physical deletion intentionally avoided — the Diagram row and its
    versions remain for audit/history purposes; ``outdate()`` marks the item
    "outdated" in ``WorkflowItemState`` (Diagram is not registered in
    ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``, so no denormalized
    field on Diagram itself is written).

    Args:
        diagram_id: UUID of the Diagram to delete.
        tenant_id:  Active tenant primary key (isolation boundary).
        ctx:        Resolved AuthContext of the caller (REQ-165/REQ-167: the
            WorkflowEngine is the sole authority for the transition).

    Raises:
        Diagram.DoesNotExist: If no diagram with the given id exists for the
            tenant.

    req_id: REQ-066, REQ-L2-DS-001
    """
    from workflow.services import outdate

    diagram = Diagram.objects.get(id=diagram_id, tenant_id=tenant_id)
    outdate(
        item_id=diagram.id,
        item_type="Diagram",
        workspace_id=diagram.workspace_id,
        ctx=ctx,
        reason="deleted via diagram delete",
    )


def list_diagrams(
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    include_deleted: bool = False,
) -> list[Diagram]:
    """Return all Diagrams for a workspace, tenant-scoped (MCP diagram.query).

    Diagram has no denormalized status mirror field (see ``delete_diagram``
    docstring) — soft-deleted (outdated) rows are excluded via
    ``workflow.services.outdated_item_ids("Diagram", ...)`` instead of a
    ``lifecycle_status`` filter.

    Args:
        workspace_id:    UUID of the owning workspace.
        tenant_id:       Active tenant primary key (isolation boundary).
        include_deleted: If True, include outdated (soft-deleted) diagrams.
            Defaults to False.

    Returns:
        List of Diagram ORM objects, newest first.

    req_id: REQ-066, REQ-173, REQ-L2-DS-001
    """
    qs = Diagram.objects.filter(workspace_id=workspace_id, tenant_id=tenant_id)
    if not include_deleted:
        from workflow.services import outdated_item_ids

        qs = qs.exclude(
            id__in=outdated_item_ids("Diagram", tenant_id=tenant_id)
        )
    return list(qs.order_by("-created_at"))


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
# IF-L1-058 / IF-L1-060: CanvasEditor → Canvas Auto-Save + Export
# REQ-L1-056, REQ-L2-DS-006
# ---------------------------------------------------------------------------

def canvas_auto_save(
    *,
    stroke_data: dict,
    tenant: object,
    diagram_id: Optional[uuid.UUID] = None,
    name: str = "Canvas Drawing",
    user: Optional[object] = None,
    target_id: Optional[uuid.UUID] = None,
) -> Diagram:
    """Auto-Save canvas stroke data (IF-L1-058 entry point).

    Validates stroke data via IF-DS-INT-004, then persists via IF-DS-INT-005.
    Creates a new canvas diagram or updates an existing one (new version).

    Args:
        stroke_data: Canvas stroke data dict with 'strokes' key.
        tenant:      Active Tenant ORM object.
        diagram_id:  Optional UUID of existing diagram (update). None = create.
        name:        Diagram name (used only on create).
        user:        Optional User ORM object for audit.
        target_id:   Optional target Artifact UUID for TraceLink creation.

    Returns:
        The created or updated Diagram ORM object.

    Raises:
        DiagramValidationError: If stroke data fails validation.

    REQ-L2-DS-006, REQ-L1-056
    """
    return _canvas_editor.handle_stroke_update(
        diagram_id=diagram_id,
        stroke_data=stroke_data,
        tenant=tenant,
        user=user,
        name=name,
        target_id=target_id,
    )


def get_canvas_diagram(
    diagram_id: uuid.UUID,
    version_number: Optional[int] = None,
) -> CanvasExportResult:
    """Retrieve a canvas diagram with stroke data and SVG export (IF-L1-060).

    Args:
        diagram_id:     UUID of the canvas diagram.
        version_number: Optional specific version. Defaults to current.

    Returns:
        CanvasExportResult with stroke_data, svg, and version info.

    Raises:
        Diagram.DoesNotExist: If diagram_id not found.

    REQ-L2-DS-006, REQ-L1-056
    """
    return _canvas_editor.get_canvas(
        diagram_id=diagram_id,
        version_number=version_number,
    )


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
# IF-L1-059, IF-L1-061: MermaidLiveRenderer — COMP-DS-007
# REQ-L1-057, REQ-L2-DS-007
# ---------------------------------------------------------------------------

def update_mermaid_source(
    *,
    diagram_id: uuid.UUID,
    source: str,
    tenant: object,
    user: Optional[object] = None,
) -> Diagram:
    """Update Mermaid source code for an existing diagram.

    IF-L1-059 entry point: PUT /api/v1/diagrams/{id}/mermaid-source

    Validates the Mermaid source and persists via DiagramManager.

    Args:
        diagram_id: UUID of the diagram to update.
        source:     New Mermaid source code.
        tenant:     Active Tenant ORM object.
        user:       Optional User ORM object for audit.

    Returns:
        The updated Diagram ORM object.

    Raises:
        DiagramValidationError: If source validation fails.
        Diagram.DoesNotExist:   If diagram_id not found.

    REQ-L2-DS-007, REQ-L1-057
    """
    return _mermaid_renderer.handle_source_update(
        diagram_id=diagram_id,
        source=source,
        tenant=tenant,
        user=user,
    )


def get_mermaid_preview(
    diagram_id: uuid.UUID,
) -> LivePreviewData:
    """Retrieve all data needed for Mermaid live preview.

    IF-L1-061 output: Source code + Render-Hints + Export data.

    Fallback behavior (REQ-L2-DS-007 AC5/AC9):
      If rendering fails, the source code is still returned in fallback_mode=True.

    Args:
        diagram_id: UUID of the diagram.

    Returns:
        LivePreviewData with source, render_hints, and fallback info.

    Raises:
        Diagram.DoesNotExist: If diagram_id not found (only in non-fallback cases).

    REQ-L2-DS-007, REQ-L1-057
    """
    return _mermaid_renderer.get_live_preview_data(diagram_id=diagram_id)


def validate_mermaid_source(
    source: str,
    diagram_type: str = "",
) -> "ValidationResult":
    """Validate Mermaid source code for the 5 supported types.

    Convenience wrapper around MermaidLiveRenderer.validate_mermaid_source().

    Args:
        source:       Raw Mermaid source code string.
        diagram_type: Optional declared diagram type for cross-check.

    Returns:
        ValidationResult with is_valid, error_msg, line_number, diagram_type.

    REQ-L2-DS-007, REQ-L1-057
    """
    from diagram.validator import ValidationResult
    return _mermaid_renderer.validate_mermaid_source(source, diagram_type)


# ---------------------------------------------------------------------------
# Re-exports for downstream consumers
# ---------------------------------------------------------------------------

__all__ = [
    # CRUD operations
    "create_diagram",
    "update_diagram",
    "get_diagram",
    "get_diagram_header",
    "delete_diagram",
    "list_diagrams",
    "list_versions",
    "get_mcp_artifact",
    # Canvas editor — COMP-DS-006
    "canvas_auto_save",
    "get_canvas_diagram",
    # Mermaid live renderer — COMP-DS-007
    "update_mermaid_source",
    "get_mermaid_preview",
    "validate_mermaid_source",
    # DTOs
    "CanvasExportResult",
    "DiagramResult",
    "DiagramValidationError",
    "LivePreviewData",
    # ORM types
    "Diagram",
    "DiagramVersion",
]
