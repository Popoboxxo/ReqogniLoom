"""
IcdManagement — Public Service Facade (ARCH-L1-014).

leaf_id: COMP-ICD-001
req_id:  REQ-L1-028, REQ-L2-ICD-001 through REQ-L2-ICD-006
arch_id: ARCH-L1-014

This module is the ONLY public import surface for downstream consumers
(ApplicationService, BaselineService). All IcdManagement operations are
accessed through these functions.

Public import paths:
    from icd.services import (
        create_icd,
        update_icd,
        validate_compatibility,
        get_icd_history,
        get_icd_versions,
    )
    from icd.services import IcdCreateDTO, IcdUpdateDTO, IcdResult, ValidationResult

Interfaces:
  IF-L1-037 (ApplicationService): create_icd, update_icd,
                                   validate_compatibility, get_icd_history
  IF-L1-038 (BaselineService):    get_icd_versions(workspace_id)
"""
from __future__ import annotations

import uuid
from typing import Any

from icd.contract_validator import ValidationResult
from icd.icd_manager import (
    IcdCreateDTO,
    IcdPgVectorUnavailableError,
    IcdResult,
    IcdUpdateDTO,
    SimilarIcdDTO,
    get_manager,
)
from icd.icd_parameter_service import (
    IcdParameterCreateDTO,
    IcdParameterNotFoundError,
    IcdParameterUpdateDTO,
    get_parameter_service,
)
from icd.models import Icd, IcdParameter, IcdVersion


# ---------------------------------------------------------------------------
# IF-L1-037: ApplicationService CRUD
# ---------------------------------------------------------------------------


def get_icd(icd_id: uuid.UUID, tenant_id: uuid.UUID) -> Icd:
    """Return a single tenant-scoped ICD by id (REQ-066).

    Encapsulates the tenant-scoped ORM lookup so REST views stay ORM-free.

    Args:
        icd_id:    UUID of the target Icd.
        tenant_id: Active tenant primary key (isolation boundary).

    Returns:
        The matching :class:`Icd` instance.

    Raises:
        Icd.DoesNotExist: When no ICD with the given id exists for the tenant.

    req_id: REQ-066, REQ-L2-ICD-001
    leaf_id: COMP-ICD-001
    """
    return Icd.objects.get(id=icd_id, tenant_id=tenant_id)


def delete_icd(icd_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Delete a tenant-scoped ICD and all its immutable versions (REQ-066).

    IcdVersion rows are immutable via a DB trigger (ADR-ICD-01); the trigger is
    temporarily disabled to permit cascade deletion, then re-enabled in a
    ``finally`` block so it always survives the operation.

    Args:
        icd_id:    UUID of the Icd to delete.
        tenant_id: Active tenant primary key (isolation boundary).

    Raises:
        Icd.DoesNotExist: When no ICD with the given id exists for the tenant.

    req_id: REQ-066, REQ-L2-ICD-001
    leaf_id: COMP-ICD-001
    """
    from django.db import connection

    icd = Icd.objects.get(id=icd_id, tenant_id=tenant_id)

    with connection.cursor() as cursor:
        # Temporarily disable the immutability trigger to allow deletion.
        cursor.execute(
            "ALTER TABLE icd_version DISABLE TRIGGER trg_icd_version_immutable"
        )
        try:
            # Nullify FK to avoid constraint issues, then delete versions.
            icd.current_version = None
            icd.save(update_fields=["current_version"])
            cursor.execute(
                "DELETE FROM icd_version WHERE icd_id = %s",
                [str(icd.id)],
            )
        finally:
            cursor.execute(
                "ALTER TABLE icd_version ENABLE TRIGGER trg_icd_version_immutable"
            )

    # Now delete the ICD itself (no child FK references remain).
    icd.delete()


def create_icd(payload: IcdCreateDTO) -> IcdResult:
    """Create a new ICD with initial version 1 and a 'realizes' TraceLink.

    IF-L1-037 (ApplicationService → IcdManagementSystem).

    Args:
        payload: IcdCreateDTO containing all required fields.

    Returns:
        IcdResult with the persisted Icd and IcdVersion(v1).

    Raises:
        ValueError: Syntax validation failure on the payload.

    req_id: REQ-L2-ICD-001, REQ-L2-ICD-002, REQ-L2-ICD-004
    leaf_id: COMP-ICD-001
    """
    return get_manager().create_icd(payload)


def update_icd(icd_id: uuid.UUID, payload: IcdUpdateDTO) -> IcdResult:
    """Append a new immutable IcdVersion with breaking-change detection.

    IF-L1-037 (ApplicationService → IcdManagementSystem).

    The returned IcdResult.validation_result indicates whether the update
    introduced breaking changes (is_breaking=True). Breaking changes are also
    logged to the AuditLog asynchronously (IF-L1-041).

    Args:
        icd_id:  UUID of the Icd to update.
        payload: IcdUpdateDTO with fields to change (None = keep current).

    Returns:
        IcdResult with the new IcdVersion and validation_result populated.

    Raises:
        Icd.DoesNotExist: When no ICD with the given id is found.
        ValueError: Syntax validation failure on the merged payload.

    req_id: REQ-L2-ICD-001, REQ-L2-ICD-003, REQ-L2-ICD-006
    leaf_id: COMP-ICD-001
    """
    return get_manager().update_icd(icd_id=icd_id, payload=payload)


def validate_compatibility(
    icd_id: uuid.UUID,
    new_payload: dict[str, Any],
) -> ValidationResult:
    """Dry-run compatibility check for a proposed ICD update.

    IF-L1-037. Does NOT persist any data.

    Args:
        icd_id:      UUID of the target Icd.
        new_payload: Dict with proposed contract fields.

    Returns:
        ValidationResult with is_breaking and breaking_changes populated.

    req_id: REQ-L2-ICD-003
    leaf_id: COMP-ICD-001
    """
    return get_manager().validate_compatibility(icd_id=icd_id, new_payload=new_payload)


def get_icd_history(icd_id: uuid.UUID) -> list[IcdVersion]:
    """Return all IcdVersions for the given ICD, oldest-first.

    IF-L1-037 (ApplicationService → IcdManagementSystem).

    Args:
        icd_id: UUID of the target Icd.

    Returns:
        List of IcdVersion objects ordered by version_number ascending.

    req_id: REQ-L2-ICD-001
    leaf_id: COMP-ICD-001
    """
    return get_manager().get_icd_history(icd_id=icd_id)


# ---------------------------------------------------------------------------
# IF-L1-038: BaselineService snapshot
# ---------------------------------------------------------------------------


def get_icd_versions(workspace_id: uuid.UUID) -> list[IcdVersion]:
    """Return the current (latest) IcdVersion for each ICD in a workspace.

    IF-L1-038 (BaselineService → IcdManagementSystem).

    Used by BaselineService to capture a point-in-time snapshot of all
    interface contracts in a workspace. Returns exactly one IcdVersion per
    active ICD (the most recent version).

    Args:
        workspace_id: UUID of the workspace to snapshot.

    Returns:
        List of IcdVersion objects (one per active ICD in the workspace).

    req_id: REQ-L2-ICD-005
    leaf_id: COMP-ICD-001
    """
    return get_manager().get_icd_versions(workspace_id=workspace_id)


# ---------------------------------------------------------------------------
# REQ-L2-VS-004: semantic similarity search
# ---------------------------------------------------------------------------


def find_similar_icds(
    icd_id: uuid.UUID,
    tenant_id: uuid.UUID,
    limit: int = 10,
) -> list[SimilarIcdDTO]:
    """Return the ICDs most semantically similar to *icd_id*.

    IF-L1-037. Cosine-distance nearest-neighbour search over the current
    IcdVersion embeddings, tenant-scoped and excluding the query ICD.

    Raises:
        Icd.DoesNotExist: The query ICD does not exist.
        ValueError: The query ICD's current version has no embedding.
        IcdPgVectorUnavailableError: pgvector package/extension unavailable.

    req_id: REQ-L2-VS-004
    leaf_id: COMP-ICD-001
    """
    return get_manager().find_similar_icds(
        icd_id=icd_id, tenant_id=tenant_id, limit=limit
    )


# ---------------------------------------------------------------------------
# REQ-L2-ICD-002: structured IcdVersion parameters (COMP-ICD-001)
# ---------------------------------------------------------------------------


def create_icd_parameter(
    payload: IcdParameterCreateDTO, tenant_id: uuid.UUID
) -> IcdParameter:
    """Create a structured parameter on an IcdVersion.

    IF-L1-037 (ApplicationService → IcdManagementSystem).

    Args:
        payload: IcdParameterCreateDTO with all fields for the new parameter.
        tenant_id: Active tenant primary key (isolation boundary).

    Returns:
        Persisted IcdParameter instance.

    Raises:
        ValueError: When the parameter name is blank.
        IcdVersion.DoesNotExist: When the target IcdVersion is not found.

    req_id: REQ-L2-ICD-002
    leaf_id: COMP-ICD-001
    """
    return get_parameter_service().create_parameter(
        icd_version_id=payload.icd_version_id,
        name=payload.name,
        tenant_id=tenant_id,
        unit=payload.unit,
        data_type=payload.data_type,
        direction=payload.direction,
        description=payload.description,
        min_value=payload.min_value,
        max_value=payload.max_value,
        nominal_value=payload.nominal_value,
        tolerance=payload.tolerance,
        ordering=payload.ordering,
    )


def update_icd_parameter(
    parameter_id: uuid.UUID,
    payload: IcdParameterUpdateDTO,
    tenant_id: uuid.UUID,
) -> IcdParameter:
    """Update an existing IcdParameter in place (``None`` fields keep current value).

    IF-L1-037 (ApplicationService → IcdManagementSystem).

    Args:
        parameter_id: UUID of the IcdParameter to update.
        payload: IcdParameterUpdateDTO with fields to change.
        tenant_id: Active tenant primary key (isolation boundary).

    Returns:
        Updated IcdParameter instance.

    Raises:
        ValueError: When ``name`` is provided but blank.
        IcdParameterNotFoundError: When no matching parameter exists.

    req_id: REQ-L2-ICD-002
    leaf_id: COMP-ICD-001
    """
    return get_parameter_service().update_parameter(
        parameter_id=parameter_id,
        tenant_id=tenant_id,
        name=payload.name,
        unit=payload.unit,
        data_type=payload.data_type,
        direction=payload.direction,
        description=payload.description,
        min_value=payload.min_value,
        max_value=payload.max_value,
        nominal_value=payload.nominal_value,
        tolerance=payload.tolerance,
        ordering=payload.ordering,
    )


def delete_icd_parameter(parameter_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Delete an IcdParameter.

    IF-L1-037 (ApplicationService → IcdManagementSystem).

    Args:
        parameter_id: UUID of the IcdParameter to delete.
        tenant_id: Active tenant primary key (isolation boundary).

    Raises:
        IcdParameterNotFoundError: When no matching parameter exists.

    req_id: REQ-L2-ICD-002
    leaf_id: COMP-ICD-001
    """
    get_parameter_service().delete_parameter(
        parameter_id=parameter_id, tenant_id=tenant_id
    )


def list_icd_parameters(icd_version_id: uuid.UUID, tenant_id: uuid.UUID):
    """Return all IcdParameters for a given IcdVersion (tenant-scoped).

    IF-L1-037 (ApplicationService → IcdManagementSystem).

    Args:
        icd_version_id: UUID of the target IcdVersion.
        tenant_id: Active tenant primary key (isolation boundary).

    Returns:
        QuerySet of IcdParameter ordered by ``ordering`` then ``name``.

    req_id: REQ-L2-ICD-002
    leaf_id: COMP-ICD-001
    """
    return get_parameter_service().list_parameters(
        icd_version_id=icd_version_id, tenant_id=tenant_id
    )


# ---------------------------------------------------------------------------
# Re-exports for downstream consumers
# ---------------------------------------------------------------------------

__all__ = [
    # Service functions
    "create_icd",
    "get_icd",
    "delete_icd",
    "update_icd",
    "validate_compatibility",
    "get_icd_history",
    "get_icd_versions",
    "find_similar_icds",
    # REQ-L2-ICD-002: IcdParameter CRUD
    "create_icd_parameter",
    "update_icd_parameter",
    "delete_icd_parameter",
    "list_icd_parameters",
    # DTOs re-exported for caller convenience
    "IcdCreateDTO",
    "IcdUpdateDTO",
    "IcdResult",
    "SimilarIcdDTO",
    "IcdPgVectorUnavailableError",
    "ValidationResult",
    "IcdParameterCreateDTO",
    "IcdParameterUpdateDTO",
    "IcdParameterNotFoundError",
    # Model re-exported for type hints
    "IcdVersion",
    "IcdParameter",
]
