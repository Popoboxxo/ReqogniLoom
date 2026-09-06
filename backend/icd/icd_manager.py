"""
IcdManagement — IcdManager (COMP-ICD-001).

leaf_id: COMP-ICD-001
req_id:  REQ-L1-028, REQ-L2-ICD-001, REQ-L2-ICD-002, REQ-L2-ICD-003,
         REQ-L2-ICD-004, REQ-L2-ICD-005, REQ-L2-ICD-006
arch_id: ARCH-L1-014

Central coordination service for Interface Control Documents.

Implements:
  - create_icd  : creates the Icd with its contract at revision 1, links via
                  TraceabilityConnector
  - update_icd  : overwrites the contract in place, appends the new revision
                  snapshot, runs breaking-change detection, calls AuditLogger
                  on breaking changes
  - validate_compatibility: standalone contract check without persisting
  - get_icd_history: all contract revisions of one Icd
  - get_icd_versions: current revision per ICD in a workspace (IF-L1-038,
                      BaselineService)

Datenmodell-Konsolidierung Task 28c-2: the ``IcdVersion`` table is gone. The
current contract lives on the :class:`icd.models.Icd` header and its history in
the one shared :class:`persistence.models.ArtifactVersion` store, rehydrated
into :class:`icd.models.IcdRevision` for readers.

Internal interfaces consumed:
  IF-ICD-INT-001: ContractValidator.validate_contract
  IF-ICD-INT-002: TraceabilityConnector.link_to_architecture
  IF-ICD-INT-003: AuditLogger.log_breaking_change

External interfaces served:
  IF-L1-037 (ApplicationService CRUD)
  IF-L1-038 (BaselineService snapshot)
  IF-L1-040 (PersistenceLayer via Django ORM save/query)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from persistence.artifact_backing import ensure_artifact
from persistence.models import ArtifactVersion

from icd.audit_logger import get_audit_logger
from icd.contract_validator import ValidationResult, get_validator
from icd.models import Icd, IcdRevision
from icd.traceability_connector import get_connector

logger = logging.getLogger(__name__)

#: Fields written to ``Icd`` by a contract create/update, plus the audit
#: columns ``AuditableModel.save`` maintains. Named once so the two write
#: paths cannot drift apart in what they persist.
_CONTRACT_UPDATE_FIELDS = [
    "direction",
    "interface_type",
    "semantic_description",
    "preconditions",
    "postconditions",
    "invariants",
    "embedding",
    "current_revision",
    "modified_at",
    "version",
]


def _record_artifact_revision(icd: Icd) -> int:
    """Append the ``ArtifactVersion`` snapshot of *icd*'s current contract.

    Writes the row directly instead of calling
    ``application.artifact_version_service.ArtifactVersionService``: this module
    is Layer 1/Ext and must not import Layer 2 (ADR-01, single entry point).

    The payload carries the field list registered for ``"Icd"`` in
    ``application.artifact_diff_service._ENTITY_FIELDS`` — including
    ``parameters_snapshot``, the by-value rendering of the structured
    parameters, which are current-state-only child rows and would otherwise be
    the one part of an ICD with no recoverable history.

    The revision number is allocated as ``current_revision + 1`` while holding
    a row lock on the ICD header, the same discipline
    ``ArtifactVersionService.record`` uses on the Artifact row, so two
    concurrent writers cannot allocate the same number and collide on
    ``uq_artifact_version_revision``.

    Args:
        icd: The ICD header, already carrying the contract to snapshot.

    Returns:
        The newly allocated revision number.

    Must run inside the caller's transaction so the snapshot rolls back with
    the contract it describes.
    """
    # Idempotent no-op when the backing already exists; this only fires for a
    # pre-Phase-3 ICD, which would otherwise never start a history at all.
    ensure_artifact(icd, artifact_type="Icd", workspace_id=icd.workspace_id)

    # The lock is on the row whose counter is being incremented. update_icd
    # already holds it; create_icd's row is this transaction's own uncommitted
    # INSERT. Re-reading through it makes the allocation correct for any
    # future caller that holds neither.
    locked_revision = (
        Icd.unscoped.select_for_update()
        .filter(pk=icd.pk)
        .values_list("current_revision", flat=True)
        .first()
    )
    revision = (locked_revision or 0) + 1
    icd.current_revision = revision

    ArtifactVersion.objects.create(
        tenant=icd.tenant,
        artifact_id=icd.artifact_id,
        revision=revision,
        payload={
            "name": icd.name,
            "direction": icd.direction,
            "interface_type": icd.interface_type,
            "semantic_description": icd.semantic_description,
            "preconditions": list(icd.preconditions or []),
            "postconditions": list(icd.postconditions or []),
            "invariants": list(icd.invariants or []),
            "parameters_snapshot": icd.parameters_snapshot,
        },
    )
    return revision


def _apply_embedding(icd: Icd) -> None:
    """Best-effort: set ``icd.embedding`` in-place before the header is saved.

    REQ-L2-VS-004. Unlike the retired immutable ``IcdVersion``, the ICD header
    is mutable, so the embedding is regenerated on every contract change and a
    generation that failed once can simply be retried by the next write (or by
    ``manage.py backfill_embeddings --model icd``). Never raises: a
    provider/network failure must not fail the surrounding create/update
    transaction (best-effort, mirrors
    ``RequirementService._generate_and_store_embedding``).
    """
    try:
        from llm_adapter.embedding_service import (
            generate_embedding,
            get_icd_embedding_text,
            warn_dimension_mismatch,
        )

        embedding = generate_embedding(get_icd_embedding_text(icd))
        field_dimensions = Icd._meta.get_field("embedding").dimensions
        if embedding is not None and len(embedding) == field_dimensions:
            icd.embedding = embedding
        elif embedding is not None:
            # Dimension mismatch (a non-default EMBEDDING_PROVIDER whose
            # native width differs from EMBEDDING_VECTOR_DIMENSIONS — see
            # RequirementService._generate_and_store_embedding and #794 for
            # the full rationale). This function only sets the in-memory
            # attribute; the actual write happens later, outside this
            # try/except, so an unguarded assignment would surface as an
            # *uncaught* DataError at save() time instead of a caught one
            # here. Skip the assignment so the previous value survives.
            warn_dimension_mismatch(
                "IcdManager", len(embedding), field_dimensions
            )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug(
            "IcdManager: embedding generation skipped for icd=%s: %s",
            getattr(icd, "pk", None),
            exc,
        )


# ---------------------------------------------------------------------------
# DTOs (data transfer objects for public API, IF-L1-037)
# ---------------------------------------------------------------------------

@dataclass
class IcdCreateDTO:
    """Input payload for creating a new ICD.

    leaf_id: COMP-ICD-001
    req_id:  REQ-L2-ICD-001, REQ-L2-ICD-002
    """

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    source_element_id: uuid.UUID
    target_element_id: uuid.UUID
    direction: str = "unidirectional"
    interface_type: str = ""
    semantic_description: str = ""
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    created_by_id: uuid.UUID | None = None


@dataclass
class IcdUpdateDTO:
    """Input payload for updating an ICD (records a new contract revision).

    leaf_id: COMP-ICD-001
    req_id:  REQ-L2-ICD-001, REQ-L2-ICD-002, REQ-L2-ICD-003
    """

    direction: str | None = None
    interface_type: str | None = None
    semantic_description: str | None = None
    preconditions: list[str] | None = None
    postconditions: list[str] | None = None
    invariants: list[str] | None = None
    modified_by_id: uuid.UUID | None = None


@dataclass
class IcdResult:
    """Return value wrapping Icd + its current contract revision + validation.

    leaf_id: COMP-ICD-001
    """

    icd: Icd
    current_version: IcdRevision
    validation_result: ValidationResult | None = None


@dataclass
class SimilarIcdDTO:
    """A single ICD similarity-search hit (REQ-L2-VS-004).

    Identifies the matched ICD by its id and the cosine ``similarity_score``.

    Task 28c-2 removed the ``version_id`` field: the embedding now lives on the
    ICD header, so there is no version row to identify. ``version_number`` is
    the ICD's current revision.
    """

    icd_id: uuid.UUID
    name: str
    interface_type: str
    version_number: int
    similarity_score: float


class IcdPgVectorUnavailableError(RuntimeError):
    """Raised when pgvector (package or ``vector`` extension) is unavailable.

    REQ-L2-VS-004: similarity search depends on pgvector. The REST layer maps
    this to HTTP 503 (service unavailable) rather than a 500.
    """


# ---------------------------------------------------------------------------
# COMP-ICD-001: IcdManager
# ---------------------------------------------------------------------------

class IcdManager:
    """Central coordination service for ICD lifecycle operations.

    leaf_id: COMP-ICD-001
    req_id:  REQ-L2-ICD-001 through REQ-L2-ICD-006
    IF:      IF-L1-037, IF-L1-038, IF-ICD-INT-001, IF-ICD-INT-002, IF-ICD-INT-003
    """

    def __init__(self) -> None:
        self._validator = get_validator()
        self._connector = get_connector()
        self._audit_logger = get_audit_logger()

    def _resolve_arch_artifact_id(self, element_id: uuid.UUID) -> uuid.UUID:
        """Resolve an ArchitectureElement ID to its backing Artifact ID.

        The TraceabilityEngine stores links between Artifact rows. Caller must
        ensure the tenant context is set before querying.
        """
        from persistence.models import ArchitectureElement

        arch = ArchitectureElement.objects.filter(id=element_id).first()
        if arch is None:
            raise ValueError(f"ArchitectureElement {element_id} not found")
        return uuid.UUID(str(arch.artifact_id))

    # ------------------------------------------------------------------
    # create_icd — IF-L1-037 (create path)
    # ------------------------------------------------------------------

    def create_icd(self, payload: IcdCreateDTO) -> IcdResult:
        """Create a new ICD with its contract at revision 1.

        Steps:
          1. Validate syntax of incoming payload (ContractValidator).
          2. Persist the Icd row carrying the contract, atomically.
          3. Snapshot revision 1 into the shared ArtifactVersion store.
          4. Call TraceabilityConnector to create 'realizes' TraceLink (IF-ICD-INT-002).

        Args:
            payload: IcdCreateDTO with all required fields.

        Returns:
            IcdResult with the new Icd and its revision-1 IcdRevision.

        Raises:
            ValueError: When syntax validation fails.
            Any DB or TraceabilityEngine error propagates for rollback.

        req_id: REQ-L2-ICD-001, REQ-L2-ICD-002, REQ-L2-ICD-004
        IF:     IF-L1-037, IF-ICD-INT-002, IF-L1-040
        """
        from persistence.models import Tenant, ArchitectureElement
        from persistence.tenancy import TenantContext

        syntax_check = self._validator.validate_syntax(
            {
                "direction": payload.direction,
                "interface_type": payload.interface_type,
                "semantic_description": payload.semantic_description,
                "preconditions": payload.preconditions,
                "postconditions": payload.postconditions,
                "invariants": payload.invariants,
            }
        )
        if not syntax_check.is_valid_syntax:
            raise ValueError(
                f"ICD payload failed syntax validation: {syntax_check.syntax_errors}"
            )

        with transaction.atomic():
            tenant = Tenant.objects.get(pk=payload.tenant_id)

            icd = Icd(
                id=uuid.uuid4(),
                tenant=tenant,
                workspace_id=payload.workspace_id,
                name=payload.name,
                source_element_id=payload.source_element_id,
                target_element_id=payload.target_element_id,
                direction=payload.direction,
                interface_type=payload.interface_type,
                semantic_description=payload.semantic_description,
                preconditions=list(payload.preconditions),
                postconditions=list(payload.postconditions),
                invariants=list(payload.invariants),
            )
            # REQ-L2-VS-004: best-effort, so it is assigned before the INSERT
            # to save a round trip — but unlike the retired immutable
            # IcdVersion, a failure here is recoverable on the next update.
            _apply_embedding(icd)
            icd.save()

            # Datenmodell-Konsolidierung Phase 3 (spec §4.3): create the
            # backing Artifact up front instead of leaving the Icd unbacked
            # until some later on-demand path creates one, so an ICD is a
            # valid TraceLink endpoint and Document-scope baseline subject
            # from birth. Task 28c-2 additionally makes it the anchor the
            # contract history hangs off, so it must exist before the first
            # revision is recorded.
            ensure_artifact(icd, artifact_type="Icd", workspace_id=icd.workspace_id)

            # Datenmodell-Konsolidierung Phase 5 (spec §6.1): record revision 1
            # in the shared revision store and advance the header's counter.
            _record_artifact_revision(icd)
            icd.save(update_fields=_CONTRACT_UPDATE_FIELDS)
            version = IcdRevision.from_icd(icd)

            # IF-ICD-INT-002: create realizes TraceLink. The engine stores
            # Artifact IDs, so resolve the ArchitectureElement IDs first.
            TenantContext.set_tenant(str(tenant.id))
            source_artifact = self._resolve_arch_artifact_id(
                payload.source_element_id
            )
            target_artifact = self._resolve_arch_artifact_id(
                payload.target_element_id
            )
            self._connector.link_to_architecture(
                icd_id=icd.id,
                source_element_id=source_artifact,
                target_element_id=target_artifact,
                created_by_id=payload.created_by_id,
            )

        return IcdResult(icd=icd, current_version=version)

    # ------------------------------------------------------------------
    # update_icd — IF-L1-037 (update path)
    # ------------------------------------------------------------------

    def update_icd(
        self,
        icd_id: uuid.UUID,
        payload: IcdUpdateDTO,
        tenant_id: uuid.UUID,
    ) -> IcdResult:
        """Overwrite the contract, snapshot it, and run breaking-change detection.

        Steps:
          1. Load and lock the Icd row (its columns are the current contract).
          2. Merge the payload fields onto the current state.
          3. Validate syntax of the merged payload.
          4. Run ContractValidator.validate_contract (IF-ICD-INT-001).
          5. Persist the merged contract onto the header.
          6. Append the new revision to the shared ArtifactVersion store.
          7. If breaking changes detected: call AuditLogger (IF-ICD-INT-003).

        Args:
            icd_id:  UUID of the Icd to update.
            payload: IcdUpdateDTO with fields to change (None = keep current value).
            tenant_id: Active tenant UUID (row-level isolation — security fix:
                this previously used `.unscoped.select_for_update().get(pk=icd_id)`
                with no tenant filter at all, so any authenticated user of any
                tenant could not just READ but MUTATE another tenant's ICD by
                supplying its UUID; the REST PATCH action had no tenant-
                ownership check of its own either, unlike its sibling actions).

        Returns:
            IcdResult with the updated Icd and the new IcdRevision.
            validation_result is populated with the breaking-change assessment.

        Raises:
            Icd.DoesNotExist: When the ICD is not found for this tenant.
            Any DB or audit error propagates for rollback.

        req_id: REQ-L2-ICD-001, REQ-L2-ICD-003, REQ-L2-ICD-006
        IF:     IF-L1-037, IF-ICD-INT-001, IF-ICD-INT-003, IF-L1-040
        """
        with transaction.atomic():
            icd: Icd = Icd.unscoped.select_for_update().get(pk=icd_id, tenant_id=tenant_id)
            old_preconditions = list(icd.preconditions or [])
            old_postconditions = list(icd.postconditions or [])
            old_invariants = list(icd.invariants or [])

            # Merge payload onto current state (None fields keep old value)
            new_direction = payload.direction if payload.direction is not None else icd.direction
            new_interface_type = payload.interface_type if payload.interface_type is not None else icd.interface_type
            new_semantic_description = payload.semantic_description if payload.semantic_description is not None else icd.semantic_description
            new_preconditions = list(payload.preconditions) if payload.preconditions is not None else old_preconditions
            new_postconditions = list(payload.postconditions) if payload.postconditions is not None else old_postconditions
            new_invariants = list(payload.invariants) if payload.invariants is not None else old_invariants

            # Syntax check on merged data
            syntax_check = self._validator.validate_syntax(
                {
                    "direction": new_direction,
                    "interface_type": new_interface_type,
                    "semantic_description": new_semantic_description,
                    "preconditions": new_preconditions,
                    "postconditions": new_postconditions,
                    "invariants": new_invariants,
                }
            )
            if not syntax_check.is_valid_syntax:
                raise ValueError(
                    f"ICD update payload failed syntax validation: {syntax_check.syntax_errors}"
                )

            # IF-ICD-INT-001: semantic breaking-change detection
            validation_result = self._validator.validate_contract(
                old_preconditions=old_preconditions,
                old_postconditions=old_postconditions,
                old_invariants=old_invariants,
                new_preconditions=new_preconditions,
                new_postconditions=new_postconditions,
                new_invariants=new_invariants,
            )

            # Overwrite the contract in place — the header IS the current
            # contract since Task 28c-2; history is the ArtifactVersion trail.
            icd.direction = new_direction
            icd.interface_type = new_interface_type
            icd.semantic_description = new_semantic_description
            icd.preconditions = new_preconditions
            icd.postconditions = new_postconditions
            icd.invariants = new_invariants
            # REQ-L2-VS-004: regenerate for the new contract text.
            _apply_embedding(icd)

            # Datenmodell-Konsolidierung Phase 5 (spec §6.1): record vN in the
            # shared revision store and advance the header's counter.
            _record_artifact_revision(icd)
            icd.save(update_fields=_CONTRACT_UPDATE_FIELDS)
            new_version = IcdRevision.from_icd(icd)

            # IF-ICD-INT-003: audit breaking changes
            if validation_result.is_breaking:
                details = "; ".join(validation_result.breaking_changes)
                self._audit_logger.log_breaking_change(icd_id=icd.id, details=details)

        return IcdResult(
            icd=icd,
            current_version=new_version,
            validation_result=validation_result,
        )

    # ------------------------------------------------------------------
    # validate_compatibility — standalone check (IF-L1-037)
    # ------------------------------------------------------------------

    def validate_compatibility(
        self,
        icd_id: uuid.UUID,
        new_payload: dict[str, Any],
        tenant_id: uuid.UUID,
    ) -> ValidationResult:
        """Check proposed contract data against the current contract without persisting.

        Useful for dry-run validation before committing an update.

        Args:
            icd_id:      UUID of the target Icd.
            new_payload: Dict with proposed contract fields (same structure as IcdUpdateDTO).
            tenant_id: Active tenant UUID (row-level isolation).

        Returns:
            ValidationResult with syntax and semantic breaking-change assessment.

        req_id: REQ-L2-ICD-003
        IF:     IF-L1-037
        """
        icd: Icd = Icd.unscoped.get(pk=icd_id, tenant_id=tenant_id)
        old_preconditions = list(icd.preconditions or [])
        old_postconditions = list(icd.postconditions or [])
        old_invariants = list(icd.invariants or [])

        syntax_check = self._validator.validate_syntax(new_payload)
        if not syntax_check.is_valid_syntax:
            return syntax_check

        return self._validator.validate_contract(
            old_preconditions=old_preconditions,
            old_postconditions=old_postconditions,
            old_invariants=old_invariants,
            new_preconditions=list(
                new_payload.get("preconditions", old_preconditions)
            ),
            new_postconditions=list(
                new_payload.get("postconditions", old_postconditions)
            ),
            new_invariants=list(new_payload.get("invariants", old_invariants)),
        )

    # ------------------------------------------------------------------
    # get_icd_history — IF-L1-037 (history read)
    # ------------------------------------------------------------------

    def get_icd_history(
        self, icd_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> list[IcdRevision]:
        """Return all contract revisions of the given ICD, oldest-first.

        Task 28c-2: reads the shared ``ArtifactVersion`` store rather than the
        retired ``IcdVersion`` table. Returns an empty list for an ICD with no
        backing Artifact, which is the only shape that can carry no history.

        Args:
            icd_id: UUID of the Icd.
            tenant_id: Active tenant UUID (row-level isolation). Every current
                call site already re-validates icd_id's tenant ownership via
                get_icd() before calling this, but requiring it here too closes
                the gap defensively for any future caller that forgets to
                (exactly what happened to the REST PATCH/update_icd path).

        Returns:
            List of IcdRevision objects ordered by version_number ascending.

        req_id: REQ-L2-ICD-001
        IF:     IF-L1-037
        """
        artifact_id = (
            Icd.unscoped.filter(pk=icd_id, tenant_id=tenant_id)
            .values_list("artifact_id", flat=True)
            .first()
        )
        if artifact_id is None:
            return []

        rows = ArtifactVersion.unscoped.filter(
            artifact_id=artifact_id, tenant_id=tenant_id
        ).order_by("revision")
        return [
            IcdRevision.from_payload(
                icd_id=icd_id,
                revision=row.revision,
                payload=row.payload or {},
                created_at=row.created_at,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # get_icd_versions — IF-L1-038 (BaselineService snapshot)
    # ------------------------------------------------------------------

    def get_icd_versions(self, workspace_id: uuid.UUID) -> list[IcdRevision]:
        """Return the current contract revision of each ICD in a workspace.

        Used by BaselineService (IF-L1-038) to capture a point-in-time snapshot
        of all interface contracts within a workspace.

        Args:
            workspace_id: UUID of the workspace to snapshot.

        Returns:
            List of IcdRevision objects — one per ICD in the workspace that has
            at least one recorded revision.

        req_id: REQ-L2-ICD-005
        IF:     IF-L1-038
        """
        # ponytail: IcdRevision.from_icd reads each ICD's parameters, i.e. one
        # extra query per ICD. Batch it if this ever serves a hot path; today
        # it has no production caller.
        return [
            IcdRevision.from_icd(icd)
            for icd in Icd.unscoped.filter(
                workspace_id=workspace_id, current_revision__gt=0
            )
        ]

    # ------------------------------------------------------------------
    # find_similar_icds — semantic similarity (REQ-L2-VS-004)
    # ------------------------------------------------------------------

    def find_similar_icds(
        self,
        icd_id: uuid.UUID,
        tenant_id: uuid.UUID,
        limit: int = 10,
    ) -> list[SimilarIcdDTO]:
        """Return the ICDs whose contract is most similar to *icd_id*'s.

        REQ-L2-VS-004: cosine-distance nearest-neighbour search over the
        pgvector ``embedding`` column of the Icd header (Task 28c-2 moved it
        there from the retired IcdVersion), tenant-scoped and excluding the
        query ICD itself. Mirrors RequirementService.find_similar_requirements.

        Args:
            icd_id: Query ICD (must have a non-null embedding).
            tenant_id: Tenant scope.
            limit: Max results (clamped to 1..50, default 10).

        Returns:
            Ordered list of SimilarIcdDTO (closest first).

        Raises:
            Icd.DoesNotExist: Query ICD does not exist.
            ValueError: Query ICD has no embedding.
            IcdPgVectorUnavailableError: pgvector package/extension unavailable.
        """
        from django.db.utils import OperationalError, ProgrammingError

        icd = Icd.unscoped.filter(id=icd_id, tenant_id=tenant_id).first()
        if icd is None:
            raise Icd.DoesNotExist(f"Icd {icd_id} not found")

        if icd.embedding is None:
            raise ValueError(
                "ICD has no embedding — similarity search not possible"
            )

        try:
            from pgvector.django import CosineDistance
        except ImportError as exc:
            raise IcdPgVectorUnavailableError(
                "pgvector package not installed — similarity search unavailable"
            ) from exc

        safe_limit = max(1, min(int(limit or 10), 50))

        queryset = (
            Icd.unscoped.filter(tenant_id=tenant_id, embedding__isnull=False)
            .exclude(id=icd.id)
            .annotate(distance=CosineDistance("embedding", icd.embedding))
            .order_by("distance")[:safe_limit]
        )

        try:
            rows = list(queryset)
        except (ProgrammingError, OperationalError) as exc:
            raise IcdPgVectorUnavailableError(
                "pgvector extension not available — similarity search unavailable"
            ) from exc

        return [
            SimilarIcdDTO(
                icd_id=row.id,
                name=row.name,
                interface_type=row.interface_type or "",
                version_number=row.current_revision,
                # Cosine distance in [0, 2]; similarity = 1 - distance.
                similarity_score=round(1.0 - float(row.distance), 6),
            )
            for row in rows
        ]


# Module-level singleton — services.py delegates to this instance
_manager = IcdManager()


def get_manager() -> IcdManager:
    """Return the module-level IcdManager singleton.

    leaf_id: COMP-ICD-001
    """
    return _manager


__all__ = [
    "IcdManager",
    "IcdCreateDTO",
    "IcdUpdateDTO",
    "IcdResult",
    "SimilarIcdDTO",
    "IcdPgVectorUnavailableError",
    "get_manager",
]
