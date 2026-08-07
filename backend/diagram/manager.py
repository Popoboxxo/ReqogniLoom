"""
ARCH-L1-013 DiagramService — DiagramManager (central coordinator).

leaf_id: COMP-DS-001_DiagramManager
req_id: REQ-L1-027, REQ-L2-DS-001, REQ-L3-DM-001, REQ-L3-DM-002,
        REQ-L3-DM-003, REQ-L3-DM-004

External interfaces:
  IF-L1-032 (input):  ApplicationService triggers create/update/get/list
  IF-L1-035 (output): Diagram + DiagramVersion entities → PersistenceLayer
  IF-L1-036 (output): Audit log entries → AuditLog
  IF-DS-INT-001:      DiagramManager → DiagramValidator
  IF-DS-INT-002:      DiagramManager → DiagramRenderer
  IF-DS-INT-003:      DiagramManager → TraceabilityConnector

Coordinates CRUD operations on Diagram artefacts.  Every content-changing
operation produces a new immutable DiagramVersion (REQ-L2-DS-001).  The
DiagramVersion history is never modified after creation.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Optional

from audit.services import log_write
from persistence.transactions import atomic_transaction

from diagram.models import Diagram, DiagramVersion, DiagramType, PayloadFormat
from diagram.renderer import DiagramRenderer, RenderableDiagram
from diagram.traceability_connector import TraceabilityConnector
from diagram.validator import DiagramValidator, DiagramValidationError  # noqa: F401 re-export


# ---------------------------------------------------------------------------
# Canonical serialization (GH-353 Task 1)
# ---------------------------------------------------------------------------

def _canonicalize_payload(payload_format: str, content: str) -> str:
    """Canonicalize a ``node_graph`` payload for stable, diffable storage.

    Every write path that can persist ``payload_format=node_graph`` (REST
    ``POST``/``PATCH /api/v1/diagrams/`` and the MCP ``diagram.*`` tools)
    funnels through :meth:`DiagramManager.create_diagram` /
    :meth:`DiagramManager.update_diagram` — this is the single shared choke
    point, so canonicalization lives here rather than being duplicated in
    each transport layer.

    Re-serializes with ``sort_keys=True`` and stable indentation so that two
    semantically-identical payloads with differently-ordered keys persist as
    byte-identical text, keeping ``GET /diagrams/<id>/diff/`` empty between
    otherwise-unchanged saves.

    MUST run AFTER :meth:`DiagramValidator.validate_payload` has already
    succeeded for *content* — canonicalizing invalid JSON is undefined.
    No-op for every other ``payload_format`` (Mermaid/PlantUML/JSON/
    canvas_stroke keep their existing raw-string persistence behaviour).

    Args:
        payload_format: One of PayloadFormat values.
        content:        The already-validated raw payload string.

    Returns:
        The canonicalized payload string for ``node_graph``; *content*
        unchanged for every other format.
    """
    if payload_format != PayloadFormat.NODE_GRAPH:
        return content
    return json.dumps(json.loads(content), ensure_ascii=False, sort_keys=True, indent=2)


# ---------------------------------------------------------------------------
# Data contracts (public surface of DiagramManager)
# ---------------------------------------------------------------------------

@dataclass
class DiagramResult:
    """Return type for get_diagram — bundles header, version and render data."""

    diagram: Diagram
    version: Optional[DiagramVersion]
    renderable: Optional[RenderableDiagram]


# ---------------------------------------------------------------------------
# DiagramManager — COMP-DS-001
# ---------------------------------------------------------------------------

class DiagramManager:
    """COMP-DS-001: Central coordinator for Diagram CRUD and versioning.

    req_id: REQ-L2-DS-001
    leaf_id: COMP-DS-001_DiagramManager

    Wires together DiagramValidator (COMP-DS-002), DiagramRenderer (COMP-DS-003)
    and TraceabilityConnector (COMP-DS-004) via the registered internal interfaces.

    All write paths run inside atomic_transaction (persistence.transactions).
    Audit entries are written inside the same transaction (IF-L1-036).
    """

    def __init__(
        self,
        validator: Optional[DiagramValidator] = None,
        renderer: Optional[DiagramRenderer] = None,
        traceability: Optional[TraceabilityConnector] = None,
    ) -> None:
        self._validator = validator or DiagramValidator()
        self._renderer = renderer or DiagramRenderer()
        self._traceability = traceability or TraceabilityConnector()

    # ------------------------------------------------------------------
    # IF-L1-032: create_diagram
    # REQ-L3-DM-001
    # ------------------------------------------------------------------

    @atomic_transaction
    def create_diagram(
        self,
        *,
        name: str,
        diagram_type: str,
        payload_format: str,
        content: str,
        tenant: object,
        description: str = "",
        created_by: Optional[object] = None,
        target_id: Optional[uuid.UUID] = None,
        canvas_json: Optional[dict] = None,
        workspace_id: Optional[uuid.UUID] = None,
    ) -> Diagram:
        """Create a new Diagram and its initial DiagramVersion (v1).

        REQ-L3-DM-001 acceptance criteria:
          - Payload is validated before persistence (IF-DS-INT-001).
          - Creates Diagram entity and DiagramVersion v1 (IF-L1-035).
          - Returns the UUID of the created Diagram.
          - Writes audit log entry (IF-L1-036).
          - Optionally creates a 'documents' TraceLink if target_id is given
            (IF-DS-INT-003 / REQ-L2-DS-004).

        Args:
            name:           Human-readable diagram name.
            diagram_type:   One of DiagramType values (block/flow/context).
            payload_format: One of PayloadFormat values (mermaid/plantuml/json).
            content:        Raw diagram payload (Mermaid string etc.).
            tenant:         Active Tenant ORM object (TenantScopedModel requirement).
            description:    Optional free-text description.
            created_by:     Optional User ORM object for audit.
            target_id:      Optional UUID of a target Artifact for TraceLink creation.
            workspace_id:   Optional owning workspace UUID (REQ-173). Nullable for
                            backwards compatibility; new diagrams should set it.

        Returns:
            The newly created Diagram ORM object.

        Raises:
            DiagramValidationError: If the payload fails validation.
        """
        # IF-DS-INT-001: validate before any persistence
        self._validator.validate_payload(diagram_type, payload_format, content)

        # GH-353 (Task 1): canonicalize node_graph payloads post-validation,
        # pre-persistence — no-op for every other payload_format.
        content = _canonicalize_payload(payload_format, content)

        # IF-L1-035: persist Diagram header (current_version set after version exists)
        diagram = Diagram.objects.create(
            name=name,
            diagram_type=diagram_type,
            description=description,
            tenant=tenant,
            created_by=created_by,
            modified_by=created_by,
            workspace_id=workspace_id,
        )

        # IF-L1-035: persist initial immutable version
        version = DiagramVersion.objects.create(
            diagram=diagram,
            version_number=1,
            payload_format=payload_format,
            payload=content,
            canvas_json=canvas_json,
            tenant=tenant,
            created_by=created_by,
            modified_by=created_by,
        )

        # Update current_version pointer
        diagram.current_version = version
        diagram.save(update_fields=["current_version", "modified_at"])

        # IF-L1-036: audit log entry for create
        log_write(
            actor=str(created_by.id) if created_by else "system",
            actor_type="user",
            operation="create",
            entity_type="Diagram",
            entity_id=diagram.id,
            version=version.version_number,
        )

        # IF-DS-INT-003 / IF-L1-034: optional TraceLink creation
        if target_id is not None:
            self._traceability.create_document_link(
                diagram_id=diagram.id,
                target_id=target_id,
                created_by_id=created_by.id if created_by else None,
            )

        return diagram

    # ------------------------------------------------------------------
    # IF-L1-032: update_diagram
    # REQ-L3-DM-002
    # ------------------------------------------------------------------

    @atomic_transaction
    def update_diagram(
        self,
        *,
        diagram_id: uuid.UUID,
        payload_format: str,
        content: str,
        modified_by: Optional[object] = None,
        target_id: Optional[uuid.UUID] = None,
        canvas_json: Optional[dict] = None,
    ) -> DiagramVersion:
        """Create a new DiagramVersion (N+1); old versions remain unchanged.

        REQ-L3-DM-002 acceptance criteria:
          - New version created only if payload is valid (IF-DS-INT-001).
          - Existing versions remain unmodified.
          - Audit log entry written (IF-L1-036).

        Args:
            diagram_id:     UUID of the Diagram to update.
            payload_format: New payload format.
            content:        New raw payload string.
            modified_by:    Optional User ORM object for audit.
            target_id:      Optional UUID for additional TraceLink.

        Returns:
            The newly created DiagramVersion ORM object.

        Raises:
            Diagram.DoesNotExist:  If diagram_id is not found.
            DiagramValidationError: If the new payload fails validation.
        """
        diagram = Diagram.objects.get(id=diagram_id)

        # IF-DS-INT-001: validate new payload before persistence
        self._validator.validate_payload(diagram.diagram_type, payload_format, content)

        # GH-353 (Task 1): canonicalize node_graph payloads post-validation,
        # pre-persistence — no-op for every other payload_format.
        content = _canonicalize_payload(payload_format, content)

        # Determine next version number — find current max
        last_version = (
            DiagramVersion.unscoped
            .filter(diagram=diagram)
            .order_by("-version_number")
            .first()
        )
        next_number = (last_version.version_number + 1) if last_version else 1

        # IF-L1-035: persist new immutable version
        new_version = DiagramVersion.objects.create(
            diagram=diagram,
            version_number=next_number,
            payload_format=payload_format,
            payload=content,
            canvas_json=canvas_json,
            tenant=diagram.tenant,
            created_by=modified_by,
            modified_by=modified_by,
        )

        # Update current_version pointer on header
        diagram.current_version = new_version
        diagram.modified_by = modified_by
        diagram.save(update_fields=["current_version", "modified_by", "modified_at"])

        # IF-L1-036: audit log
        log_write(
            actor=str(modified_by.id) if modified_by else "system",
            actor_type="user",
            operation="update",
            entity_type="Diagram",
            entity_id=diagram.id,
            version=new_version.version_number,
        )

        # IF-DS-INT-003 / IF-L1-034: optional additional TraceLink
        if target_id is not None:
            self._traceability.create_document_link(
                diagram_id=diagram.id,
                target_id=target_id,
                created_by_id=modified_by.id if modified_by else None,
            )

        return new_version

    # ------------------------------------------------------------------
    # IF-L1-032: get_diagram
    # REQ-L3-DM-003
    # ------------------------------------------------------------------

    def get_diagram(
        self,
        diagram_id: uuid.UUID,
        version_number: Optional[int] = None,
    ) -> DiagramResult:
        """Retrieve a Diagram and enrich it with render information.

        REQ-L3-DM-003 acceptance criteria:
          - Diagram is read from PersistenceLayer (IF-L1-035).
          - DiagramRenderer is called to enrich payload (IF-DS-INT-002).

        Args:
            diagram_id:     UUID of the diagram to retrieve.
            version_number: Optional specific version to retrieve.
                            Defaults to current_version.

        Returns:
            DiagramResult with diagram, version and renderable fields.

        Raises:
            Diagram.DoesNotExist: If diagram_id not found, or if it has been
                soft-deleted (outdated) via ``delete_diagram``. Diagram has no
                denormalized status mirror field (see
                ``diagram.services.delete_diagram`` docstring) — soft-deleted
                rows are excluded via ``workflow.services.outdated_item_ids``
                instead of a ``lifecycle_status`` filter, mirroring
                ``diagram.services.list_diagrams``.
            DiagramVersion.DoesNotExist: If version_number not found.
        """
        from workflow.services import outdated_item_ids

        diagram = (
            Diagram.objects.select_related("current_version")
            .exclude(id__in=outdated_item_ids("Diagram"))
            .get(id=diagram_id)
        )

        if version_number is not None:
            version = DiagramVersion.unscoped.get(
                diagram=diagram,
                version_number=version_number,
            )
        else:
            version = diagram.current_version

        renderable = None
        if version is not None:
            # IF-DS-INT-002: enrich with render information
            renderable = self._renderer.prepare_renderable(
                diagram_type=diagram.diagram_type,
                payload_format=version.payload_format,
                content=version.payload,
            )

        return DiagramResult(
            diagram=diagram,
            version=version,
            renderable=renderable,
        )

    # ------------------------------------------------------------------
    # IF-L1-032: list_versions
    # REQ-L3-DM-004
    # ------------------------------------------------------------------

    def list_versions(
        self,
        diagram_id: uuid.UUID,
    ) -> list[DiagramVersion]:
        """Return all DiagramVersions for a Diagram, chronologically.

        REQ-L3-DM-004 acceptance criteria:
          - List includes version_number, created_at, created_by.

        Args:
            diagram_id: UUID of the parent Diagram.

        Returns:
            List of DiagramVersion objects sorted ascending by version_number.

        Raises:
            Diagram.DoesNotExist: If diagram_id not found.
        """
        # Verify the diagram is accessible within the active tenant context.
        Diagram.objects.get(id=diagram_id)

        return list(
            DiagramVersion.unscoped
            .filter(diagram_id=diagram_id)
            .select_related("created_by")
            .order_by("version_number")
        )


__all__ = [
    "DiagramManager",
    "DiagramResult",
    "DiagramValidationError",
]
