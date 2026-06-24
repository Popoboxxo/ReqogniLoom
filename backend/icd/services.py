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
    IcdResult,
    IcdUpdateDTO,
    get_manager,
)
from icd.models import IcdVersion


# ---------------------------------------------------------------------------
# IF-L1-037: ApplicationService CRUD
# ---------------------------------------------------------------------------


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
# Re-exports for downstream consumers
# ---------------------------------------------------------------------------

__all__ = [
    # Service functions
    "create_icd",
    "update_icd",
    "validate_compatibility",
    "get_icd_history",
    "get_icd_versions",
    # DTOs re-exported for caller convenience
    "IcdCreateDTO",
    "IcdUpdateDTO",
    "IcdResult",
    "ValidationResult",
    # Model re-exported for type hints
    "IcdVersion",
]
