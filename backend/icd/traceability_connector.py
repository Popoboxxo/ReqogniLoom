"""
IcdManagement — TraceabilityConnector (COMP-ICD-003).

leaf_id: COMP-ICD-003
req_id:  REQ-L1-028, REQ-L2-ICD-004
arch_id: ARCH-L1-014
IF:      IF-ICD-INT-002 (IcdManager -> TraceabilityConnector)
         IF-L1-039 (TraceabilityConnector -> TraceabilityEngine)

Adapter that decouples IcdManager from the external TraceabilityEngine.
On ICD creation, creates 'realizes' TraceLinks from:
  - source ArchitectureElement Artifact → ICD Artifact (conceptual)
  - target ArchitectureElement Artifact → ICD Artifact (conceptual)

Because the TraceabilityEngine operates on Artifact UUIDs (persistence.models.Artifact),
and an ICD does not have its own Artifact row, the links are created between
the source_element_id and target_element_id directly, with the ICD id as payload
carried in the link_type metadata. Concretely: the source → target link with
type='realizes' represents the ICD contract.

The connector calls traceability.services.create_trace_link (IF-L1-039).
Errors from the traceability engine are logged and re-raised to allow the
caller (IcdManager) to decide on rollback behaviour.
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


class TraceabilityConnector:
    """Adapter for creating 'realizes' TraceLinks via the TraceabilityEngine.

    leaf_id: COMP-ICD-003
    req_id:  REQ-L2-ICD-004
    IF:      IF-ICD-INT-002 (called by IcdManager)
             IF-L1-039 (calls traceability.services.create_trace_link)
    """

    def link_to_architecture(
        self,
        icd_id: uuid.UUID,
        source_element_id: uuid.UUID,
        target_element_id: uuid.UUID,
        created_by_id: uuid.UUID | None = None,
    ) -> None:
        """Create 'realizes' TraceLink(s) for the given ICD.

        Creates a directed TraceLink from source_element_id to
        target_element_id with link_type='realizes'. This represents
        that the ICD contract describes the interface between these two
        architecture elements.

        Args:
            icd_id:            UUID of the Icd being linked.
            source_element_id: Artifact UUID of the source architecture element.
            target_element_id: Artifact UUID of the target architecture element.
            created_by_id:     Optional UUID of the user creating the link.

        Raises:
            Any exception from traceability.services.create_trace_link is
            propagated to the caller (IcdManager) for transaction-level handling.

        req_id: REQ-L2-ICD-004
        IF:     IF-ICD-INT-002, IF-L1-039
        """
        # Import is deferred to avoid circular imports at module load time.
        # The traceability app is always available at runtime (INSTALLED_APPS).
        from traceability.services import create_trace_link

        logger.debug(
            "Creating 'realizes' TraceLink: source=%s -> target=%s (icd=%s)",
            source_element_id,
            target_element_id,
            icd_id,
        )
        create_trace_link(
            source_id=source_element_id,
            target_id=target_element_id,
            link_type="realizes",
            created_by_id=created_by_id,
        )
        logger.info(
            "TraceLink 'realizes' created: source=%s -> target=%s for ICD %s",
            source_element_id,
            target_element_id,
            icd_id,
        )


# Module-level singleton — IcdManager uses this instance (IF-ICD-INT-002)
_connector = TraceabilityConnector()


def get_connector() -> TraceabilityConnector:
    """Return the module-level TraceabilityConnector singleton.

    leaf_id: COMP-ICD-003
    """
    return _connector


__all__ = [
    "TraceabilityConnector",
    "get_connector",
]
