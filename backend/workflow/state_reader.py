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

from .definition_store import PRESET_SCHEMAS
from .models import WorkflowItemState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from django.db.models import QuerySet

# Datenmodell-Konsolidierung Phase 1 (Task 12): fixed default-preset key per
# item type, used only to resolve the fallback initial state when
# ``current_state`` returns ``None`` (no ``WorkflowItemState`` row -- the
# item's workspace had no workflow definition when ``workflow/0003``/``0005``
# backfilled it). Mirrors ``workflow.management.commands
# .provision_workflow_definitions._ENTITY_PRESETS`` / ``application
# .workspace_provisioning.WORKFLOW_ENTITY_TYPES`` — kept as its own copy for
# the same "Layer 1 must not import upward from Layer 2" reason documented
# there. ``Requirement``'s own preset is the workspace's rigor tier (minimal/
# standard/extended), but all three share ``"draft"`` as ``states[0]``, so it
# is hardcoded below rather than resolved per-workspace.
#
# Scoped to exactly the nine non-Requirement types whose ``status`` *column*
# Task 12 drops -- used as-is by :data:`STATUS_TRACKED_ITEM_TYPES` below
# (``mcp_server.tools.generic`` needs to know precisely this set, not every
# workflow-tracked type, to decide whether a wire response should carry a
# ``"status"`` key at all).
_DEFAULT_PRESET_BY_ITEM_TYPE: dict[str, str] = {
    "StakeholderNeed": "need_default",
    "TestCase": "testcase_default",
    "Interview": "interview_default",
    "Adr": "adr_default",
    "Risk": "risk_default",
    "Issue": "issue_default",
    "ChangeRequest": "ccb_approval",
    "Goal": "goal_default",
    "MainGoal": "main_goal_default",
}

# Item types tracked by the WorkflowEngine that never had a denormalized
# ``status`` column to begin with (ArchitectureElement/Icd/Diagram/
# GlossaryTerm — see e.g. ``workflow/definition_store.py``'s
# ``architecture_default``/``icd_default`` comments). Kept separate from
# :data:`_DEFAULT_PRESET_BY_ITEM_TYPE` so :data:`STATUS_TRACKED_ITEM_TYPES`
# stays exactly the Task 12 column-drop set — but :func:`initial_state` must
# still resolve these too, because ``rest_api.mixins.workflow_state
# .WorkflowStateSerializerMixin`` (this module's other consumer) serves both
# groups through the identical fallback path.
_COLUMNLESS_PRESET_BY_ITEM_TYPE: dict[str, str] = {
    "ArchitectureElement": "architecture_default",
    "Icd": "icd_default",
    "Diagram": "diagram_default",
    "GlossaryTerm": "glossary_term_default",
}


def current_states(
    item_type: str,
    item_ids: Iterable[UUID | str],
    *,
    tenant_id: UUID | str | None = None,
) -> dict[str, str]:
    """Resolve the current workflow state of many items in one query.

    Args:
        item_type: Entity type string, e.g. ``"Requirement"``.
        item_ids:  Item UUIDs (or their string form).
        tenant_id: When given, queries via the ``unscoped`` manager with an
                   explicit tenant filter — for call sites that run outside a
                   request-scoped ``TenantContext`` and already do explicit
                   tenant filtering (mirrors :func:`item_ids_in_state`).
                   When ``None`` (default), uses the tenant-scoped ``objects``
                   manager, which relies on the active thread-local
                   ``TenantContext``. Keyword-only so it cannot be passed
                   positionally into a cross-tenant read.

    Returns:
        Mapping ``str(item_id) -> current_state``. Items without a
        ``WorkflowItemState`` row are **absent** from the mapping (not mapped to
        ``None``), so callers decide their own fallback.
    """
    ids = [str(item_id) for item_id in item_ids]
    if not ids:
        return {}
    if tenant_id is not None:
        manager = WorkflowItemState.unscoped.filter(tenant_id=tenant_id)
    else:
        manager = WorkflowItemState.objects
    rows = manager.filter(item_type=item_type, item_id__in=ids).values_list(
        "item_id", "current_state"
    )
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


def initial_state(item_type: str) -> str:
    """Return *item_type*'s fixed default-preset initial state.

    Datenmodell-Konsolidierung Phase 1 (Task 12): fallback for
    ``current_state``/``current_states`` returning nothing. Before Task 12 an
    item with no ``WorkflowItemState`` row fell back to its (now-dropped)
    ``status`` column, which still carried its true legacy value. That column
    is gone, so such a row can no longer report its legacy value — it reports
    its type's initial state instead. This is an explicit, reviewed
    data-loss tradeoff (see the Task 12 report, Finding 2 resolution), not a
    bug: it only affects items whose workspace had no workflow definition
    provisioned when ``workflow/0003``/``0005`` backfilled
    ``WorkflowItemState``.

    Also resolves the four column-less types
    (:data:`_COLUMNLESS_PRESET_BY_ITEM_TYPE`) for
    ``rest_api.mixins.workflow_state.WorkflowStateSerializerMixin``, which
    serves both groups through this same fallback path.

    Args:
        item_type: Entity type string, e.g. ``"Requirement"`` or ``"Adr"``.
            ``"Requirement"`` always resolves to ``"draft"`` — the workspace's
            rigor tier (minimal/standard/extended) governs its live
            transitions, but all three presets share ``"draft"`` as their
            first state.

    Returns:
        The state name.
    """
    if item_type == "Requirement":
        return "draft"
    preset_key = _DEFAULT_PRESET_BY_ITEM_TYPE.get(item_type) or _COLUMNLESS_PRESET_BY_ITEM_TYPE[
        item_type
    ]
    return PRESET_SCHEMAS[preset_key]["states"][0]


#: The full set of item types :func:`initial_state` can resolve -- i.e. every
#: type that carries a status/lifecycle-state concept at all (the ten types
#: whose ``status`` column Task 12 dropped). For callers that used to detect
#: "does this entity have a status" by checking for a ``status`` key/column on
#: the ORM row (now unreliable -- the column, and therefore any
#: ``obj.__dict__``-driven introspection of it, is gone) and must switch to a
#: static membership check instead (e.g.
#: ``mcp_server.tools.generic.GenericCrudToolGroup._to_dict``).
STATUS_TRACKED_ITEM_TYPES = frozenset({"Requirement", *_DEFAULT_PRESET_BY_ITEM_TYPE})

__all__ = [
    "current_state",
    "current_states",
    "initial_state",
    "item_ids_in_state",
    "STATUS_TRACKED_ITEM_TYPES",
]
