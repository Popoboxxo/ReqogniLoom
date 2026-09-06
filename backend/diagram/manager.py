"""
ARCH-L1-013 DiagramService — DiagramManager (central coordinator).

leaf_id: COMP-DS-001_DiagramManager
req_id: REQ-L1-027, REQ-L2-DS-001, REQ-L3-DM-001, REQ-L3-DM-002,
        REQ-L3-DM-003, REQ-L3-DM-004

External interfaces:
  IF-L1-032 (input):  ApplicationService triggers create/update/get/list
  IF-L1-035 (output): Diagram entities → PersistenceLayer
  IF-L1-036 (output): Audit log entries → AuditLog
  IF-DS-INT-001:      DiagramManager → DiagramValidator
  IF-DS-INT-002:      DiagramManager → DiagramRenderer
  IF-DS-INT-003:      DiagramManager → TraceabilityConnector

Coordinates CRUD operations on Diagram artefacts. Every content-changing
operation overwrites the Diagram's payload and appends an immutable snapshot
of it to ``persistence.ArtifactVersion`` (REQ-L2-DS-001). Recorded revisions
are never modified after creation.

Datenmodell-Konsolidierung Task 28c-2 retired the ``DiagramVersion`` table;
:class:`diagram.models.DiagramRevision` is the read model those snapshots are
rehydrated into.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Optional

from audit.services import log_write
from persistence.artifact_backing import ensure_artifact
from persistence.models import ArtifactVersion
from persistence.transactions import atomic_transaction

from diagram.models import Diagram, DiagramRevision, DiagramType, PayloadFormat
from diagram.renderer import DiagramRenderer, RenderableDiagram
from diagram.traceability_connector import TraceabilityConnector, sync_node_links
from diagram.validator import DiagramValidator, DiagramValidationError  # noqa: F401 re-export


class DiagramRevisionNotFoundError(LookupError):
    """No recorded content revision exists under the requested number.

    Task 28c-2 replacement for ``DiagramVersion.DoesNotExist``, which callers
    used to catch when asking ``get_diagram`` for a historical version.
    Subclasses ``LookupError`` so ``except LookupError`` keeps catching it.
    """


#: Content columns a write touches on ``Diagram``, plus the audit columns
#: ``AuditableModel.save`` maintains. Named once so create and update cannot
#: drift apart in what they persist.
_CONTENT_UPDATE_FIELDS = [
    "payload_format",
    "payload",
    "canvas_json",
    "current_revision",
    "modified_at",
]


# ---------------------------------------------------------------------------
# Content history (Datenmodell-Konsolidierung Phase 5, spec section 6.1)
# ---------------------------------------------------------------------------

def _record_artifact_revision(diagram: Diagram) -> int:
    """Append the ``ArtifactVersion`` snapshot of *diagram*'s current content.

    Writes the row directly instead of calling
    ``application.artifact_version_service.ArtifactVersionService``: this module
    is Layer 1/Ext and must not import Layer 2 (ADR-01, single entry point).

    The revision number is allocated as ``current_revision + 1`` while holding
    a row lock on the Diagram, the same discipline
    ``ArtifactVersionService.record`` uses on the Artifact row, so two
    concurrent writers cannot allocate the same number and collide on
    ``uq_artifact_version_revision``.

    The counter is advanced either way, but the snapshot is skipped for a
    workspace-less legacy Diagram: ``Artifact.workspace`` is not nullable, so
    such a row cannot have a backing Artifact to hang the revision on (the same
    limitation ``create_diagram`` already documents, and the same rows Task 28a
    could not copy history for). Its current content still lives on the row
    itself; only its *history* is unavailable.

    Args:
        diagram: The Diagram, already carrying the content to snapshot.

    Returns:
        The newly allocated revision number.

    Must run inside the caller's transaction so the snapshot rolls back with
    the content it describes.
    """
    if diagram.artifact_id is None and diagram.workspace_id is not None:
        # Idempotent no-op when the backing already exists; this call only
        # fires for pre-Phase-3 diagrams, which would otherwise never start
        # a history at all.
        ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )

    # The lock is on the row whose counter is being incremented. update_diagram
    # holds no lock of its own, so this is where concurrent writers serialise.
    locked_revision = (
        Diagram.unscoped.select_for_update()
        .filter(pk=diagram.pk)
        .values_list("current_revision", flat=True)
        .first()
    )
    revision = (locked_revision or 0) + 1
    diagram.current_revision = revision

    if diagram.artifact_id is not None:
        ArtifactVersion.objects.create(
            tenant=diagram.tenant,
            artifact_id=diagram.artifact_id,
            revision=revision,
            payload={
                "payload_format": diagram.payload_format,
                "payload": diagram.payload,
                "canvas_json": diagram.canvas_json,
            },
        )
    return revision


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
# Per-node artifact_ref trace-link reconciliation (GH-353 Task 4)
# ---------------------------------------------------------------------------

def _sync_node_graph_links(
    diagram: Diagram,
    payload_format: str,
    content: str,
    created_by_id: Optional[uuid.UUID],
) -> None:
    """Reconcile ``LinkType.DIAGRAM_REF`` TraceLinks for a node_graph save.

    Runs in the same write path Task 1 wired canonicalization into (this is
    the single choke point both create_diagram and update_diagram share for
    ``payload_format=node_graph``), so canonicalization and reconciliation
    always run together on every node_graph create/update. No-op for every
    other ``payload_format`` — mirrors :func:`_canonicalize_payload`.

    MUST run AFTER the Diagram row for this write has been persisted (``sync_node_links`` needs ``diagram.tenant_id`` and, for
    Diagrams that already have refs, the shadow Artifact) and inside the same
    ``@atomic_transaction`` as the rest of the write, so an aborted
    reconciliation rolls back the whole save.

    Args:
        diagram:        The just-created/updated Diagram (current call's
                         tenant/workspace already set).
        payload_format: One of PayloadFormat values.
        content:        The already-canonicalized payload string.
        created_by_id:  Optional actor UUID for audit metadata on new links.

    Raises:
        DiagramValidationError: An artifact_ref does not resolve — see
            diagram.traceability_connector.sync_node_links.
    """
    if payload_format != PayloadFormat.NODE_GRAPH:
        return
    sync_node_links(
        diagram=diagram,
        node_graph_payload=json.loads(content),
        created_by_id=created_by_id,
    )


# ---------------------------------------------------------------------------
# Data contracts (public surface of DiagramManager)
# ---------------------------------------------------------------------------

@dataclass
class DiagramResult:
    """Return type for get_diagram — bundles the row, a revision and render data."""

    diagram: Diagram
    version: Optional[DiagramRevision]
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
        """Create a new Diagram with its content at revision 1.

        REQ-L3-DM-001 acceptance criteria:
          - Payload is validated before persistence (IF-DS-INT-001).
          - Creates the Diagram entity and records revision 1 (IF-L1-035).
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

        # IF-L1-035: persist the Diagram row, content included.
        diagram = Diagram.objects.create(
            name=name,
            diagram_type=diagram_type,
            description=description,
            tenant=tenant,
            created_by=created_by,
            modified_by=created_by,
            workspace_id=workspace_id,
            payload_format=payload_format,
            payload=content,
            canvas_json=canvas_json,
        )

        # Datenmodell-Konsolidierung Phase 3 (spec §4.3): create the backing
        # Artifact up front instead of lazily on first TraceLink use, so a
        # Diagram is a valid link endpoint and baseline subject from birth.
        # Skipped for the workspace-less legacy shape (workspace_id is
        # nullable, REQ-173) — those rows keep the pre-existing behaviour of
        # raising only when a link is actually attempted.
        if workspace_id is not None:
            ensure_artifact(
                diagram, artifact_type="Diagram", workspace_id=workspace_id
            )

        # Datenmodell-Konsolidierung Phase 5 (spec §6.1): record revision 1 in
        # the shared revision store and advance the row's counter.
        _record_artifact_revision(diagram)
        diagram.save(update_fields=["current_revision", "modified_at"])
        version = DiagramRevision.from_diagram(diagram)

        # IF-L1-036: audit log entry for create
        log_write(
            actor=str(created_by.id) if created_by else "system",
            actor_type="user",
            operation="create",
            entity_type="Diagram",
            entity_id=diagram.id,
            version=version.version_number,
        )

        # GH-353 Task 4: reconcile per-node DIAGRAM_REF TraceLinks — no-op
        # for every payload_format other than node_graph.
        _sync_node_graph_links(
            diagram=diagram,
            payload_format=payload_format,
            content=content,
            created_by_id=created_by.id if created_by else None,
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
    ) -> DiagramRevision:
        """Record content revision N+1; recorded revisions remain unchanged.

        REQ-L3-DM-002 acceptance criteria:
          - New revision recorded only if payload is valid (IF-DS-INT-001).
          - Existing revisions remain unmodified.
          - Audit log entry written (IF-L1-036).

        Args:
            diagram_id:     UUID of the Diagram to update.
            payload_format: New payload format.
            content:        New raw payload string.
            modified_by:    Optional User ORM object for audit.
            target_id:      Optional UUID for additional TraceLink.

        Returns:
            The newly recorded DiagramRevision.

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

        # IF-L1-035: overwrite the content in place — the Diagram row IS the
        # current content since Task 28c-2; history is the ArtifactVersion
        # trail appended below.
        diagram.payload_format = payload_format
        diagram.payload = content
        diagram.canvas_json = canvas_json
        diagram.modified_by = modified_by

        # Datenmodell-Konsolidierung Phase 5 (spec §6.1): record vN in the
        # shared revision store and advance the row's counter.
        _record_artifact_revision(diagram)
        diagram.save(update_fields=[*_CONTENT_UPDATE_FIELDS, "modified_by"])
        new_version = DiagramRevision.from_diagram(diagram)

        # IF-L1-036: audit log
        log_write(
            actor=str(modified_by.id) if modified_by else "system",
            actor_type="user",
            operation="update",
            entity_type="Diagram",
            entity_id=diagram.id,
            version=new_version.version_number,
        )

        # GH-353 Task 4: reconcile per-node DIAGRAM_REF TraceLinks — no-op
        # for every payload_format other than node_graph.
        _sync_node_graph_links(
            diagram=diagram,
            payload_format=payload_format,
            content=content,
            created_by_id=modified_by.id if modified_by else None,
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
            version_number: Optional specific revision to retrieve.
                            Defaults to the current one.

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
            DiagramRevisionNotFoundError: If version_number has no recorded
                snapshot.
        """
        from workflow.services import outdated_item_ids

        diagram = Diagram.objects.exclude(
            id__in=outdated_item_ids("Diagram")
        ).get(id=diagram_id)

        if version_number is not None and version_number != diagram.current_revision:
            version = self._resolve_revision(diagram, version_number)
        elif diagram.current_revision:
            version = DiagramRevision.from_diagram(diagram)
        else:
            version = None

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
    ) -> list[DiagramRevision]:
        """Return all recorded content revisions of a Diagram, chronologically.

        REQ-L3-DM-004 acceptance criteria:
          - List includes version_number and created_at.

        Args:
            diagram_id: UUID of the Diagram.

        Returns:
            List of DiagramRevision objects sorted ascending by version_number.

        Raises:
            Diagram.DoesNotExist: If diagram_id not found.
        """
        # Verify the diagram is accessible within the active tenant context.
        diagram = Diagram.objects.get(id=diagram_id)
        if diagram.artifact_id is None:
            # Workspace-less legacy row: no backing Artifact, so no recorded
            # history. Its current content is all there is.
            return (
                [DiagramRevision.from_diagram(diagram)]
                if diagram.current_revision
                else []
            )

        return [
            DiagramRevision.from_payload(
                diagram_id=diagram_id,
                revision=row.revision,
                payload=row.payload or {},
                created_at=row.created_at,
            )
            for row in ArtifactVersion.unscoped.filter(
                artifact_id=diagram.artifact_id, tenant_id=diagram.tenant_id
            ).order_by("revision")
        ]

    @staticmethod
    def _resolve_revision(
        diagram: Diagram, version_number: int
    ) -> DiagramRevision:
        """Return the recorded snapshot for *version_number*.

        Raises:
            DiagramRevisionNotFoundError: No snapshot stored under that number.
        """
        row = (
            ArtifactVersion.unscoped.filter(
                artifact_id=diagram.artifact_id,
                tenant_id=diagram.tenant_id,
                revision=version_number,
            ).first()
            if diagram.artifact_id is not None
            else None
        )
        if row is None:
            raise DiagramRevisionNotFoundError(
                f"Revision {version_number} not found for diagram {diagram.pk}"
            )
        return DiagramRevision.from_payload(
            diagram_id=diagram.pk,
            revision=row.revision,
            payload=row.payload or {},
            created_at=row.created_at,
        )


__all__ = [
    "DiagramManager",
    "DiagramResult",
    "DiagramRevisionNotFoundError",
    "DiagramValidationError",
]
