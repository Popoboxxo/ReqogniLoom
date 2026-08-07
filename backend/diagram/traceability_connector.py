"""
ARCH-L1-013 DiagramService — Traceability connector.

leaf_id: COMP-DS-004_TraceabilityConnector
req_id: REQ-L1-027, REQ-L2-DS-004, REQ-L3-TC-001

Internal interface:
  IF-DS-INT-003: create_document_link(diagram_id, target_id, created_by_id) -> TraceLink

External interface (outgoing):
  IF-L1-034: creates a TraceLink of link_type='documents' via
             traceability.services.create_trace_link

Links a Diagram's shadow-Artifact to a target artifact (Requirement or
ArchitectureElement) using the TraceabilityEngine (ARCH-L1-007) with
link_type='documents' (LinkType.DOCUMENTS).

Shadow-Artifact pattern (Codeberg #353 Task 3, closes #392):
  Diagram entities do not inherit from persistence.models.Artifact — they
  remain a standalone domain entity in the DiagramService module (bounded
  context, unchanged by this fix). What changed: a Diagram's *raw* UUID is no
  longer used directly as a TraceLink source_id. TraceLinkManager.create looks
  up the source via ``Artifact.unscoped.get(pk=source_id)`` — a bare
  ``diagram.id`` never resolves there, so every "documents" link creation
  raised SourceNotFoundError (#392). Diagram now owns an optional, lazily-
  created 1:1 ``Diagram.artifact`` side-channel FK (persistence/models.py via
  diagram/models.py, migration 0007) to a *real*, persisted Artifact row.
  ``_resolve_artifact_id`` is the single choke point that creates/looks up
  that shadow Artifact; both this module's own "documents" link path and the
  Task 4 "diagram-ref" reconciler call it, so the fix lives in exactly one
  place.
"""
from __future__ import annotations

import uuid
from typing import Optional

from diagram.models import Diagram
from persistence.models import Artifact
from traceability.services import create_trace_link
from traceability.exceptions import TraceLinkError


# ---------------------------------------------------------------------------
# Shadow-Artifact resolution (Codeberg #353 Task 3 / #392)
# ---------------------------------------------------------------------------

def _resolve_artifact_id(diagram: Diagram) -> uuid.UUID:
    """Resolve the shadow Artifact id backing *diagram*, creating it lazily.

    Idempotent: if ``diagram.artifact_id`` is already set, it is returned
    unchanged — no second shadow Artifact is ever created for the same
    Diagram.

    Concurrency-safety (code review round 1, Codeberg #353 Task 3): a plain
    read-then-write here is a TOCTOU race — two concurrent callers (e.g. two
    MCP ``diagram.create``/``update`` requests referencing the same
    pre-existing Diagram) could both observe ``artifact_id is None`` and both
    ``INSERT`` a shadow Artifact, orphaning one of them. There is no unique
    constraint that would reject the second Artifact (``Diagram.artifact``'s
    OneToOneField index only prevents two *Diagrams* sharing one Artifact, it
    does not limit how many Artifacts a Diagram can be pointed at over
    successive writes). To close this, the *fast-path* check above is only a
    cheap optimization for the already-resolved case; whenever it is
    ambiguous we re-fetch the row via ``select_for_update()`` so a second,
    concurrent caller blocks on the row lock until the first caller's
    transaction commits (or rolls back) — at which point it observes the
    now-set ``artifact_id`` and returns it instead of creating a duplicate.

    Transaction-safety: performs a write (Artifact creation + Diagram save)
    but never opens its own transaction. It must be called from inside the
    caller's existing atomic block (DiagramManager's write paths are already
    wrapped in ``@atomic_transaction`` — persistence.transactions) so that a
    rollback of the outer operation also rolls back the shadow Artifact.
    ``select_for_update()`` itself requires an active transaction (Django
    raises ``TransactionManagementError`` otherwise), which doubles as a
    guard against this function ever being called outside one.

    Args:
        diagram: The Diagram ORM instance to resolve/attach a shadow
            Artifact for.

    Returns:
        The UUID of the (possibly newly-created) shadow Artifact.

    Raises:
        TraceLinkError: If the diagram has no ``workspace_id`` set. An
            Artifact row requires a non-null ``workspace`` FK
            (persistence.models.Artifact), so a Diagram must first be
            assigned to a workspace (REQ-173) before it can back a TraceLink.
    """
    if diagram.artifact_id is not None:
        return diagram.artifact_id

    # Ambiguous fast-path: re-fetch under a row lock so a concurrent caller
    # racing us here blocks instead of also creating a shadow Artifact.
    locked_diagram = Diagram.objects.select_for_update().get(pk=diagram.pk)

    if locked_diagram.artifact_id is not None:
        # Another caller created it while we were waiting for the lock.
        diagram.artifact_id = locked_diagram.artifact_id
        return locked_diagram.artifact_id

    if locked_diagram.workspace_id is None:
        raise TraceLinkError(
            f"Diagram {locked_diagram.id} has no workspace_id; a Diagram "
            "must be assigned to a workspace before it can back a TraceLink."
        )

    artifact = Artifact.objects.create(
        artifact_type="Diagram",
        tenant=locked_diagram.tenant,
        workspace_id=locked_diagram.workspace_id,
    )
    locked_diagram.artifact = artifact
    locked_diagram.save(update_fields=["artifact", "modified_at"])
    diagram.artifact = artifact
    return artifact.id


# ---------------------------------------------------------------------------
# Public interface — IF-DS-INT-003 / IF-L1-034
# ---------------------------------------------------------------------------

class TraceabilityConnector:
    """COMP-DS-004: Creates 'documents' TraceLinks via the TraceabilityEngine.

    req_id: REQ-L2-DS-004, REQ-L3-TC-001
    leaf_id: COMP-DS-004_TraceabilityConnector

    Called exclusively by DiagramManager (COMP-DS-001) via IF-DS-INT-003.
    Delegates to traceability.services.create_trace_link (IF-L1-034).
    """

    LINK_TYPE: str = "documents"

    def create_document_link(
        self,
        diagram_id: uuid.UUID,
        target_id: uuid.UUID,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> object:
        """Create a 'documents' TraceLink between a diagram and a target artifact.

        IF-DS-INT-003 contract: create_document_link(diagram_id, target_id)

        #392 fix: resolves *diagram_id* to its shadow Artifact id via
        ``_resolve_artifact_id`` before delegating to the TraceabilityEngine,
        instead of passing the raw Diagram UUID as source_id.

        Args:
            diagram_id:     UUID of the Diagram (source side).
            target_id:      UUID of the target Artifact (Requirement or
                            ArchitectureElement).
            created_by_id:  Optional actor UUID for audit metadata.

        Returns:
            The created TraceLink ORM object (from TraceabilityEngine).

        Raises:
            Diagram.DoesNotExist: If diagram_id does not resolve to a Diagram
                                  in the active tenant.
            TraceLinkError:       If TraceabilityEngine rejects the link
                                  (e.g. target not found, cross-tenant, cycle),
                                  or if the Diagram has no workspace assigned.
                                  REQ-L3-TC-001: errors propagated transparently.
        """
        diagram = Diagram.objects.get(id=diagram_id)
        resolved_source_id = _resolve_artifact_id(diagram)

        # IF-L1-034: delegate to TraceabilityEngine public facade
        return create_trace_link(
            source_id=resolved_source_id,
            target_id=target_id,
            link_type=self.LINK_TYPE,
            created_by_id=created_by_id,
        )


__all__ = [
    "TraceabilityConnector",
    "_resolve_artifact_id",
]
