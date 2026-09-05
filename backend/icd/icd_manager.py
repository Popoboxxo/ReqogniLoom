"""
IcdManagement — IcdManager (COMP-ICD-001).

leaf_id: COMP-ICD-001
req_id:  REQ-L1-028, REQ-L2-ICD-001, REQ-L2-ICD-002, REQ-L2-ICD-003,
         REQ-L2-ICD-004, REQ-L2-ICD-005, REQ-L2-ICD-006
arch_id: ARCH-L1-014

Central coordination service for Interface Control Documents.

Implements:
  - create_icd  : creates Icd + IcdVersion(v1), links via TraceabilityConnector
  - update_icd  : appends a new IcdVersion, runs breaking-change detection,
                  calls AuditLogger on breaking changes
  - validate_compatibility: standalone contract check without persisting
  - get_icd_history: all IcdVersions for one Icd
  - get_icd_versions: current versions for a workspace (IF-L1-038, BaselineService)

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

from icd.audit_logger import get_audit_logger
from icd.contract_validator import ValidationResult, get_validator
from icd.models import Icd, IcdVersion
from icd.traceability_connector import get_connector

logger = logging.getLogger(__name__)


def _apply_embedding(version: IcdVersion) -> None:
    """Best-effort: set ``version.embedding`` in-place before it is saved.

    REQ-L2-VS-004. IcdVersion is immutable (BEFORE UPDATE trigger), so the
    embedding MUST be assigned before the initial INSERT — it can never be
    patched in afterwards. Never raises: a provider/network failure must not
    fail the surrounding create/update transaction (best-effort, mirrors
    RequirementService._generate_and_store_embedding).
    """
    try:
        from llm_adapter.embedding_service import (
            generate_embedding,
            get_icd_version_embedding_text,
            warn_dimension_mismatch,
        )

        embedding = generate_embedding(get_icd_version_embedding_text(version))
        field_dimensions = IcdVersion._meta.get_field("embedding").dimensions
        if embedding is not None and len(embedding) == field_dimensions:
            version.embedding = embedding
        elif embedding is not None:
            # Dimension mismatch (a non-default EMBEDDING_PROVIDER whose
            # native width differs from EMBEDDING_VECTOR_DIMENSIONS — see
            # RequirementService._generate_and_store_embedding and #794 for
            # the full rationale). Unlike the Requirement/TraceLink write
            # paths, this function only sets the in-memory attribute; the
            # actual INSERT happens later, outside this try/except, so an
            # unguarded assignment here would surface as an *uncaught*
            # DataError at save() time instead of a caught one here. Skip
            # the assignment so ``version.embedding`` stays unset (None).
            warn_dimension_mismatch(
                "IcdManager", len(embedding), field_dimensions
            )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug(
            "IcdManager: embedding generation skipped for icd=%s: %s",
            getattr(version, "icd_id", None),
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
    """Input payload for updating an existing ICD (appends a new IcdVersion).

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
    """Return value wrapping Icd + current IcdVersion + validation state.

    leaf_id: COMP-ICD-001
    """

    icd: Icd
    current_version: IcdVersion
    validation_result: ValidationResult | None = None


@dataclass
class SimilarIcdDTO:
    """A single ICD similarity-search hit (REQ-L2-VS-004).

    Identifies the matched ICD by its header id plus the current version that
    carried the matched embedding, and the cosine similarity_score.
    """

    icd_id: uuid.UUID
    version_id: uuid.UUID
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
        """Create a new ICD with initial version 1.

        Steps:
          1. Validate syntax of incoming payload (ContractValidator).
          2. Persist Icd header and IcdVersion(version=1) atomically.
          3. Point Icd.current_version to the new IcdVersion.
          4. Call TraceabilityConnector to create 'realizes' TraceLink (IF-ICD-INT-002).

        Args:
            payload: IcdCreateDTO with all required fields.

        Returns:
            IcdResult with the new Icd and IcdVersion.

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

            # Create the Icd header (without current_version yet to avoid
            # a chicken-and-egg FK constraint)
            icd = Icd(
                id=uuid.uuid4(),
                tenant=tenant,
                workspace_id=payload.workspace_id,
                name=payload.name,
                source_element_id=payload.source_element_id,
                target_element_id=payload.target_element_id,
            )
            icd.save()

            # Datenmodell-Konsolidierung Phase 3 (spec §4.3): create the
            # backing Artifact up front instead of leaving the Icd unbacked
            # until some later on-demand path creates one, so an ICD is a
            # valid TraceLink endpoint and Document-scope baseline subject
            # from birth.
            ensure_artifact(icd, artifact_type="Icd", workspace_id=icd.workspace_id)

            # Create the first IcdVersion (immutable from DB trigger onwards)
            version = IcdVersion(
                id=uuid.uuid4(),
                tenant=tenant,
                icd=icd,
                version_number=1,
                direction=payload.direction,
                interface_type=payload.interface_type,
                semantic_description=payload.semantic_description,
                preconditions=list(payload.preconditions),
                postconditions=list(payload.postconditions),
                invariants=list(payload.invariants),
            )
            # REQ-L2-VS-004: assign the semantic embedding BEFORE the INSERT —
            # IcdVersion is immutable, so it cannot be patched in afterwards.
            _apply_embedding(version)
            version.save()

            # Point the header at its first version
            icd.current_version = version
            icd.save(update_fields=["current_version", "modified_at", "version"])

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
        """Append a new IcdVersion and run breaking-change detection.

        Steps:
          1. Load the current IcdVersion.
          2. Build the new version by merging payload fields onto the current state.
          3. Validate syntax of the merged payload.
          4. Run ContractValidator.validate_contract (IF-ICD-INT-001).
          5. Persist the new IcdVersion (append-only via INSERT).
          6. Update Icd.current_version pointer.
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
            IcdResult with the updated Icd and new IcdVersion.
            validation_result is populated with the breaking-change assessment.

        Raises:
            Icd.DoesNotExist: When the ICD is not found for this tenant.
            Any DB or audit error propagates for rollback.

        req_id: REQ-L2-ICD-001, REQ-L2-ICD-003, REQ-L2-ICD-006
        IF:     IF-L1-037, IF-ICD-INT-001, IF-ICD-INT-003, IF-L1-040
        """
        with transaction.atomic():
            icd: Icd = Icd.unscoped.select_for_update().get(pk=icd_id, tenant_id=tenant_id)
            old_version: IcdVersion = icd.current_version  # type: ignore[assignment]

            # Merge payload onto current state (None fields keep old value)
            new_direction = payload.direction if payload.direction is not None else old_version.direction
            new_interface_type = payload.interface_type if payload.interface_type is not None else old_version.interface_type
            new_semantic_description = payload.semantic_description if payload.semantic_description is not None else old_version.semantic_description
            new_preconditions = list(payload.preconditions) if payload.preconditions is not None else list(old_version.preconditions)
            new_postconditions = list(payload.postconditions) if payload.postconditions is not None else list(old_version.postconditions)
            new_invariants = list(payload.invariants) if payload.invariants is not None else list(old_version.invariants)

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
                old_preconditions=list(old_version.preconditions),
                old_postconditions=list(old_version.postconditions),
                old_invariants=list(old_version.invariants),
                new_preconditions=new_preconditions,
                new_postconditions=new_postconditions,
                new_invariants=new_invariants,
            )

            # Append new IcdVersion (immutable after save; DB trigger prevents updates)
            new_version = IcdVersion(
                id=uuid.uuid4(),
                tenant=icd.tenant,
                icd=icd,
                version_number=old_version.version_number + 1,
                direction=new_direction,
                interface_type=new_interface_type,
                semantic_description=new_semantic_description,
                preconditions=new_preconditions,
                postconditions=new_postconditions,
                invariants=new_invariants,
            )
            # REQ-L2-VS-004: embed at INSERT time (immutable version).
            _apply_embedding(new_version)
            new_version.save()

            # Advance the header pointer
            icd.current_version = new_version
            icd.save(update_fields=["current_version", "modified_at", "version"])

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
        """Check proposed contract data against the current IcdVersion without persisting.

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
        old: IcdVersion = icd.current_version  # type: ignore[assignment]

        syntax_check = self._validator.validate_syntax(new_payload)
        if not syntax_check.is_valid_syntax:
            return syntax_check

        return self._validator.validate_contract(
            old_preconditions=list(old.preconditions),
            old_postconditions=list(old.postconditions),
            old_invariants=list(old.invariants),
            new_preconditions=list(new_payload.get("preconditions", old.preconditions)),
            new_postconditions=list(new_payload.get("postconditions", old.postconditions)),
            new_invariants=list(new_payload.get("invariants", old.invariants)),
        )

    # ------------------------------------------------------------------
    # get_icd_history — IF-L1-037 (history read)
    # ------------------------------------------------------------------

    def get_icd_history(
        self, icd_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> list[IcdVersion]:
        """Return all IcdVersions for the given ICD, ordered oldest-first.

        Args:
            icd_id: UUID of the Icd.
            tenant_id: Active tenant UUID (row-level isolation). Every current
                call site already re-validates icd_id's tenant ownership via
                get_icd() before calling this, but requiring it here too closes
                the gap defensively for any future caller that forgets to
                (exactly what happened to the REST PATCH/update_icd path).

        Returns:
            List of IcdVersion objects ordered by version_number ascending.

        req_id: REQ-L2-ICD-001
        IF:     IF-L1-037
        """
        return list(
            IcdVersion.unscoped.filter(icd_id=icd_id, tenant_id=tenant_id)
            .order_by("version_number")
        )

    # ------------------------------------------------------------------
    # get_icd_versions — IF-L1-038 (BaselineService snapshot)
    # ------------------------------------------------------------------

    def get_icd_versions(self, workspace_id: uuid.UUID) -> list[IcdVersion]:
        """Return the current (latest) IcdVersion for each ICD in a workspace.

        Used by BaselineService (IF-L1-038) to capture a point-in-time snapshot
        of all interface contracts within a workspace.

        The result set contains exactly one IcdVersion per Icd (the most recent),
        filtered by workspace_id.

        Args:
            workspace_id: UUID of the workspace to snapshot.

        Returns:
            List of IcdVersion objects — one per active ICD in the workspace.

        req_id: REQ-L2-ICD-005
        IF:     IF-L1-038
        """
        # Fetch all Icd headers in this workspace, select_related for efficiency
        icds = Icd.unscoped.filter(
            workspace_id=workspace_id,
            current_version__isnull=False,
        ).select_related("current_version")

        return [icd.current_version for icd in icds]  # type: ignore[misc]

    # ------------------------------------------------------------------
    # find_similar_icds — semantic similarity (REQ-L2-VS-004)
    # ------------------------------------------------------------------

    def find_similar_icds(
        self,
        icd_id: uuid.UUID,
        tenant_id: uuid.UUID,
        limit: int = 10,
    ) -> list[SimilarIcdDTO]:
        """Return the ICDs whose current version is most similar to *icd_id*.

        REQ-L2-VS-004: cosine-distance nearest-neighbour search over the
        pgvector ``embedding`` column of the current IcdVersion, tenant-scoped
        and excluding the query ICD itself. Mirrors
        RequirementService.find_similar_requirements.

        Args:
            icd_id: Query ICD (its current version must have a non-null embedding).
            tenant_id: Tenant scope.
            limit: Max results (clamped to 1..50, default 10).

        Returns:
            Ordered list of SimilarIcdDTO (closest first).

        Raises:
            Icd.DoesNotExist: Query ICD does not exist.
            ValueError: Query ICD's current version has no embedding.
            IcdPgVectorUnavailableError: pgvector package/extension unavailable.
        """
        from django.db.utils import OperationalError, ProgrammingError

        icd = (
            Icd.unscoped.filter(id=icd_id, tenant_id=tenant_id)
            .select_related("current_version")
            .first()
        )
        if icd is None:
            raise Icd.DoesNotExist(f"Icd {icd_id} not found")

        query_version = icd.current_version
        if query_version is None or query_version.embedding is None:
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

        # Compare against the current version of every other ICD in the tenant.
        current_version_ids = (
            Icd.unscoped.filter(
                tenant_id=tenant_id, current_version__isnull=False
            )
            .exclude(id=icd.id)
            .values_list("current_version_id", flat=True)
        )
        queryset = (
            IcdVersion.unscoped.filter(
                id__in=list(current_version_ids), embedding__isnull=False
            )
            .select_related("icd")
            .annotate(distance=CosineDistance("embedding", query_version.embedding))
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
                icd_id=row.icd_id,
                version_id=row.id,
                name=row.icd.name if row.icd_id else "",
                interface_type=row.interface_type or "",
                version_number=row.version_number,
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
