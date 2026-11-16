"""Shared ``allocated`` / ``level`` filter expressions (Tabellenansicht S1).

``?allocated=`` and ``?level=`` were implemented inline in
:meth:`application.requirement_service.RequirementService.list_requirements`.
The table filter DSL exposes the same two values under the same names as
*pseudo-fields* on the ``Requirement`` table (plan O2), and consumer and table
must answer with exactly the same rows — so the expression is defined once,
here, and both call sites import it.

``allocated`` reads the ``allocated-to`` trace links (Requirement → Element),
so its ``source_id`` is the Requirement's backing ``Artifact`` id (#1668).
``level`` is the V-model cascade level column (derived, ADR-005; a manual
override via #1289 does not change the column's meaning).
"""
from __future__ import annotations

from uuid import UUID

from django.db.models import Q

__all__ = ["allocated_q", "level_q"]


def allocated_q(*, allocated: bool, tenant_id: UUID) -> Q:
    """Return the ``Q`` matching allocated (``True``) or unallocated rows.

    Args:
        allocated: ``True`` keeps only rows with at least one ``allocated-to``
            link, ``False`` keeps only rows without one.
        tenant_id: Tenant whose link rows are consulted. Explicit because the
            table query may run outside a request-scoped tenant context
            (``TraceLink.unscoped``).

    Returns:
        A ``Q`` on the Requirement queryset (``artifact_id`` based).
    """
    from persistence.models import TraceLink

    allocated_artifact_ids = TraceLink.unscoped.filter(
        tenant_id=tenant_id,
        link_type="allocated-to",
    ).values_list("source_id", flat=True)
    if allocated:
        return Q(artifact_id__in=allocated_artifact_ids)
    return ~Q(artifact_id__in=allocated_artifact_ids)


def level_q(level: int) -> Q:
    """Return the ``Q`` matching one V-model cascade level (1..4)."""
    return Q(level=level)
