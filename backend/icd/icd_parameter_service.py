"""
IcdManagement — IcdParameterService (structured interface parameters).

leaf_id: COMP-ICD-001
req_id:  REQ-L2-ICD-002
arch_id: ARCH-L1-014

CRUD for :class:`icd.models.IcdParameter` — structured, version-specific
interface parameters that extend the free-text pre/post/invariant JSON lists
on :class:`icd.models.IcdVersion` with typed values (unit, data_type,
direction, min/max bounds, tolerance).

Parameters are attached to a concrete IcdVersion. IcdVersion rows themselves
are immutable (DB trigger, ADR-ICD-01), but IcdParameter rows are NOT under
that trigger — they may be added/edited/removed within the lifetime of a
version to correct structured metadata without forcing a new contract
revision. Mirrors the tenant-scoping convention used by
:mod:`icd.icd_manager` (explicit ``tenant_id`` argument + ``unscoped``
manager, rather than relying solely on thread-local ``TenantContext``).

External interfaces served:
  IF-L1-037 (ApplicationService CRUD) — REST layer (rest_api/icd_views.py)
IF-L1-040 (PersistenceLayer via Django ORM save/query)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db.models import QuerySet

from icd.models import IcdParameter, IcdVersion


@dataclass
class IcdParameterCreateDTO:
    """Input payload for creating a new IcdParameter (REQ-L2-ICD-002)."""

    icd_version_id: uuid.UUID
    name: str
    unit: str = ""
    data_type: str = "other"
    direction: str = "input"
    description: str = ""
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    nominal_value: str = ""
    tolerance: str = ""
    ordering: int = 0


@dataclass
class IcdParameterUpdateDTO:
    """Input payload for updating an IcdParameter (``None`` = keep current value)."""

    name: Optional[str] = None
    unit: Optional[str] = None
    data_type: Optional[str] = None
    direction: Optional[str] = None
    description: Optional[str] = None
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    nominal_value: Optional[str] = None
    tolerance: Optional[str] = None
    ordering: Optional[int] = None


class IcdParameterNotFoundError(LookupError):
    """Raised when a requested IcdParameter does not exist (tenant-scoped)."""


# ---------------------------------------------------------------------------
# COMP-ICD-001: IcdParameterService
# ---------------------------------------------------------------------------


class IcdParameterService:
    """CRUD for structured IcdVersion parameters (REQ-L2-ICD-002).

    leaf_id: COMP-ICD-001
    req_id:  REQ-L2-ICD-002
    """

    def create_parameter(
        self,
        icd_version_id: uuid.UUID,
        name: str,
        tenant_id: uuid.UUID,
        unit: str = "",
        data_type: str = "other",
        direction: str = "input",
        description: str = "",
        min_value: Optional[Decimal] = None,
        max_value: Optional[Decimal] = None,
        nominal_value: str = "",
        tolerance: str = "",
        ordering: int = 0,
    ) -> IcdParameter:
        """Create a structured parameter on an IcdVersion.

        Args:
            icd_version_id: UUID of the target IcdVersion.
            name: Parameter name (required).
            tenant_id: Active tenant primary key (isolation boundary).
            unit: Physical/logical unit (e.g. "V", "m/s"), optional.
            data_type: One of IcdParameterDataType choices.
            direction: One of IcdParameterDirection choices.
            description: Optional free-text description.
            min_value: Optional numeric lower bound.
            max_value: Optional numeric upper bound.
            nominal_value: Optional symbolic/default value (enum/string types).
            tolerance: Optional free-text tolerance (e.g. "±5%").
            ordering: Display order within the version's parameter list.

        Returns:
            Persisted IcdParameter instance.

        Raises:
            ValueError: When ``name`` is blank.
            IcdVersion.DoesNotExist: When the IcdVersion is not found for
                the given tenant.

        req_id: REQ-L2-ICD-002
        """
        if not name or not name.strip():
            raise ValueError("IcdParameter name is required")

        version = IcdVersion.unscoped.filter(
            id=icd_version_id, tenant_id=tenant_id
        ).first()
        if version is None:
            raise IcdVersion.DoesNotExist(f"IcdVersion {icd_version_id} not found")

        parameter = IcdParameter(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            icd_version=version,
            name=name.strip(),
            unit=unit,
            data_type=data_type,
            direction=direction,
            description=description,
            min_value=min_value,
            max_value=max_value,
            nominal_value=nominal_value,
            tolerance=tolerance,
            ordering=ordering,
        )
        parameter.save()
        return parameter

    def update_parameter(
        self,
        parameter_id: uuid.UUID,
        tenant_id: uuid.UUID,
        name: Optional[str] = None,
        unit: Optional[str] = None,
        data_type: Optional[str] = None,
        direction: Optional[str] = None,
        description: Optional[str] = None,
        min_value: Optional[Decimal] = None,
        max_value: Optional[Decimal] = None,
        nominal_value: Optional[str] = None,
        tolerance: Optional[str] = None,
        ordering: Optional[int] = None,
    ) -> IcdParameter:
        """Update an existing IcdParameter in place (fields default to unchanged).

        Args:
            parameter_id: UUID of the IcdParameter to update.
            tenant_id: Active tenant primary key (isolation boundary).
            name: New name (optional).
            unit: New unit (optional).
            data_type: New data type (optional).
            direction: New direction (optional).
            description: New description (optional).
            min_value: New lower bound (optional).
            max_value: New upper bound (optional).
            nominal_value: New nominal value (optional).
            tolerance: New tolerance text (optional).
            ordering: New display order (optional).

        Returns:
            Updated IcdParameter instance.

        Raises:
            ValueError: When ``name`` is provided but blank.
            IcdParameterNotFoundError: When no matching parameter exists for
                the given tenant.

        req_id: REQ-L2-ICD-002
        """
        parameter = IcdParameter.unscoped.filter(
            id=parameter_id, tenant_id=tenant_id
        ).first()
        if parameter is None:
            raise IcdParameterNotFoundError(f"IcdParameter {parameter_id} not found")

        if name is not None:
            if not name.strip():
                raise ValueError("IcdParameter name is required")
            parameter.name = name.strip()
        if unit is not None:
            parameter.unit = unit
        if data_type is not None:
            parameter.data_type = data_type
        if direction is not None:
            parameter.direction = direction
        if description is not None:
            parameter.description = description
        if min_value is not None:
            parameter.min_value = min_value
        if max_value is not None:
            parameter.max_value = max_value
        if nominal_value is not None:
            parameter.nominal_value = nominal_value
        if tolerance is not None:
            parameter.tolerance = tolerance
        if ordering is not None:
            parameter.ordering = ordering

        parameter.save()
        return parameter

    def delete_parameter(self, parameter_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Delete an IcdParameter (hard delete — no TraceLink/audit fan-out).

        Args:
            parameter_id: UUID of the IcdParameter to delete.
            tenant_id: Active tenant primary key (isolation boundary).

        Raises:
            IcdParameterNotFoundError: When no matching parameter exists for
                the given tenant.

        req_id: REQ-L2-ICD-002
        """
        parameter = IcdParameter.unscoped.filter(
            id=parameter_id, tenant_id=tenant_id
        ).first()
        if parameter is None:
            raise IcdParameterNotFoundError(f"IcdParameter {parameter_id} not found")
        parameter.delete()

    def list_parameters(
        self, icd_version_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> QuerySet[IcdParameter]:
        """Return all IcdParameters for a given IcdVersion (tenant-scoped).

        Args:
            icd_version_id: UUID of the target IcdVersion.
            tenant_id: Active tenant primary key (isolation boundary).

        Returns:
            QuerySet of IcdParameter, ordered by ``ordering`` then ``name``
            (mirrors ``IcdParameter.Meta.ordering``).

        req_id: REQ-L2-ICD-002
        """
        return IcdParameter.unscoped.filter(
            icd_version_id=icd_version_id, tenant_id=tenant_id
        ).order_by("ordering", "name")


# Module-level singleton — mirrors icd_manager.get_manager()
_service = IcdParameterService()


def get_parameter_service() -> IcdParameterService:
    """Return the module-level IcdParameterService singleton.

    leaf_id: COMP-ICD-001
    """
    return _service


__all__ = [
    "IcdParameterService",
    "IcdParameterCreateDTO",
    "IcdParameterUpdateDTO",
    "IcdParameterNotFoundError",
    "get_parameter_service",
]
