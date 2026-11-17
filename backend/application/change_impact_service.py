"""Persistence queries for the MCP ``context.change_impact`` tool (ADR-01 façade).

R2S-003 boundary fix: ``mcp_server/tools/cross_cutting.py`` used to perform
four function-local ``persistence.models`` imports and four ``.objects``
queries inside the change-impact handler and its helpers, and armed
``TenantContext`` itself.  This module owns all of that in Layer 2; the MCP
tool consumes plain DTOs and never imports a persistence model.

Behaviour contract
------------------
Every query is a verbatim relocation of the former inline tool query —
tenant filters, ``order_by``/slice behaviour, ``values()`` projections and
the ``NOT_FOUND`` decision (signalled by ``None`` for the anchor) are
unchanged.  Tenant fencing is preserved exactly: the anchor lookup still
arms ``TenantContext.set_tenant(tenant_id)`` and filters on ``tenant_id``.

Rollout flag
------------
The tool's call sites use
:func:`application.user_query_service.service_backed_queries_enabled`; the
``legacy_*`` functions here are the relocated originals and the
:class:`ChangeImpactService` façade delegates to them, so both paths yield
byte-identical ``ToolResult`` payloads.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from persistence.models import (
    ArchitectureElement,
    Requirement,
    StakeholderNeed,
    TestCase,
)
from persistence.tenancy import TenantContext

#: ``entity_type`` -> model, for the anchor lookup (former tool-local dict).
_ANCHOR_MODELS: dict[str, Any] = {
    "Requirement": Requirement,
    "ArchitectureElement": ArchitectureElement,
    "TestCase": TestCase,
    "StakeholderNeed": StakeholderNeed,
}

#: Mirrored entity types resolved via ``WorkflowItemState`` (former dict).
_MIRRORED_MODELS: dict[str, Any] = {
    "Requirement": Requirement,
    "TestCase": TestCase,
    "StakeholderNeed": StakeholderNeed,
}


# ---------------------------------------------------------------------------
# Canonical queries — verbatim relocations of the former tool-layer queries
# ---------------------------------------------------------------------------


def legacy_get_anchor(
    entity_type: str, entity_id: UUID, *, tenant_id: UUID
) -> Any | None:
    """Load the change-impact anchor entity, or ``None`` when absent.

    Relocated from ``_handle_change_impact``.  The ``TenantContext`` arming
    and the explicit ``tenant_id`` filter are preserved unchanged — callers
    map ``None`` to the exact former ``NOT_FOUND`` error.
    """
    model = _ANCHOR_MODELS[entity_type]

    TenantContext.set_tenant(tenant_id)
    try:
        return model.objects.get(id=entity_id, tenant_id=tenant_id)
    except model.DoesNotExist:
        return None


def legacy_decomposition_children(
    entity_id: UUID, *, tenant_id: UUID
) -> list[dict[str, Any]]:
    """Return raw neighbour dicts for an ArchitectureElement's FK children.

    Relocated from ``_gather_change_impact_neighbors``.  The decomposition
    tree is a plain FK relation, not a TraceLink, hence the synthetic
    ``decomposes`` neighbour records.
    """
    children: list[dict[str, Any]] = []
    for child in ArchitectureElement.objects.filter(
        parent_id=entity_id, tenant_id=tenant_id
    ):
        children.append(
            {
                "artifact_id": child.artifact_id,
                "entity_type": "ArchitectureElement",
                "link_type": "decomposes",
                "relation": "child",
            }
        )
    return children


def legacy_resolve_mirrored_neighbors(
    neighbors: list[dict[str, Any]], type_name: str
) -> list[dict[str, Any]]:
    """Resolve mirrored-type neighbours to business DTOs.

    Relocated from ``_resolve_mirrored_change_impact_neighbors``.  Status is
    read through ``WorkflowItemState`` with the frozen ``status`` column's
    initial-state fallback (Task 12 data-loss tradeoff); the ``status``
    column is intentionally absent from the ``values()`` projection.
    """
    from workflow import state_reader

    model = _MIRRORED_MODELS[type_name]
    artifact_ids = [neighbor["artifact_id"] for neighbor in neighbors]
    rows_by_artifact = {
        row["artifact_id"]: row
        for row in model.objects.filter(artifact_id__in=artifact_ids).values(
            "id", "artifact_id", "title"
        )
    }
    states = state_reader.current_states(
        type_name, (row["id"] for row in rows_by_artifact.values())
    )
    type_initial_state = state_reader.initial_state(type_name)

    resolved: list[dict[str, Any]] = []
    for neighbor in neighbors:
        row = rows_by_artifact.get(neighbor["artifact_id"])
        if row is None:
            continue
        resolved_status = states.get(str(row["id"])) or type_initial_state
        resolved.append(
            {
                "id": str(row["id"]),
                "entity_type": type_name,
                "title": row["title"],
                "link_type": neighbor["link_type"],
                "relation": neighbor["relation"],
                "outdated": resolved_status == "outdated",
            }
        )
    return resolved


def legacy_resolve_architecture_neighbors(
    neighbors: list[dict[str, Any]], *, tenant_id: UUID
) -> list[dict[str, Any]]:
    """Resolve ArchitectureElement neighbours to business DTOs.

    Relocated from ``_resolve_architecture_change_impact_neighbors``.
    ArchitectureElement has no ``status`` column; ``outdated`` comes solely
    from ``WorkflowItemState`` via ``workflow.services.outdated_item_ids``.
    """
    from workflow.services import outdated_item_ids

    artifact_ids = [neighbor["artifact_id"] for neighbor in neighbors]
    outdated_ids = set(
        outdated_item_ids("ArchitectureElement", tenant_id=tenant_id)
    )
    rows_by_artifact = {
        row["artifact_id"]: row
        for row in ArchitectureElement.objects.filter(
            artifact_id__in=artifact_ids
        ).values("id", "artifact_id", "title")
    }

    resolved: list[dict[str, Any]] = []
    for neighbor in neighbors:
        row = rows_by_artifact.get(neighbor["artifact_id"])
        if row is None:
            continue
        resolved.append(
            {
                "id": str(row["id"]),
                "entity_type": "ArchitectureElement",
                "title": row["title"],
                "link_type": neighbor["link_type"],
                "relation": neighbor["relation"],
                "outdated": row["id"] in outdated_ids,
            }
        )
    return resolved


class ChangeImpactService:
    """ADR-01 façade over the relocated change-impact queries.

    Delegates to the ``legacy_*`` functions so the service-backed path is
    byte-identical to the legacy path by construction.
    """

    def get_anchor(
        self, entity_type: str, entity_id: UUID, *, tenant_id: UUID
    ) -> Any | None:
        """Return the anchor entity, or ``None`` when it does not exist."""
        return legacy_get_anchor(entity_type, entity_id, tenant_id=tenant_id)

    def decomposition_children(
        self, entity_id: UUID, *, tenant_id: UUID
    ) -> list[dict[str, Any]]:
        """Return raw neighbour dicts for an anchor's FK children."""
        return legacy_decomposition_children(entity_id, tenant_id=tenant_id)

    def resolve_mirrored_neighbors(
        self, neighbors: list[dict[str, Any]], type_name: str
    ) -> list[dict[str, Any]]:
        """Resolve mirrored-type neighbours to business DTOs."""
        return legacy_resolve_mirrored_neighbors(neighbors, type_name)

    def resolve_architecture_neighbors(
        self, neighbors: list[dict[str, Any]], *, tenant_id: UUID
    ) -> list[dict[str, Any]]:
        """Resolve ArchitectureElement neighbours to business DTOs."""
        return legacy_resolve_architecture_neighbors(
            neighbors, tenant_id=tenant_id
        )
