"""COMP-AS-RBQ RequirementBundleQueryService — grouped requirement export by
architecture element via ALLOCATED_TO trace links (Requirement Bundle
Export, Plan 1 Task 1).

Design: docs/superpowers/specs/Archive/2026-08-08-requirement-bundle-export-design.md

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

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
)
from application.base import NotFoundError, ServiceBase, ValidationError

MAX_DEPTH = 20  # mirrors ArtifactService.get_tree's recursive CTE cap


class BundleDepthExceededError(ValidationError):
    """Raised when a caller passes a depth greater than MAX_DEPTH."""


@dataclass
class BundleItem:
    """One Requirement found during the ALLOCATED_TO walk, with its origin.

    .. warning:: ``requirement_id`` and ``found_under_element_id`` live in
       **different id spaces**. ``requirement_id`` is ``Requirement.id`` (the
       business id, directly usable against ``/api/v1/requirements/{id}/``),
       while ``found_under_element_id`` is the element's backing
       ``Artifact`` id (``ArchitectureElement.artifact_id``) — *not*
       ``ArchitectureElement.id``, which is what ``root_id`` takes on the way
       in. Resolving one back to the other goes through the Artifact layer,
       e.g. ``ArchitectureElement.objects.get(artifact_id=...)`` server-side
       or ``TraceLinkService._resolve_artifact_id`` in the other direction.
       This is a deliberate, documented design choice (the walk operates on
       artifact ids throughout); changing the returned value would be a
       breaking contract change.
    """

    requirement_id: UUID
    found_under_element_id: UUID
    depth: int
    fields: Dict[str, Any]


@dataclass
class BundleResult:
    items: List[BundleItem] = field(default_factory=list)
    truncated_at_depth: bool = False


# FALLBACK ONLY (spec section 7, Task 14): the authoritative export field list
# for a bootstrapped workspace now comes from the resolved AttributeDefinition's
# ``export=true`` attributes via ``resolve_export_fields`` below. This tuple is
# what a workspace with no definition yet (bootstrap not run for its tenant)
# still exports, and it is what the OpenAPI schema / describe_attribute_schema()
# document as the baseline set (the legacy
# AttributeVisibilityConfigService.describe_schema this replaced is gone).
#
# It is deliberately NOT identical to RequirementSerializer's field list, in
# both directions:
#   * the serializer additionally exposes parent_id, custom_fields and
#     change_reason — none of which is a Requirement column. parent_id in
#     particular is derived dynamically from the backing Artifact's parent
#     chain (see persistence/models.py Artifact docstring: only
#     Artifact.parent stores requirement hierarchy, RequirementService writes
#     it on create/decompose), so a plain .values("parent_id") against
#     Requirement raises django.core.exceptions.FieldError. Reproducing that
#     derivation is out of scope for a straight field passthrough; left for a
#     later task if the design spec calls for it.
#   * this set additionally includes level, suspect and lifecycle_status,
#     which the serializer happens not to publish — they are legitimate
#     export fields here. level/suspect are real Requirement columns;
#     lifecycle_status (like status) is not a column at all since Task 24 --
#     it is resolved from the backing Artifact (see get_bundle).
# created_at/modified_at are ordinary user-visible audit columns (the
# serializer publishes them as created_at/updated_at) and are exported too.
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
    "created_at",
    "modified_at",
)

# Live-verified (Task 14, against a real `bootstrap_attribute_definitions` run):
# `bootstrap_attribute_definitions.EXCLUDED_MODEL_FIELDS` deliberately excludes
# these 7 names from the attribute-definition model entirely -- id/workspace_id/
# version/created_at/modified_at are server-owned columns, suspect/
# lifecycle_status are the SN-30/Datenmodell-Konsolidierung server-state flags.
# None of them can ever be marked ``export=true`` through admin configuration,
# on any preset. Without unioning them back in, `resolve_export_fields` would
# silently drop all 7 from every "all"/"visible" bundle export -- and reject
# them outright (ValidationError) as "unknown" for filter_mode="custom" -- for
# every already-bootstrapped workspace (which is every workspace, per the SDD
# ledger's corrected-deployment-state finding), even though they exported fine
# before this task. Confirmed exhaustively (0 unexpected extras/omissions) via
# a real `AttributeDefinitionService().export_attributes(ctx, "Requirement",
# workspace_id)` call against a freshly bootstrapped tenant: it returns exactly
# `set(REQUIREMENT_ALL_FIELDS) - _SYSTEM_EXPORT_FIELDS`.
_SYSTEM_EXPORT_FIELDS: frozenset = frozenset(
    {
        "id",
        "workspace_id",
        "version",
        "created_at",
        "modified_at",
        "suspect",
        "lifecycle_status",
    }
)

# Shared recursive CTE walking ALLOCATED_TO ArchitectureElement->
# ArchitectureElement edges down from a root element. Used verbatim by both
# get_bundle's main query and its truncation probe — they MUST agree on the
# reachable node set, so the text lives here once rather than being inlined
# twice.
#
# Placeholders, in order:
#   1. root artifact id (uuid)
#   2. link type ('allocated-to')
#   3. tenant id (uuid)
#   4. depth cap (int)
#
# Design notes:
#   * Direction: ALLOCATED_TO points child -> parent (source = the allocated
#     thing, target = the allocation target), so walking *down* from the root
#     matches on tl.target_id and yields tl.source_id.
#   * The artifact_type join is load-bearing, not cosmetic: SE_LINK_SEMANTICS
#     (traceability/types.py) only constrains ALLOCATED_TO endpoints to
#     {(Requirement, ArchitectureElement), (ArchitectureElement,
#     ArchitectureElement)} when the workspace has se_mode configured —
#     TraceLinkService._check_se_semantics returns early otherwise. Without
#     the join, a Requirement --allocated-to--> Requirement edge in an
#     ordinary dev-mode workspace would enter arch_tree as if it were an
#     architecture element and corrupt found_under_element_id.
#   * UNION (not UNION ALL) is the cycle/diamond guard: nothing enforces a
#     single parent for Arch->Arch edges (TraceLinkService.create_trace_link
#     only dedupes previous links for Requirement sources), so a diamond
#     allocation multiplies rows per path with UNION ALL, up to MAX_DEPTH
#     levels deep — on a query now reachable from an authenticated external
#     REST/MCP endpoint. UNION dedupes (element_artifact_id, depth) pairs,
#     bounding the walk at roughly nodes x (cap + 1) rows.
#   * tenant_id is filtered explicitly even though pl_tracelink/pl_artifact
#     both carry FORCE ROW LEVEL SECURITY (persistence/migrations/
#     0003_rls_policies.py). Every other query path in this codebase has two
#     layers of tenant scoping (RLS + the ORM's thread-local tenant filter);
#     this raw-SQL path would otherwise have one, which matters for future
#     non-request contexts (e.g. Celery) where no middleware runs.
_ARCH_TREE_CTE = """
    WITH RECURSIVE arch_tree AS (
        SELECT %s::uuid AS element_artifact_id, 0 AS depth

        UNION

        SELECT tl.source_id AS element_artifact_id, t.depth + 1
        FROM pl_tracelink tl
        INNER JOIN arch_tree t ON tl.target_id = t.element_artifact_id
        INNER JOIN pl_artifact a
            ON a.id = tl.source_id
           AND a.artifact_type = 'ArchitectureElement'
        WHERE tl.link_type = %s
          AND tl.tenant_id = %s::uuid
          AND t.depth < %s
    )
"""


class RequirementBundleQueryService(ServiceBase):
    """Raw (non-AI) requirement bundle query with attribute filtering
    (Task 1: allocation walk + unfiltered field set; Task 2: filter_mode)."""

    def get_bundle(
        self,
        ctx: AuthContext,
        root_id: UUID,
        workspace_id: UUID,
        depth: "int | None" = None,
        *,
        filter_mode: str = "all",
        fields: "List[str] | None" = None,
    ) -> BundleResult:
        """Return every Requirement allocated (ALLOCATED_TO) to *root_id* or
        its ALLOCATED_TO sub-elements, up to *depth* levels, with fields
        limited per *filter_mode*.

        Args:
            ctx: Resolved AuthContext (tenant scoping).
            root_id: ArchitectureElement id (the more user-facing id, same
                convention as TraceLinkService endpoints — resolved to its
                backing Artifact id internally).
            workspace_id: Workspace the root element must belong to.
            depth: 0 = only requirements directly allocated to the root.
                N = also walk N levels of ALLOCATED_TO Arch->Arch
                sub-elements. None = unbounded, capped at MAX_DEPTH.
            filter_mode: "all" (every ``export=true`` attribute of the
                resolved Requirement AttributeDefinition, plus the system
                columns no definition can ever carry — see
                resolve_export_fields), "visible" (additionally
                ``visible=true``), or "custom" (only the fields named in
                *fields*, each of which must be one of the above).
            fields: Required (non-empty) when filter_mode="custom".

        Raises:
            NotFoundError: root_id does not resolve to an ArchitectureElement
                in workspace_id.
            BundleDepthExceededError: depth > MAX_DEPTH.
            ValidationError: filter_mode is invalid, or filter_mode="custom"
                with a missing/empty or unknown field name.
        """
        self._set_tenant_context(ctx)

        if filter_mode not in ("all", "visible", "custom"):
            raise ValidationError(
                f"Invalid filter_mode {filter_mode!r}; expected 'all', 'visible', or 'custom'"
            )
        if filter_mode == "custom" and not fields:
            raise ValidationError(
                "filter_mode='custom' requires a non-empty 'fields' list"
            )
        # Resolved eagerly, before the query runs: an invalid filter_mode='custom'
        # field name must fail loudly even when the walk below finds zero
        # requirements to return — deferring this to right before the (skipped
        # on an empty walk) field-projection step used to silently swallow a
        # typo'd field name whenever `root_id` had nothing allocated to it yet.
        selected_fields = self.resolve_export_fields(ctx, workspace_id, filter_mode, fields)

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
        # ArchitectureElement->ArchitectureElement edges from the root (see
        # _ARCH_TREE_CTE), then collecting every Requirement->ArchitectureElement
        # edge landing on any element found in that walk. Mirrors
        # ArtifactService.get_tree's raw-SQL CTE shape
        # (backend/application/artifact_service.py:492).
        #
        # Deviation from the plan brief: the brief's recursive term joined
        # ``tl.source_id = t.element_artifact_id`` and selected
        # ``tl.target_id`` — that walks a "current node IS the source"
        # (child) edge to its *target* (parent), i.e. upward. But
        # ALLOCATED_TO edges point child -> parent (source=child,
        # target=container), and the walk must go the opposite way: from
        # the root *down* into elements allocated onto it. The recursive
        # term therefore matches on ``tl.target_id`` (current node is the
        # allocation target) and yields ``tl.source_id`` (the sub-element
        # allocated onto it). Both endpoint pairs are declared explicitly in
        # ``traceability/types.py:119``
        # (``LinkType.ALLOCATED_TO.value: {(Requirement, ArchitectureElement),
        # (ArchitectureElement, ArchitectureElement)}``, ordered
        # source -> target), so the Arch->Arch direction is proven from that
        # table rather than inferred from the Requirement->Arch case; the
        # Requirement->Arch direction is additionally exercised by
        # application/tests/test_allocation.py's create_allocated_to_tracelink.
        sql = _ARCH_TREE_CTE + """
            SELECT DISTINCT ON (req_link.source_id)
                req_link.source_id AS requirement_artifact_id,
                arch_tree.element_artifact_id AS found_under_artifact_id,
                arch_tree.depth AS found_depth
            FROM arch_tree
            INNER JOIN pl_tracelink req_link
                ON req_link.target_id = arch_tree.element_artifact_id
                AND req_link.link_type = %s
                AND req_link.tenant_id = %s::uuid
            ORDER BY req_link.source_id, arch_tree.depth ASC;
        """
        allocated_to = LinkType.ALLOCATED_TO.value
        tenant_id = str(ctx.tenant_id)
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [
                    str(root_artifact_id),
                    allocated_to,
                    tenant_id,
                    effective_cap,
                    allocated_to,
                    tenant_id,
                ],
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
        #
        # The EXISTS probe applies the same ArchitectureElement type filter as
        # the walk itself: only an *element* beyond the cap is something the
        # recursion cut off. A Requirement allocated to the boundary element
        # is already present in the result, so counting it as truncation
        # would be a false positive.
        truncated = False
        if depth is None:
            truncation_sql = _ARCH_TREE_CTE + """
                SELECT EXISTS (
                    SELECT 1 FROM pl_tracelink tl
                    JOIN arch_tree t ON tl.target_id = t.element_artifact_id
                    INNER JOIN pl_artifact a
                        ON a.id = tl.source_id
                       AND a.artifact_type = 'ArchitectureElement'
                    WHERE tl.link_type = %s
                      AND tl.tenant_id = %s::uuid
                      AND t.depth = %s
                );
            """
            with connection.cursor() as cursor:
                cursor.execute(
                    truncation_sql,
                    [
                        str(root_artifact_id),
                        allocated_to,
                        tenant_id,
                        effective_cap,
                        allocated_to,
                        tenant_id,
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

        # Task 12: `status` is dropped from Requirement -- it can no longer
        # be a `.values()` column. Query every *other* selected field as
        # before, and resolve `status` separately through the workflow
        # engine seam (batched) when the caller actually selected it.
        # Task 24: `lifecycle_status` is dropped too -- same treatment,
        # resolved from `Artifact.lifecycle_status` (Decision D-3) instead.
        wants_status = "status" in selected_fields
        wants_lifecycle_status = "lifecycle_status" in selected_fields
        query_fields = tuple(
            (set(selected_fields) - {"status", "lifecycle_status"})
            | {"id", "artifact_id"}
        )
        req_rows = list(
            Requirement.unscoped.filter(
                artifact_id__in=req_artifact_ids, tenant_id=ctx.tenant_id
            ).values(*query_fields)
        )

        status_by_id: Dict[Any, str] = {}
        if wants_status and req_rows:
            from workflow import state_reader

            states = state_reader.current_states(
                "Requirement", (row["id"] for row in req_rows), tenant_id=ctx.tenant_id
            )
            requirement_initial_state = state_reader.initial_state("Requirement")
            status_by_id = {
                row["id"]: states.get(str(row["id"])) or requirement_initial_state
                for row in req_rows
            }

        lifecycle_status_by_artifact_id: Dict[Any, str] = {}
        if wants_lifecycle_status and req_rows:
            from persistence.models import Artifact

            lifecycle_status_by_artifact_id = {
                str(artifact_id): value
                for artifact_id, value in Artifact.unscoped.filter(
                    id__in=(row["artifact_id"] for row in req_rows)
                ).values_list("id", "lifecycle_status")
            }

        items: List[BundleItem] = []
        for row in req_rows:
            artifact_id = row.pop("artifact_id")
            found_under_artifact_id, found_depth = found_under_by_req[artifact_id]
            item_fields = {k: v for k, v in row.items() if k in selected_fields}
            if wants_status:
                item_fields["status"] = status_by_id[row["id"]]
            if wants_lifecycle_status:
                item_fields["lifecycle_status"] = lifecycle_status_by_artifact_id.get(
                    str(artifact_id), "active"
                )
            items.append(
                BundleItem(
                    requirement_id=row["id"],
                    found_under_element_id=found_under_artifact_id,
                    depth=found_depth,
                    fields=item_fields,
                )
            )

        return BundleResult(items=items, truncated_at_depth=truncated)

    def resolve_export_fields(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        filter_mode: str,
        fields: "List[str] | None",
    ) -> "set[str]":
        """Return the field names a bundle export must carry (spec section 7).

        Replaces the retired ``AttributeVisibilityConfigService`` /
        ``_resolve_field_set``'s "visible degrades to all" placeholder with a
        real read against the resolved Requirement AttributeDefinition:
        ``export=true`` attributes drive "all", additionally ``visible=true``
        drives "visible", and "custom" is rejected if it names anything
        outside that set.

        Args:
            filter_mode: ``"all"`` (every ``export=true`` attribute),
                ``"visible"`` (additionally ``visible=true``), or ``"custom"``
                (the caller's ``fields``, each of which must be exportable).

        Raises:
            ValidationError: ``filter_mode="custom"`` names a field that is
                neither an ``export=true`` attribute nor a system column.
                Rejecting loudly is the point — the old code silently
                dropped unknown names into an empty result instead.
        """
        try:
            attributes = AttributeDefinitionService().export_attributes(
                ctx, "Requirement", workspace_id
            )
        except AttributeDefinitionNotFound:
            # No GlobalAttributeDefinition bootstrapped yet for this tenant's
            # (item_type, preset) — REQUIREMENT_ALL_FIELDS is the pre-Task-14
            # behaviour, not a degraded stub: every name is treated as visible.
            attributes = [
                {"name": name, "visible": True} for name in REQUIREMENT_ALL_FIELDS
            ]

        # _SYSTEM_EXPORT_FIELDS is unioned into every mode, not just "all":
        # these columns are structurally excluded from the attribute-definition
        # model (see its docstring above) and so can never be admin-marked
        # export/visible one way or the other — they keep behaving as they did
        # before this attribute-definition-driven resolution existed.
        exportable = {a["name"] for a in attributes} | _SYSTEM_EXPORT_FIELDS
        if filter_mode == "custom":
            requested = set(fields or [])
            unknown = sorted(requested - exportable)
            if unknown:
                raise ValidationError(
                    f"Unknown field(s) for filter_mode='custom': {', '.join(unknown)}. "
                    f"Available: {', '.join(sorted(exportable))}"
                )
            return requested
        if filter_mode == "visible":
            visible = {a["name"] for a in attributes if a.get("visible", True)}
            return visible | _SYSTEM_EXPORT_FIELDS
        return exportable


def describe_attribute_schema(entity_type: "str | None" = None) -> "List[Dict[str, Any]]":
    """Return the available attributes for *entity_type* (or every known type).

    Replaces ``AttributeVisibilityConfigService.describe_schema`` (retired in
    Task 9 along with ``AttributeVisibilityConfig``): every attribute now
    reports ``is_visible=True`` unconditionally rather than resolving a
    per-tenant hide toggle. Shared by the REST ``AttributeSchemaView`` and the
    MCP ``requirement_bundle.attribute_schema`` tool so the degraded
    "everything visible" behaviour lives in exactly one place.

    Raises:
        NotFoundError: *entity_type* is not one of the known schemas.
    """
    schemas: Dict[str, tuple] = {"Requirement": REQUIREMENT_ALL_FIELDS}
    if entity_type is not None:
        if entity_type not in schemas:
            raise NotFoundError(f"Unknown entity_type {entity_type!r}")
        schemas = {entity_type: schemas[entity_type]}
    return [
        {"entity_type": et, "attribute_name": name, "is_visible": True}
        for et, names in schemas.items()
        for name in names
    ]


__all__ = [
    "RequirementBundleQueryService",
    "BundleResult",
    "BundleItem",
    "BundleDepthExceededError",
    "REQUIREMENT_ALL_FIELDS",
    "MAX_DEPTH",
    "describe_attribute_schema",
]
