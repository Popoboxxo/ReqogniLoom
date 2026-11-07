"""Flat allocation list (P2 Task 2.9): ``GET /api/v1/allocations/``.

One row per Requirement with its allocation target, tier and intent. Kept as a
service (not a ViewSet ORM query) so REST and MCP share one read model.
"""
from __future__ import annotations

from uuid import UUID

from application.base import ServiceBase, ValidationError
from auth_tenancy.context import AuthContext
from persistence.models import ArchitectureElement, Requirement, TraceLink


class AllocationQueryService(ServiceBase):
    """Read flat requirement/allocation rows for one workspace."""

    def list(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        *,
        requirement: UUID | None = None,
        element: UUID | None = None,
        allocated: bool | None = None,
        tier: str | None = None,
        level: int | None = None,
        intent: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        self._set_tenant_context(ctx)
        if limit < 1 or limit > 500:
            raise ValidationError("limit must be between 1 and 500")
        if offset < 0:
            raise ValidationError("offset must be >= 0")

        requirements = list(
            Requirement.objects.filter(workspace_id=workspace_id).values(
                "id",
                "artifact_id",
                "title",
                "uid",
                "level",
                "tier_key",
                "level_source",
                "allocation_intent",
            )
        )
        if not requirements:
            return {
                "results": [],
                "meta": {
                    "total": 0,
                    "allocated": 0,
                    "unallocated": 0,
                    "not_allocatable": 0,
                    "limit": limit,
                    "offset": offset,
                },
            }

        artifact_ids = [row["artifact_id"] for row in requirements]
        allocation_by_artifact = {
            source_id: target_id
            for source_id, target_id in TraceLink.objects.filter(
                link_type="allocated-to", source_id__in=artifact_ids
            ).values_list("source_id", "target_id")
        }
        element_by_artifact = {
            artifact_id: (element_id, title)
            for element_id, artifact_id, title in ArchitectureElement.objects.filter(
                artifact_id__in=set(allocation_by_artifact.values())
            ).values_list("id", "artifact_id", "title")
        }

        rows = []
        for req in requirements:
            target = allocation_by_artifact.get(req["artifact_id"])
            element_row = element_by_artifact.get(target) if target else None
            rows.append(
                {
                    "requirement_id": str(req["id"]),
                    "artifact_id": str(req["artifact_id"]),
                    "title": req["title"],
                    "uid": req["uid"],
                    "tier_key": req["tier_key"],
                    "level": req["level"],
                    "level_source": req["level_source"],
                    "allocation_intent": req["allocation_intent"],
                    "allocated": target is not None,
                    "element_id": str(element_row[0]) if element_row else None,
                    "element_title": element_row[1] if element_row else None,
                }
            )

        def matches(row: dict) -> bool:
            if requirement is not None and row["requirement_id"] != str(requirement):
                return False
            if element is not None and row["element_id"] != str(element):
                return False
            if allocated is not None and row["allocated"] is not allocated:
                return False
            if tier is not None and row["tier_key"] != tier:
                return False
            if level is not None and row["level"] != level:
                return False
            if intent is not None and row["allocation_intent"] != intent:
                return False
            return True

        filtered = [row for row in rows if matches(row)]
        return {
            "results": filtered[offset : offset + limit],
            "meta": {
                "total": len(filtered),
                "allocated": sum(1 for row in filtered if row["allocated"]),
                "unallocated": sum(1 for row in filtered if not row["allocated"]),
                "not_allocatable": sum(
                    1
                    for row in filtered
                    if row["allocation_intent"] == "not_allocatable"
                ),
                "limit": limit,
                "offset": offset,
            },
        }
