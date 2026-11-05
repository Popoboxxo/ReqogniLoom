"""Flat allocation view for the connection-view renderers (P3, V10/B9).

One paged read object feeds every renderer (tree with requirements, two
columns, matrix, card graph): a flat row per Requirement and per
ArchitectureElement, with the fields a renderer needs. Pagination is
``page_size`` (default 200, max 500); counters are computed over the filtered
set, never over the page.
"""
from __future__ import annotations

from uuid import UUID

from application.base import ServiceBase, ValidationError
from application.tier_ladder_service import TierLadderService
from auth_tenancy.context import AuthContext
from persistence.models import ArchitectureElement, Artifact, Requirement, TraceLink
from workflow import state_reader

_OPEN_FINAL_STATES = frozenset(
    {"approved", "done", "closed", "Freigegeben", "Abgelöst", "Archiviert"}
)


class AllocationViewService(ServiceBase):
    """Return the flat allocation view for one workspace."""

    def list(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        *,
        allocated: bool | None = None,
        intent: str | None = None,
        tier: str | None = None,
        type: str | None = None,
        category: str | None = None,
        state: str | None = None,
        element_subtree: UUID | None = None,
        q: str | None = None,
        open: bool | None = None,
        page_size: int = 200,
        offset: int = 0,
    ) -> dict:
        self._set_tenant_context(ctx)
        if page_size < 1 or page_size > 500:
            raise ValidationError("page_size must be between 1 and 500")
        if offset < 0:
            raise ValidationError("offset must be >= 0")

        ladder = TierLadderService().get(workspace_id)
        names = {
            entry.tier_key: (entry.name or {}).get("en")
            or (entry.name or {}).get("de")
            or entry.tier_key
            for entry in ladder.entries
        }

        elements = list(
            ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id).values(
                "id", "artifact_id", "parent_id", "title", "element_type"
            )
        )
        children: dict[UUID, list[UUID]] = {}
        element_by_id = {row["id"]: row for row in elements}
        element_by_artifact = {row["artifact_id"]: row for row in elements}
        for row in elements:
            if row["parent_id"] is not None:
                children.setdefault(row["parent_id"], []).append(row["id"])

        subtree_ids: set[UUID] | None = None
        if element_subtree is not None:
            subtree_ids = set()
            frontier = [element_subtree]
            while frontier:
                current = frontier.pop()
                if current in subtree_ids:
                    continue
                subtree_ids.add(current)
                frontier.extend(children.get(current, ()))

        requirements = list(
            Requirement.objects.filter(workspace_id=workspace_id).values(
                "id",
                "artifact_id",
                "title",
                "type",
                "category",
                "level",
                "tier_key",
                "level_source",
                "allocation_intent",
            )
        )
        artifact_rows = {
            row["id"]: row
            for row in Artifact.unscoped.filter(
                id__in=[req["artifact_id"] for req in requirements]
            ).values("id", "parent_id", "sort_key")
        }
        allocation_by_artifact = {
            source_id: target_id
            for source_id, target_id in TraceLink.objects.filter(
                link_type="allocated-to",
                source_id__in=[req["artifact_id"] for req in requirements],
            ).values_list("source_id", "target_id")
        }
        states = state_reader.current_states(
            "Requirement", (req["id"] for req in requirements)
        )

        def _requirement_row(req: dict) -> dict:
            target = allocation_by_artifact.get(req["artifact_id"])
            element = element_by_artifact.get(target) if target else None
            artifact = artifact_rows.get(req["artifact_id"], {})
            current_state = states.get(str(req["id"])) or "draft"
            return {
                "kind": "requirement",
                "id": str(req["id"]),
                "artifact_id": str(req["artifact_id"]),
                "parent_id": (
                    str(artifact.get("parent_id")) if artifact.get("parent_id") else None
                ),
                "sort_key": artifact.get("sort_key"),
                "title": req["title"],
                "state": current_state,
                "tier_key": req["tier_key"],
                "tier_name": names.get(req["tier_key"]),
                "level": req["level"],
                "type": req["type"],
                "category": req["category"],
                "allocated_to": str(target) if target else None,
                "element_id": str(element["id"]) if element else None,
                "allocation_intent": req["allocation_intent"],
                "locked": None,
                "findings": [],
                "group": None,
            }

        def _element_row(row: dict) -> dict:
            return {
                "kind": "element",
                "id": str(row["id"]),
                "artifact_id": str(row["artifact_id"]),
                "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
                "sort_key": None,
                "title": row["title"],
                "state": None,
                "tier_key": None,
                "tier_name": None,
                "level": None,
                "type": row["element_type"],
                "category": None,
                "allocated_to": None,
                "element_id": str(row["id"]),
                "allocation_intent": None,
                "locked": None,
                "findings": [],
                "group": None,
            }

        rows = [_requirement_row(req) for req in requirements]
        rows.extend(_element_row(row) for row in elements)

        def matches(row: dict) -> bool:
            if row["kind"] == "requirement":
                if allocated is not None and (row["allocated_to"] is not None) is not allocated:
                    return False
                if intent is not None and row["allocation_intent"] != intent:
                    return False
                if category is not None and row["category"] != category:
                    return False
                if open is not None:
                    is_open = row["state"] not in _OPEN_FINAL_STATES
                    if is_open is not open:
                        return False
                if (
                    element_subtree is not None
                    and (row["element_id"] is None or UUID(row["element_id"]) not in subtree_ids)
                ):
                    return False
            else:
                if allocated is not None or intent is not None or category is not None:
                    return False
                if open is not None:
                    return False
                if element_subtree is not None and row["id"] not in {
                    str(value) for value in subtree_ids or set()
                }:
                    return False
            if tier is not None and row["tier_key"] != tier:
                return False
            if type is not None and row["type"] != type:
                return False
            if state is not None and row["state"] != state:
                return False
            if q is not None and q.lower() not in (row["title"] or "").lower():
                return False
            return True

        filtered = [row for row in rows if matches(row)]
        return {
            "results": filtered[offset : offset + page_size],
            "meta": {
                "total": len(filtered),
                "unallocated": sum(
                    1
                    for row in filtered
                    if row["kind"] == "requirement" and row["allocated_to"] is None
                ),
                "locked": sum(1 for row in filtered if row["locked"] is not None),
                "findings": sum(len(row["findings"]) for row in filtered),
                "page_size": page_size,
                "offset": offset,
            },
        }
