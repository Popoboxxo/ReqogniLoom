"""Read-only seam over ``WorkflowItemState`` (Datenmodell-Konsolidierung Phase 0).

Every consumer that previously read a denormalized ``status`` column reads
through this module instead. Keeping the resolution in one place is what makes
dropping those columns (Phase 1) a mechanical change rather than an audit of
every reader.

Tenant isolation: all queries go through ``WorkflowItemState.objects``, the
tenant-scoped manager, so an active ``TenantContext`` is required — exactly like
every other Layer-1 read. ``item_ids_in_state`` additionally accepts an explicit
``tenant_id`` for callers that already hold one (mirrors
``workflow.services.outdated_item_ids``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable
from uuid import UUID

from .models import WorkflowItemState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from django.db.models import QuerySet


def current_states(
    item_type: str, item_ids: Iterable[UUID | str]
) -> dict[str, str]:
    """Resolve the current workflow state of many items in one query.

    Args:
        item_type: Entity type string, e.g. ``"Requirement"``.
        item_ids:  Item UUIDs (or their string form).

    Returns:
        Mapping ``str(item_id) -> current_state``. Items without a
        ``WorkflowItemState`` row are **absent** from the mapping (not mapped to
        ``None``), so callers decide their own fallback.
    """
    ids = [str(item_id) for item_id in item_ids]
    if not ids:
        return {}
    rows = WorkflowItemState.objects.filter(
        item_type=item_type, item_id__in=ids
    ).values_list("item_id", "current_state")
    return {str(item_id): state for item_id, state in rows}


def current_state(item_type: str, item_id: UUID | str) -> str | None:
    """Resolve the current workflow state of a single item.

    Returns:
        The state name, or ``None`` if the item has no ``WorkflowItemState``.
    """
    return current_states(item_type, [item_id]).get(str(item_id))


def item_ids_in_state(
    item_type: str, state: str, *, tenant_id: UUID | str | None = None
) -> "QuerySet[UUID]":
    """Return the ``item_id`` values of *item_type* currently in *state*.

    Matches the state name literally — no ``state_meta`` interpretation (same
    contract as ``workflow.services.outdated_item_ids``).

    Args:
        item_type: Entity type string.
        state:     Exact state name to match.
        tenant_id: When given, queries via the ``unscoped`` manager with an
                   explicit tenant filter — for call sites that run outside a
                   request-scoped ``TenantContext`` and already do explicit
                   tenant filtering (mirrors ``workflow.services.outdated_item_ids``).
                   When ``None`` (default), uses the tenant-scoped ``objects``
                   manager, which relies on the active thread-local
                   ``TenantContext``. Keyword-only so it cannot be passed
                   positionally into a cross-tenant read.

    Returns:
        Lazy ``QuerySet`` of ``item_id`` UUIDs, usable as an ``__in`` subquery.
    """
    if tenant_id is not None:
        qs = WorkflowItemState.unscoped.filter(
            tenant_id=tenant_id, item_type=item_type, current_state=state
        )
    else:
        qs = WorkflowItemState.objects.filter(item_type=item_type, current_state=state)
    return qs.values_list("item_id", flat=True)


__all__ = ["current_state", "current_states", "item_ids_in_state"]
