"""
ARCH-L1-013 DiagramService — Traceability connector.

leaf_id: COMP-DS-004_TraceabilityConnector
req_id: REQ-L1-027, REQ-L2-DS-004, REQ-L3-TC-001

Internal interface:
  IF-DS-INT-003: create_document_link(diagram_id, target_id, created_by_id) -> TraceLink

External interface (outgoing):
  IF-L1-034: creates a TraceLink of link_type='documents' via
             traceability.services.create_trace_link

Links a Diagram's artifact-proxy UUID to a target artifact (Requirement or
ArchitectureElement) using the TraceabilityEngine (ARCH-L1-007) with
link_type='documents' (LinkType.DOCUMENTS).

Note on artifact-proxy pattern:
  Diagram entities do not inherit from persistence.models.Artifact because they
  are a standalone domain entity in the DiagramService module.  For traceability
  purposes the Diagram's own UUID (diagram.id) is passed as the source_id.
  The TraceabilityEngine stores this UUID in TraceLink.source and the
  PersistenceLayer's RLS/foreign-key constraints do not enforce referential
  integrity across application-layer entities — only persistence.Artifact rows
  carry the FK constraint.  This is the accepted trade-off for the DiagramService
  module (bounded context); a proper Artifact proxy can be introduced via a
  migration in a future iteration without changing this interface.
"""
from __future__ import annotations

import uuid
from typing import Optional

from traceability.services import create_trace_link
from traceability.exceptions import TraceLinkError


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

        Args:
            diagram_id:     UUID of the Diagram (source side).
            target_id:      UUID of the target Artifact (Requirement or
                            ArchitectureElement).
            created_by_id:  Optional actor UUID for audit metadata.

        Returns:
            The created TraceLink ORM object (from TraceabilityEngine).

        Raises:
            TraceLinkError:       If TraceabilityEngine rejects the link
                                  (e.g. target not found, cross-tenant, cycle).
                                  REQ-L3-TC-001: errors propagated transparently.
        """
        # IF-L1-034: delegate to TraceabilityEngine public facade
        return create_trace_link(
            source_id=diagram_id,
            target_id=target_id,
            link_type=self.LINK_TYPE,
            created_by_id=created_by_id,
        )


__all__ = [
    "TraceabilityConnector",
]
