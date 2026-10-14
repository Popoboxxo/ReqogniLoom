"""
IcdManagement — TraceabilityConnector (COMP-ICD-003).

leaf_id: COMP-ICD-003
req_id:  REQ-L1-028, REQ-L2-ICD-004
arch_id: ARCH-L1-014
IF:      IF-ICD-INT-002 (IcdManager -> TraceabilityConnector)
         IF-L1-039 (TraceabilityConnector -> TraceabilityEngine)

Adapter that decouples IcdManager from the external TraceabilityEngine.
On ICD creation, creates 'decomposes' TraceLinks from:
  - source ArchitectureElement Artifact → ICD Artifact (conceptual)
  - target ArchitectureElement Artifact → ICD Artifact (conceptual)

Because the TraceabilityEngine operates on Artifact UUIDs (persistence.models.Artifact),
and the ICD does have its own backing Artifact row
(``persistence.artifact_backing.ensure_artifact``), the links are created
between the source_element_id and target_element_id directly, with the ICD id as
payload carried in the link_type metadata. Concretely: the source → target link
with type='decomposes' represents the ICD contract. (This link type was spelled
using the retired realizes key until the link-type consolidation folded that
key into 'decomposes' — see link_types.builtin.LEGACY_LINK_TYPE_MAPPING. Both
endpoints are ArchitectureElements, which 'decomposes' allows.)

#1268 — interface anchoring
---------------------------------
The 'decomposes' link above connects the two architecture elements to each
other; it does NOT connect the ICD to either of them. A reader therefore could
not reach the ICD from the architecture at all unless a user hand-authored a
link. This connector additionally writes 'references' links from each anchor
(direction "* -> Icd", the pair the catalog actually allows) to the ICD's
backing Artifact:

  - every ArchitectureElement Artifact passed in
    (``source_element_id``/``target_element_id``) → ICD Artifact, and
  - every Requirement Artifact allocated ('allocated-to') to one of those
    elements → ICD Artifact, so an ICD is reachable from the Requirements it
    interfaces as well.

These extra links are **best-effort**: the 'decomposes' contract link is the
REQ-L2-ICD-004 obligation and must not be rolled back because an auxiliary
anchoring link could not be written (e.g. a duplicate or a cycle). They are
written with ``get_or_create`` semantics — an already-present link is left
untouched — so re-running the connector never duplicates edges. Every created
anchor is picked up by the SE-Auditor rule ``IFC-001``
(``traceability/audit/rules/interface_coverage.py``).

The connector calls traceability.services.create_trace_link (IF-L1-039).
Errors from the traceability engine are logged and re-raised to allow the
caller (IcdManager) to decide on rollback behaviour.
"""
from __future__ import annotations

import logging
import uuid
from typing import Iterable

logger = logging.getLogger(__name__)

#: Link type used to anchor an ICD in the architecture (#1268). The catalog's
#: ``references`` pairs cover ``("*", "Icd")`` (link_types/builtin.py:361), so
#: the anchor is the *source* and the Icd Artifact the *target*.
_ANCHOR_LINK_TYPE = "references"


class TraceabilityConnector:
    """Adapter for creating TraceLinks via the TraceabilityEngine.

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
        """Create the ICD's TraceLink(s) for the given architecture elements.

        Creates a directed 'decomposes' TraceLink from source_element_id to
        target_element_id (the ICD contract between the two elements) and, on a
        best-effort basis, 'references' links anchoring the ICD in the
        architecture (#1268, see the module docstring).

        Args:
            icd_id:            UUID of the Icd being linked.
            source_element_id: Artifact UUID of the source architecture element.
            target_element_id: Artifact UUID of the target architecture element.
            created_by_id:     Optional UUID of the user creating the link.

        Raises:
            Any exception from traceability.services.create_trace_link is
            propagated to the caller (IcdManager) for transaction-level handling.
            Exceptions from the *auxiliary* 'references' links are swallowed and
            logged (best-effort anchoring), never propagated.

        req_id: REQ-L2-ICD-004
        IF:     IF-ICD-INT-002, IF-L1-039
        """
        # Import is deferred to avoid circular imports at module load time.
        # The traceability app is always available at runtime (INSTALLED_APPS).
        from traceability.services import create_trace_link

        logger.debug(
            "Creating 'decomposes' TraceLink: source=%s -> target=%s (icd=%s)",
            source_element_id,
            target_element_id,
            icd_id,
        )
        create_trace_link(
            source_id=source_element_id,
            target_id=target_element_id,
            link_type="decomposes",
            created_by_id=created_by_id,
        )
        logger.info(
            "TraceLink 'decomposes' created: source=%s -> target=%s for ICD %s",
            source_element_id,
            target_element_id,
            icd_id,
        )

        self._link_references(
            icd_id=icd_id,
            architecture_element_ids=(source_element_id, target_element_id),
            created_by_id=created_by_id,
        )

    # ------------------------------------------------------------------
    # #1268 — interface anchoring (best-effort 'references' links)
    # ------------------------------------------------------------------

    def _link_references(
        self,
        *,
        icd_id: uuid.UUID,
        architecture_element_ids: Iterable[uuid.UUID | None],
        created_by_id: uuid.UUID | None,
    ) -> None:
        """Anchor *icd_id* in the architecture with 'references' links (#1268).

        Best-effort: skips silently (debug-logged) when no tenant context is
        active or the ICD has no backing Artifact, and swallows per-link engine
        errors (logged) so the enclosing ``create_icd`` transaction is never
        rolled back on an auxiliary-link failure.
        """
        from persistence.tenancy import TenantContext, TenantContextNotSetError

        try:
            tenant_id = TenantContext.get_tenant()
        except TenantContextNotSetError:
            logger.debug(
                "No tenant context; skipping 'references' anchoring for icd=%s",
                icd_id,
            )
            return

        icd_artifact_id = self._resolve_icd_artifact_id(icd_id, tenant_id)
        if icd_artifact_id is None:
            logger.debug(
                "ICD %s has no backing Artifact; skipping 'references' anchoring",
                icd_id,
            )
            return

        anchor_ids = self._anchor_artifact_ids(architecture_element_ids, tenant_id)
        for anchor_id in sorted(anchor_ids, key=str):
            self._ensure_references_link(
                source_id=anchor_id,
                target_id=icd_artifact_id,
                tenant_id=tenant_id,
                created_by_id=created_by_id,
            )

    @staticmethod
    def _resolve_icd_artifact_id(
        icd_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Return the ICD's backing Artifact id, or ``None`` when unbacked."""
        from icd.models import Icd

        artifact_id = (
            Icd.unscoped.filter(pk=icd_id, tenant_id=tenant_id)
            .values_list("artifact_id", flat=True)
            .first()
        )
        return uuid.UUID(str(artifact_id)) if artifact_id else None

    @staticmethod
    def _anchor_artifact_ids(
        architecture_element_ids: Iterable[uuid.UUID | None], tenant_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Return the Artifact ids that should reference the ICD.

        The architecture elements themselves plus every Requirement Artifact
        allocated ('allocated-to') to one of them, per the module docstring.
        """
        from persistence.models import TraceLink

        elements = {el for el in architecture_element_ids if el is not None}
        anchors: set[uuid.UUID] = set(elements)
        if not elements:
            return anchors
        allocated = (
            TraceLink.unscoped.filter(
                tenant_id=tenant_id,
                link_type="allocated-to",
                target_id__in=list(elements),
            )
            .values_list("source_id", flat=True)
        )
        anchors.update(uuid.UUID(str(row)) for row in allocated if row)
        return anchors

    @staticmethod
    def _ensure_references_link(
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        tenant_id: uuid.UUID,
        created_by_id: uuid.UUID | None,
    ) -> bool:
        """Create a 'references' link source→target unless it already exists.

        Returns ``True`` when a new link was created, ``False`` on a no-op
        (already present) or a swallowed engine error.
        """
        from persistence.models import TraceLink

        if source_id == target_id:
            return False
        already_present = TraceLink.unscoped.filter(
            tenant_id=tenant_id,
            source_id=source_id,
            target_id=target_id,
            link_type=_ANCHOR_LINK_TYPE,
        ).exists()
        if already_present:
            return False

        from traceability.services import create_trace_link

        try:
            create_trace_link(
                source_id=source_id,
                target_id=target_id,
                link_type=_ANCHOR_LINK_TYPE,
                created_by_id=created_by_id,
            )
        except Exception:  # noqa: BLE001 — best-effort auxiliary link
            logger.warning(
                "ICD anchoring: could not create 'references' link %s -> %s",
                source_id,
                target_id,
                exc_info=True,
            )
            return False
        return True


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
