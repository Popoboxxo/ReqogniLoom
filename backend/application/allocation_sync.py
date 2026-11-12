"""Dual-write helper: keep ``Allocation`` and the ``allocated-to`` edge in sync.

ADR-028: the edge stays the graph truth (coverage, baselines, audit, MCP read
it), the object carries status/release/primary. Every writer of an
``allocated-to`` edge goes through one of the two helpers here, so the
invariant "active allocation <-> edge" holds for the service paths.

``revoked`` rows are the archive: revoking removes the edge and keeps the row
for the audit trail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from persistence.models import Allocation


def sync_allocation_for_edge(
    *,
    requirement_artifact_id: UUID,
    element_artifact_id: UUID,
    tenant_id: UUID | None = None,
) -> "Allocation | None":
    """Create (or return) the active allocation behind a new edge.

    Returns ``None`` when the requirement artifact has no workspace row yet —
    a defensive branch for half-created artifacts during imports; the edge then
    exists without a status and the consistency check reports it.
    """
    from persistence.models import Allocation, AllocationStatus, Artifact

    # ``unscoped`` on purpose: the caller may run without a thread-local tenant
    # (unit tests, import bootstrap) while the link row already carries the
    # tenant. Filtering by ``tenant_id`` keeps the read tenant-safe.
    artifacts = Artifact.unscoped.filter(id=requirement_artifact_id)
    if tenant_id is not None:
        artifacts = artifacts.filter(tenant_id=tenant_id)
    requirement_artifact = artifacts.only("id", "tenant_id", "workspace_id").first()
    if requirement_artifact is None:
        return None

    active = [AllocationStatus.DRAFT, AllocationStatus.RELEASED]
    existing = Allocation.objects.filter(
        requirement_artifact_id=requirement_artifact_id,
        element_artifact_id=element_artifact_id,
        status__in=active,
    ).first()
    if existing is not None:
        return existing

    from django.db import IntegrityError, transaction

    try:
        with transaction.atomic():
            return Allocation.objects.create(
                tenant_id=requirement_artifact.tenant_id,
                workspace_id=requirement_artifact.workspace_id,
                requirement_artifact_id=requirement_artifact_id,
                element_artifact_id=element_artifact_id,
                status=AllocationStatus.DRAFT,
                is_primary=True,
            )
    except IntegrityError:
        # A concurrent writer won the unique constraint: return its row.
        return Allocation.objects.filter(
            requirement_artifact_id=requirement_artifact_id,
            element_artifact_id=element_artifact_id,
            status__in=active,
        ).first()


def revoke_allocation_for_edge(
    *,
    requirement_artifact_id: UUID,
    element_artifact_id: UUID,
    reason: str,
) -> int:
    """Archive the active allocation behind a removed edge. Returns row count."""
    from django.utils import timezone

    from persistence.models import Allocation, AllocationStatus

    return Allocation.objects.filter(
        requirement_artifact_id=requirement_artifact_id,
        element_artifact_id=element_artifact_id,
        status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
    ).update(
        status=AllocationStatus.REVOKED,
        revoked_at=timezone.now(),
        revocation_reason=reason,
        is_primary=False,
    )


def revoke_allocations_for_requirement(
    *, requirement_artifact_id: UUID, reason: str
) -> int:
    """Archive every active allocation of one requirement (replace/deallocate)."""
    from django.utils import timezone

    from persistence.models import Allocation, AllocationStatus

    return Allocation.objects.filter(
        requirement_artifact_id=requirement_artifact_id,
        status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
    ).update(
        status=AllocationStatus.REVOKED,
        revoked_at=timezone.now(),
        revocation_reason=reason,
        is_primary=False,
    )
