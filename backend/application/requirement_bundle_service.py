"""COMP-AS-RBQ RequirementBundleQueryService — grouped requirement export by
architecture element via ALLOCATED_TO trace links (Requirement Bundle
Export, Plan 1 Task 1).

Design: docs/superpowers/specs/2026-08-08-requirement-bundle-export-design.md

Walks the ALLOCATED_TO trace-link graph (Requirement->ArchitectureElement and
ArchitectureElement->ArchitectureElement) starting at a root
ArchitectureElement, up to a configurable depth, collecting every Requirement
directly allocated to the root or any sub-element within that depth. Does NOT
use the Artifact parent_id structural tree (that is a different relationship,
see ArtifactService.get_tree) — grouping here is the semantic ALLOCATED_TO
allocation, per the design spec's explicit decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from uuid import UUID

from django.db import connection

from auth_tenancy.context import AuthContext
from traceability.types import LinkType

from application.base import NotFoundError, ServiceBase, ValidationError

MAX_DEPTH = 20  # mirrors ArtifactService.get_tree's recursive CTE cap


class BundleDepthExceededError(ValidationError):
    """Raised when a caller passes a depth greater than MAX_DEPTH."""


@dataclass
class BundleItem:
    """One Requirement found during the ALLOCATED_TO walk, with its origin."""

    requirement_id: UUID
    found_under_element_id: UUID
    depth: int
    fields: Dict[str, Any]


@dataclass
class BundleResult:
    items: List[BundleItem] = field(default_factory=list)
    truncated_at_depth: bool = False


# Requirement's own fields exposed by RequirementSerializer
# (backend/rest_api/serializers.py:459), used as the "all" field set — never
# internal-only columns (tenant_id, embedding, raw *_by_id FKs).
#
# Deviation from the plan brief: the brief's draft included "parent_id" here
# (mirroring RequirementSerializer's parent_id field), but Requirement has no
# such column — the serializer derives it dynamically from the backing
# Artifact's parent chain (see persistence/models.py Artifact docstring: only
# Artifact.parent stores requirement hierarchy, RequirementService writes it
# on create/decompose). A plain .values("parent_id") against Requirement
# raises django.core.exceptions.FieldError. Reproducing that derivation is
# out of scope for Task 1 (a straight field-passthrough); left for a later
# task if the design spec calls for it.
REQUIREMENT_ALL_FIELDS = (
    "id",
    "workspace_id",
    "title",
    "description",
    "acceptance_criteria",
    "category",
    "status",
    "type",
    "level",
    "complexity_fibonacci",
    "verification_method",
    "uid",
    "suspect",
    "lifecycle_status",
    "version",
)


class RequirementBundleQueryService(ServiceBase):
    """Raw (non-AI) requirement bundle query — Task 1: unfiltered field set."""

    def get_bundle(
        self,
        ctx: AuthContext,
        root_id: UUID,
        workspace_id: UUID,
        depth: "int | None" = None,
    ) -> BundleResult:
        """Return every Requirement allocated (ALLOCATED_TO) to *root_id* or
        its ALLOCATED_TO sub-elements, up to *depth* levels.

        Args:
            ctx: Resolved AuthContext (tenant scoping).
            root_id: ArchitectureElement id (the more user-facing id, same
                convention as TraceLinkService endpoints — resolved to its
                backing Artifact id internally).
            workspace_id: Workspace the root element must belong to.
            depth: 0 = only requirements directly allocated to the root.
                N = also walk N levels of ALLOCATED_TO Arch->Arch
                sub-elements. None = unbounded, capped at MAX_DEPTH.

        Raises:
            NotFoundError: root_id does not resolve to an ArchitectureElement
                in workspace_id.
            BundleDepthExceededError: depth > MAX_DEPTH.
        """
        self._set_tenant_context(ctx)

        if depth is not None and depth > MAX_DEPTH:
            raise BundleDepthExceededError(
                f"depth {depth} exceeds the maximum of {MAX_DEPTH}"
            )
        effective_cap = MAX_DEPTH if depth is None else depth

        from application.trace_link_service import TraceLinkService
        from persistence.models import ArchitectureElement

        root_artifact_id = TraceLinkService()._resolve_artifact_id(root_id)
        if not ArchitectureElement.objects.filter(
            artifact_id=root_artifact_id, artifact__workspace_id=workspace_id
        ).exists():
            raise NotFoundError(
                f"ArchitectureElement {root_id} not found in workspace {workspace_id}"
            )

        # Recursive CTE over pl_tracelink, filtered to ALLOCATED_TO, walking
        # ArchitectureElement->ArchitectureElement edges from the root, then
        # collecting every Requirement->ArchitectureElement edge landing on
        # any element found in that walk. Mirrors ArtifactService.get_tree's
        # raw-SQL CTE shape (backend/application/artifact_service.py:492).
        #
        # Deviation from the plan brief: the brief's recursive term joined
        # ``tl.source_id = t.element_artifact_id`` and selected
        # ``tl.target_id`` — that walks a "current node IS the source"
        # (child) edge to its *target* (parent), i.e. upward. But
        # ALLOCATED_TO edges point child -> parent (source=child,
        # target=container), and the walk must go the opposite way: from
        # the root *down* into elements allocated onto it. The recursive
        # term below therefore matches on ``tl.target_id`` (current node is
        # the allocation target) and yields ``tl.source_id`` (the
        # sub-element allocated onto it) — the Requirement->ArchitectureElement
        # edge direction (source=allocated thing, target=allocation target)
        # is directly proven by application/tests/test_allocation.py's
        # create_allocated_to_tracelink; the same direction for
        # ArchitectureElement->ArchitectureElement edges is inferred by
        # symmetry (same TraceLink table/link_type, no separate codepath) and
        # confirmed empirically by running
        # TestGetBundleRecursiveDepth::test_depth_one_includes_direct_child_requirements,
        # which failed (empty result) against the brief's original direction
        # and passes with this one.
        sql = """
            WITH RECURSIVE arch_tree AS (
                SELECT %s::uuid AS element_artifact_id, 0 AS depth

                UNION ALL

                SELECT tl.source_id AS element_artifact_id, t.depth + 1
                FROM pl_tracelink tl
                INNER JOIN arch_tree t ON tl.target_id = t.element_artifact_id
                WHERE tl.link_type = %s
                  AND t.depth < %s
            )
            SELECT DISTINCT ON (req_link.source_id)
                req_link.source_id AS requirement_artifact_id,
                arch_tree.element_artifact_id AS found_under_artifact_id,
                arch_tree.depth AS found_depth
            FROM arch_tree
            INNER JOIN pl_tracelink req_link
                ON req_link.target_id = arch_tree.element_artifact_id
                AND req_link.link_type = %s
            ORDER BY req_link.source_id, arch_tree.depth ASC;
        """
        allocated_to = LinkType.ALLOCATED_TO.value
        with connection.cursor() as cursor:
            cursor.execute(
                sql, [str(root_artifact_id), allocated_to, effective_cap, allocated_to]
            )
            rows = cursor.fetchall()

        # Fix (code review, round 1): truncated_at_depth must reflect the
        # full arch_tree walk, not just the post-JOIN `rows` (elements that
        # happen to have a directly-allocated Requirement). Computing it from
        # `rows` alone is a false-negative trap: an ALLOCATED_TO sub-element
        # hierarchy that extends past MAX_DEPTH, with no Requirement
        # allocated at exactly the deepest *visited* level, would silently
        # report truncated_at_depth=False even though Requirements attached
        # to unvisited (depth>MAX_DEPTH) descendants are missing from the
        # result entirely — violating the plan's Global Constraint "never
        # silently flattened." Only meaningful for an unbounded request
        # (depth=None -> effective_cap=MAX_DEPTH); an explicit depth is a
        # deliberately scoped query, not a truncation of an unbounded one.
        #
        # Fix (code review, round 2): the round-1 version checked
        # ``EXISTS (SELECT 1 FROM arch_tree WHERE depth >= effective_cap)`` —
        # that only proves a node exists AT the cap depth, not that anything
        # was cut off there. A hierarchy exactly MAX_DEPTH levels deep with
        # no further children naturally reaches (and includes) that boundary
        # node too, so the round-1 check false-positived on perfectly
        # complete, untruncated results. The correct test is whether some
        # ALLOCATED_TO edge actually *targets* a depth-effective_cap node —
        # i.e. there is a real child beyond the cap that the recursion's
        # ``t.depth < effective_cap`` guard stopped it from adding — not
        # whether the boundary node itself merely exists.
        #
        # Runs the recursive walk a second time to answer this (cheap,
        # index-backed given MAX_DEPTH=20 and pl_tracelink's
        # idx_tracelink_graph index; a known, deliberate tradeoff over
        # threading a "did we cut something off" flag through the main
        # query, which would need the same recursion structure anyway).
        truncated = False
        if depth is None:
            truncation_sql = """
                WITH RECURSIVE arch_tree AS (
                    SELECT %s::uuid AS element_artifact_id, 0 AS depth

                    UNION ALL

                    SELECT tl.source_id AS element_artifact_id, t.depth + 1
                    FROM pl_tracelink tl
                    INNER JOIN arch_tree t ON tl.target_id = t.element_artifact_id
                    WHERE tl.link_type = %s
                      AND t.depth < %s
                )
                SELECT EXISTS (
                    SELECT 1 FROM pl_tracelink tl
                    JOIN arch_tree t ON tl.target_id = t.element_artifact_id
                    WHERE tl.link_type = %s AND t.depth = %s
                );
            """
            with connection.cursor() as cursor:
                cursor.execute(
                    truncation_sql,
                    [
                        str(root_artifact_id),
                        allocated_to,
                        effective_cap,
                        allocated_to,
                        effective_cap,
                    ],
                )
                truncated = bool(cursor.fetchone()[0])

        if not rows:
            return BundleResult(items=[], truncated_at_depth=truncated)

        req_artifact_ids = [r[0] for r in rows]
        found_under_by_req: Dict[UUID, tuple] = {
            r[0]: (r[1], r[2]) for r in rows
        }

        from persistence.models import Requirement

        req_rows = Requirement.unscoped.filter(
            artifact_id__in=req_artifact_ids, tenant_id=ctx.tenant_id
        ).values(*REQUIREMENT_ALL_FIELDS, "artifact_id")

        items: List[BundleItem] = []
        for row in req_rows:
            artifact_id = row.pop("artifact_id")
            found_under_artifact_id, found_depth = found_under_by_req[artifact_id]
            items.append(
                BundleItem(
                    requirement_id=row["id"],
                    found_under_element_id=found_under_artifact_id,
                    depth=found_depth,
                    fields={k: v for k, v in row.items()},
                )
            )

        return BundleResult(items=items, truncated_at_depth=truncated)


__all__ = [
    "RequirementBundleQueryService",
    "BundleResult",
    "BundleItem",
    "BundleDepthExceededError",
    "REQUIREMENT_ALL_FIELDS",
    "MAX_DEPTH",
]
