"""
COMP-AS-005 TraceLinkService — TraceLink CRUD and cascade-delete.

leaf_id : COMP-AS-005
req_id  : REQ-L2-AS-010 (TraceLink Orchestration)

Orchestrates TraceLink operations via the TraceabilityEngine (IF-AS-EXT-OUT-003).
Validates Source/Target existence and workspace membership before INSERT.
Cascade-delete runs inside the caller's transaction context (ADR-L3-AS005-02).

Interfaces served:
  IF-AS-INT-001  ArtifactService     → cascade_delete_trace_links(artifact_id)
  IF-AS-INT-002  RequirementService  → create_trace_link(source_id, target_id, type)
  IF-AS-INT-004  ArchitectureService → cascade_delete_trace_links(arch_el_id)
  IF-AS-INT-005  TestService         → cascade_delete_trace_links(test_case_id)

Interfaces consumed:
  IF-AS-EXT-OUT-003  TraceabilityEngine:
      create_trace_link, delete_trace_link, batch_delete_trace_links,
      query, VALID_LINK_TYPES

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-005_TraceLinkService/
      L3_COMP-AS-005_TraceLinkService_Architecture.md

ADR-L3-AS005-01: cross-workspace prevention.
ADR-L3-AS005-02: cascade-delete in caller TX.
ADR-L3-AS005-03: polymorphic source_type/target_type.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from django.conf import settings

from auth_tenancy.context import AuthContext

from application.base import NotFoundError, ServiceBase, ValidationError
from traceability.types import VALID_LINK_TYPES  # REQ-L1-030: single source of truth

logger = logging.getLogger(__name__)


@dataclass
class SimilarTraceLinkDTO:
    """A single trace-link similarity-search hit (REQ-L2-VS-004)."""

    id: UUID
    source_id: UUID
    target_id: UUID
    link_type: str
    similarity_score: float


@dataclass
class TraceEdgeDTO:
    """A single incoming/outgoing TraceLink edge (MCP-05, Codeberg #117)."""

    source_id: UUID
    target_id: UUID
    link_type: str


class TraceLinkService(ServiceBase):
    """TraceLink CRUD and cascade-delete for COMP-AS-005.

    All write operations run inside the caller's transaction context —
    no internal transaction.atomic() wrapper is added here (ADR-L3-AS005-02).
    """

    # ---------- IF-AS-INT-002 ----------

    def _resolve_artifact_id(self, entity_id: UUID) -> UUID:
        """Resolve a business-entity ID to its backing Artifact ID.

        The TraceabilityEngine stores links between Artifact IDs.  Callers may
        pass the more user-facing Requirement, ArchitectureElement, ADR, Goal
        or MainGoal IDs; this helper transparently maps those to their
        backing Artifact.

        Resolution order:
          1. If *entity_id* is already an Artifact ID, return it unchanged.
          2. If it matches a Requirement, return Requirement.artifact_id.
          3. If it matches an ArchitectureElement, return its artifact_id.
          4. If it matches an ADR, return Adr.artifact_id (REQ-L2-TE-020).
          5. If it matches a Goal, return Goal.artifact_id (fix #237: Goal is
             a first-class artifact type with its own dedicated Artifact row,
             see GoalService.create_version, but was missing here so any
             Goal<->Requirement trace link raised "Entity not found").
          6. If it matches a MainGoal, return MainGoal.artifact_id (same gap
             as Goal — fix #237).
          7. Otherwise raise NotFoundError.
        """
        from persistence.models import (
            ArchitectureElement,
            Artifact,
            Requirement,
        )

        # 1. Already an Artifact ID?
        if Artifact.objects.filter(id=entity_id).first() is not None:
            return entity_id

        # 2. Requirement -> Artifact
        req = Requirement.objects.filter(id=entity_id).first()
        if req is not None:
            return UUID(str(req.artifact_id))

        # 3. ArchitectureElement -> Artifact
        arch = ArchitectureElement.objects.filter(id=entity_id).first()
        if arch is not None:
            return UUID(str(arch.artifact_id))

        # 4. ADR -> Artifact (REQ-L2-TE-020). Adr lives in the application app
        # and is not tenant-scoped, so it is imported locally to avoid a
        # circular import (adr_service imports TraceLinkService).
        from application.models import Adr, Goal, MainGoal

        adr = Adr.objects.filter(id=entity_id).first()
        if adr is not None and adr.artifact_id is not None:
            return UUID(str(adr.artifact_id))

        # 5. Goal -> Artifact (fix #237).
        goal = Goal.objects.filter(id=entity_id).first()
        if goal is not None:
            return UUID(str(goal.artifact_id))

        # 6. MainGoal -> Artifact (fix #237).
        main_goal = MainGoal.objects.filter(id=entity_id).first()
        if main_goal is not None:
            return UUID(str(main_goal.artifact_id))

        raise NotFoundError(f"Entity {entity_id} not found")

    def _check_se_semantics(
        self,
        source_artifact_id: UUID,
        target_artifact_id: UUID,
        link_type: str,
    ) -> None:
        """Enforce SE endpoint semantics in se_mode workspaces (finding F1).

        Resolution failures (missing artifact/preset config, unit-test
        contexts) skip enforcement — same permissive fallback pattern as
        ArchitectureElementInvariantValidator.for_workspace().

        Raises:
            ValidationError: If the workspace runs in se_mode and the
                link violates the SE endpoint matrix.
        """
        from traceability.types import check_se_link_semantics

        try:
            from persistence.models import Artifact
            from presets.models import WorkspacePresetConfig

            source = Artifact.objects.filter(id=source_artifact_id).first()
            target = Artifact.objects.filter(id=target_artifact_id).first()
            if source is None or target is None:
                return  # existence errors are raised downstream

            config = WorkspacePresetConfig.objects.filter(
                workspace_id=source.workspace_id
            ).first()
            if config is None or config.terminology_profile != "se_mode":
                return  # dev_mode / unconfigured: no SE rigor

            error = check_se_link_semantics(
                link_type, source.artifact_type, target.artifact_type
            )
        except ValidationError:
            raise
        except Exception:
            logger.debug(
                "SE semantics check skipped for %s -> %s",
                source_artifact_id,
                target_artifact_id,
                exc_info=True,
            )
            return

        if error is not None:
            raise ValidationError(error)

    def create_trace_link(
        self,
        source_id: UUID,
        target_id: UUID,
        link_type: str,
        ctx: AuthContext,
    ):
        """Create a single TraceLink after validation.

        REQ-L2-AS-010: validates existence, workspace membership, link type.
        Accepts Artifact, Requirement or ArchitectureElement IDs for
        *source_id* and *target_id* and resolves them to Artifact IDs before
        delegating to the TraceabilityEngine.

        Args:
            source_id: UUID of the source artifact or derived entity.
            target_id: UUID of the target artifact or derived entity.
            link_type: One of VALID_LINK_TYPES.
            ctx: Resolved AuthContext.

        Returns:
            Created TraceLink ORM instance.

        Raises:
            ValidationError: Invalid link_type or cross-workspace link.
            NotFoundError:   Source or target entity does not exist.
        """
        self._set_tenant_context(ctx)

        if link_type not in VALID_LINK_TYPES:
            raise ValidationError(
                f"Invalid link type '{link_type}'. "
                f"Valid types: {sorted(VALID_LINK_TYPES)}"
            )

        # Resolve Requirement/ArchitectureElement IDs to Artifact IDs
        resolved_source = self._resolve_artifact_id(source_id)
        resolved_target = self._resolve_artifact_id(target_id)

        # SE endpoint semantics (se_mode workspaces only, permissive for
        # non-core artifact types — see docs/se/workspace_modes_er_model.md F1).
        self._check_se_semantics(resolved_source, resolved_target, link_type)

        # REQ-L1-044 I4: allocated-to must not target an ancestor of the
        # source (Extended rigor only, gated inside the validator).
        from traceability.types import LinkType

        if link_type == LinkType.ALLOCATED_TO:
            self._check_allocation_invariant(resolved_source, resolved_target)

        from traceability.services import (
            SourceNotFoundError,
            TargetNotFoundError,
            create_trace_link as te_create,
        )

        try:
            result = te_create(
                source_id=resolved_source,
                target_id=resolved_target,
                link_type=link_type,
                created_by_id=ctx.user_id,
            )
        except SourceNotFoundError as exc:
            raise NotFoundError("Source entity not found") from exc
        except TargetNotFoundError as exc:
            raise NotFoundError("Target entity not found") from exc
        except Exception as exc:
            # Re-map cross-tenant errors as ValidationError
            msg = str(exc)
            if "cross" in msg.lower() or "tenant" in msg.lower():
                raise ValidationError(
                    "Cross-workspace TraceLinks are not permitted"
                ) from exc
            raise

        # REQ-L2-VS-004: best-effort semantic embedding for similarity search.
        self._generate_and_store_embedding(result)

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="TraceLink",
            entity_id=result.id if hasattr(result, "id") else source_id,
        )
        return result

    # ---------- Semantic similarity (REQ-L2-VS-004) ----------

    @staticmethod
    def _generate_and_store_embedding(trace_link) -> None:
        """Best-effort: generate and persist the trace link's embedding.

        REQ-L2-VS-004. Uses a bare ``.update()`` so it neither bumps the
        version nor emits a domain event. Never raises: the embedding is
        supplementary, so a provider/network failure must not fail the
        surrounding create transaction. Mirrors
        RequirementService._generate_and_store_embedding.
        """
        try:
            from persistence.models import TraceLink
            from llm_adapter.embedding_service import (
                generate_embedding,
                get_tracelink_embedding_text,
            )

            if not getattr(trace_link, "id", None):
                return
            embedding = generate_embedding(get_tracelink_embedding_text(trace_link))
            if embedding is not None:
                TraceLink.objects.filter(id=trace_link.id).update(embedding=embedding)
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.debug(
                "TraceLinkService: embedding generation skipped for link=%s: %s",
                getattr(trace_link, "id", None),
                exc,
            )

    def find_similar_trace_links(
        self,
        trace_link_id: UUID,
        ctx: AuthContext,
        limit: int = 10,
    ) -> List[SimilarTraceLinkDTO]:
        """Return the top-N trace links most similar to *trace_link_id*.

        REQ-L2-VS-004: cosine-distance nearest-neighbour search over the
        pgvector ``embedding`` column, tenant-scoped and excluding the query
        link itself. Mirrors RequirementService.find_similar_requirements.

        Raises:
            NotFoundError: Query trace link does not exist.
            ValidationError: Query trace link has no embedding.
            PgVectorUnavailableError: pgvector package/extension unavailable.
        """
        from django.db.utils import OperationalError, ProgrammingError
        from persistence.models import TraceLink
        from application.requirement_service import PgVectorUnavailableError

        self._set_tenant_context(ctx)

        link = TraceLink.objects.filter(id=trace_link_id).first()
        if link is None:
            raise NotFoundError(f"TraceLink {trace_link_id} not found")
        if link.embedding is None:
            raise ValidationError(
                "TraceLink has no embedding — similarity search not possible"
            )

        try:
            from pgvector.django import CosineDistance
        except ImportError as exc:
            raise PgVectorUnavailableError(
                "pgvector package not installed — similarity search unavailable"
            ) from exc

        safe_limit = max(1, min(int(limit or 10), 50))

        queryset = (
            TraceLink.objects.filter(
                tenant_id=ctx.tenant_id, embedding__isnull=False
            )
            .exclude(id=link.id)
            .annotate(distance=CosineDistance("embedding", link.embedding))
            .order_by("distance")[:safe_limit]
        )

        try:
            rows = list(queryset)
        except (ProgrammingError, OperationalError) as exc:
            raise PgVectorUnavailableError(
                "pgvector extension not available — similarity search unavailable"
            ) from exc

        return [
            SimilarTraceLinkDTO(
                id=row.id,
                source_id=row.source_id,
                target_id=row.target_id,
                link_type=row.link_type,
                # Cosine distance in [0, 2]; similarity = 1 - distance.
                similarity_score=round(1.0 - float(row.distance), 6),
            )
            for row in rows
        ]

    # ---------- IF-AS-INT-001 / 004 / 005 ----------

    def cascade_delete_trace_links(
        self, entity_id: UUID, ctx: AuthContext
    ) -> int:
        """Delete all TraceLinks where source OR target is *entity_id*.

        Runs in the caller's transaction context (ADR-L3-AS005-02).
        Idempotent: deleting a non-existent entity's links is a no-op.

        Returns:
            Number of deleted TraceLinks.
        """
        self._set_tenant_context(ctx)

        from traceability.services import batch_delete_trace_links, query
        from traceability.types import Direction

        # Gather all link IDs where this entity is source or target
        link_ids: List[UUID] = []
        for direction in ("upstream", "downstream"):
            try:
                results = query(
                    artifact_id=entity_id,
                    direction=direction,
                    transitive=False,
                )
                for item in results:
                    if hasattr(item, "link_id"):
                        link_ids.append(item.link_id)
            except Exception:
                logger.debug(
                    "TraceLinkService: no links found for entity %s direction=%s",
                    entity_id,
                    direction,
                )

        if not link_ids:
            return 0

        deleted = batch_delete_trace_links(link_ids)
        return deleted

    # ---------- Allocation (REQ-L1-042, REQ-L1-044) ----------

    def _check_allocation_invariant(
        self, source_artifact_id: UUID, target_artifact_id: UUID
    ) -> None:
        """Enforce invariant I4 for allocated-to links (REQ-L1-044).

        Applies only when both endpoints resolve to ArchitectureElements
        (Requirement → ArchitectureElement allocations are unaffected).
        The check itself is rigor-gated inside the validator (Extended only).

        Raises:
            ValidationError: If the target is an ancestor of the source.
        """
        from persistence.models import ArchitectureElement

        from application.validators import ArchitectureElementInvariantValidator

        source_el = (
            ArchitectureElement.objects.select_related("artifact")
            .filter(artifact_id=source_artifact_id)
            .first()
        )
        target_el = ArchitectureElement.objects.filter(
            artifact_id=target_artifact_id
        ).first()
        if source_el is None or target_el is None:
            return

        validator = ArchitectureElementInvariantValidator.for_workspace(
            source_el.artifact.workspace_id
        )
        validator.validate_allocation(
            source_element=source_el, target_element=target_el
        )

    def allocate(
        self,
        requirement_id: UUID,
        architecture_element_id: UUID,
        ctx: AuthContext,
    ):
        """Allocate a Requirement to an ArchitectureElement via allocated-to TraceLink.

        REQ-L1-042: Creates or replaces the allocated-to link. Only one allocation
        per Requirement is allowed; if a previous allocation exists, it is deleted first.

        Args:
            requirement_id: UUID of the Requirement to allocate.
            architecture_element_id: UUID of the target ArchitectureElement.
            ctx: AuthContext for tenant scoping and audit.

        Returns:
            Created TraceLink instance.

        Raises:
            NotFoundError: Requirement or ArchitectureElement not found.
            ValidationError: Invalid entity types or cross-tenant link.
        """
        from persistence.models import ArchitectureElement, Requirement, TraceLink
        from traceability.types import LinkType

        self._set_tenant_context(ctx)

        # Validate that requirement_id is a Requirement
        req = Requirement.objects.filter(id=requirement_id).first()
        if req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        # Validate that architecture_element_id is an ArchitectureElement
        arch_el = ArchitectureElement.objects.filter(id=architecture_element_id).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {architecture_element_id} not found")

        # Delete any previous allocated-to link for this requirement
        req_artifact_id = UUID(str(req.artifact_id))
        existing = TraceLink.objects.filter(
            source_id=req_artifact_id,
            link_type=LinkType.ALLOCATED_TO,
        )
        if existing.exists():
            existing.delete()

        # Create new allocated-to link
        result = self.create_trace_link(
            source_id=requirement_id,
            target_id=architecture_element_id,
            link_type=LinkType.ALLOCATED_TO,
            ctx=ctx,
        )

        return result

    def get_allocation_coverage(
        self,
        architecture_element_id: UUID,
        ctx: AuthContext,
    ) -> dict:
        """Get allocation coverage metrics for an ArchitectureElement.

        REQ-L1-042: Returns metrics on how many child requirements are allocated
        to this ArchitectureElement and its descendants.

        Args:
            architecture_element_id: UUID of the ArchitectureElement to analyze.
            ctx: AuthContext for tenant scoping.

        Returns:
            Dict with keys:
              - allocated_count: Number of allocated Requirements.
              - coverage_ratio: Percentage (0-100) of allocated vs total child requirements.
              - unallocated_requirements: List of unallocated child requirement IDs and titles.

        Raises:
            NotFoundError: ArchitectureElement not found.
        """
        from persistence.models import ArchitectureElement, Requirement
        from traceability.types import LinkType

        self._set_tenant_context(ctx)

        arch_el = ArchitectureElement.objects.filter(id=architecture_element_id).first()
        if arch_el is None:
            raise NotFoundError(f"ArchitectureElement {architecture_element_id} not found")

        # Get all child requirements in the workspace
        # Child requirements are those in the same workspace
        workspace_id = arch_el.artifact.workspace_id
        all_reqs = list(
            Requirement.objects.filter(artifact__workspace_id=workspace_id)
        )

        # Count how many are allocated to this element
        allocated_count = 0
        unallocated_list = []

        for req in all_reqs:
            # Check if this requirement has an allocated-to link to this arch_el
            from traceability.services import query

            req_artifact_id = UUID(str(req.artifact_id))
            links = list(query(artifact_id=req_artifact_id, direction="downstream"))
            allocated_to_ids = [
                link.entity_id
                for link in links
                if getattr(link, "link_type", None) == LinkType.ALLOCATED_TO
            ]

            # Check if any of the allocated-to targets match this arch_el's artifact
            arch_el_artifact_id = UUID(str(arch_el.artifact_id))
            is_allocated_to_this = arch_el_artifact_id in allocated_to_ids

            if is_allocated_to_this:
                allocated_count += 1
            else:
                unallocated_list.append({
                    "id": req.id,
                    "title": req.title,
                })

        # Calculate coverage ratio
        total_reqs = len(all_reqs)
        coverage_ratio = (
            (allocated_count / total_reqs * 100) if total_reqs > 0 else 0
        )

        return {
            "allocated_count": allocated_count,
            "coverage_ratio": coverage_ratio,
            "unallocated_requirements": unallocated_list,
        }

    def get_requirement_allocations(
        self,
        requirement_artifact_id: UUID,
        tenant_id: UUID,
        ctx: AuthContext,
    ) -> list[dict]:
        """Return the ArchitectureElements a requirement is allocated to.

        REQ-L1-058 AC3: resolves all ``allocated-to`` TraceLinks whose source is
        the requirement's artifact and returns the target ArchitectureElement
        details. REQ-066: ORM access lives in the service layer.

        Issue #129: the target levels are pre-computed for all resolved
        elements in a single recursive-CTE query via
        ``ArchitectureElement.annotate_levels`` before the dicts are built.
        Reading ``ae.level`` per element would otherwise fall back to a
        per-instance lookup (N+1). A previous ``get_with_level()`` prefetch was
        dead code — ``objects`` is a plain ``TenantManager`` without that
        method, so the endpoint raised ``AttributeError`` on every call; the
        annotation would also have been shadowed by the ``level`` property.

        Args:
            requirement_artifact_id: Artifact UUID of the source requirement.
            tenant_id: Tenant UUID for row scoping.
            ctx: AuthContext for tenant scoping.

        Returns:
            List of dicts with architecture_element_id, architecture_element_title,
            target_level, asil_level, make_or_buy.
        """
        from django.db.models import Prefetch

        from persistence.models import ArchitectureElement, TraceLink

        self._set_tenant_context(ctx)

        trace_links = (
            TraceLink.objects.filter(
                source_id=requirement_artifact_id,
                link_type="allocated-to",
                tenant_id=tenant_id,
            )
            .select_related("target")
            .prefetch_related(
                Prefetch(
                    "target__architecture_element",
                    queryset=ArchitectureElement.objects.all(),
                )
            )
        )

        elements = [
            tl.target.architecture_element
            for tl in trace_links
            if tl.target and hasattr(tl.target, "architecture_element")
        ]
        # Issue #129: one CTE query for all levels instead of one query per
        # ancestor per element.
        ArchitectureElement.annotate_levels(elements)

        return [
            {
                "architecture_element_id": str(ae.id),
                "architecture_element_title": ae.title,
                "target_level": ae.level,
                "asil_level": ae.asil_level,
                "make_or_buy": ae.make_or_buy,
            }
            for ae in elements
        ]

    # ---------- Query ----------

    def query_trace_links(
        self,
        entity_id: UUID,
        direction: str,
        link_type: Optional[str] = None,
        ctx: Optional[AuthContext] = None,
    ) -> list:
        """Query TraceLinks for *entity_id* with optional direction/type filter.

        REQ-L2-AS-010.

        Args:
            entity_id: Starting artifact, Requirement or ArchitectureElement UUID.
            direction: "upstream" | "downstream".
            link_type: Optional filter; ignored if None.
            ctx: AuthContext (required for tenant scoping).
        """
        if ctx is not None:
            self._set_tenant_context(ctx)

        from traceability.services import query

        # Resolve Requirement/ArchitectureElement IDs to Artifact IDs so the
        # TraceabilityEngine can look them up (B-TR-002).
        resolved_id = self._resolve_artifact_id(entity_id)
        results = query(artifact_id=resolved_id, direction=direction)
        if link_type is not None:
            results = [
                r
                for r in results
                if getattr(r, "link_type", None) == link_type
            ]
        return results

    def list_incoming(self, entity_id: UUID, ctx: AuthContext) -> List[TraceEdgeDTO]:
        """List TraceLinks where *entity_id* is the target (MCP-05, Codeberg #117).

        "Incoming" mirrors upstream traversal (QueryEngine returns the link
        sources for links whose target is *entity_id*, see
        propagate_suspect_status below for the upstream/downstream convention).
        """
        neighbors = self.query_trace_links(entity_id, direction="upstream", ctx=ctx)
        return [
            TraceEdgeDTO(
                source_id=n.entity_id, target_id=entity_id, link_type=n.link_type
            )
            for n in neighbors
        ]

    def list_outgoing(self, entity_id: UUID, ctx: AuthContext) -> List[TraceEdgeDTO]:
        """List TraceLinks where *entity_id* is the source (MCP-05, Codeberg #117)."""
        neighbors = self.query_trace_links(entity_id, direction="downstream", ctx=ctx)
        return [
            TraceEdgeDTO(
                source_id=entity_id, target_id=n.entity_id, link_type=n.link_type
            )
            for n in neighbors
        ]

    def propagate_suspect_status(self, source_id: UUID, ctx: AuthContext) -> None:
        """Propagate 'suspect' status to dependent artifacts (SN-30).

        When the artifact ``source_id`` changes, every artifact that DEPENDS ON
        it must be flagged as suspect. In the SE link convention the dependent
        is the SOURCE of the link and the changed artifact is the TARGET
        (e.g. ``TestCase --verifies--> Requirement`` or
        ``ChildReq --derives-from--> ParentReq``). Dependents are therefore
        reached by traversing INCOMING edges — the ``upstream`` direction, where
        the QueryEngine returns the link sources for links whose target is
        ``source_id``.

        The transitive upstream closure is computed by the recursive CTE in the
        QueryEngine, which has built-in cycle detection and no hard depth cap,
        so no dependent is silently truncated (the previous BFS stopped at a
        hard-coded depth of 5). An optional
        ``settings.SUSPECT_PROPAGATION_MAX_DEPTH`` (int) bounds the traversal
        explicitly when configured; the default (``None``) keeps the full hull.
        """
        if ctx is not None:
            self._set_tenant_context(ctx)

        try:
            resolved_id = self._resolve_artifact_id(source_id)
        except NotFoundError:
            return  # Source does not exist or isn't an artifact

        from traceability.services import query

        try:
            # Dependents are UPSTREAM nodes: links where target == resolved_id.
            # transitive=True returns the full (cycle-safe) closure.
            results = query(
                artifact_id=resolved_id,
                direction="upstream",
                transitive=True,
            )

            max_depth = getattr(settings, "SUSPECT_PROPAGATION_MAX_DEPTH", None)
            dependent_ids = {
                r.entity_id
                for r in results
                if max_depth is None or getattr(r, "depth", 1) <= max_depth
            }
            dependent_ids.discard(resolved_id)  # never flag the source itself
            if not dependent_ids:
                return

            from persistence.models import (
                ArchitectureElement,
                Requirement,
                TestCase,
            )

            # Update every reachable dependent entity type.
            Requirement.objects.filter(
                artifact_id__in=dependent_ids
            ).update(suspect=True)
            ArchitectureElement.objects.filter(
                artifact_id__in=dependent_ids
            ).update(suspect=True)
            TestCase.objects.filter(
                artifact_id__in=dependent_ids
            ).update(suspect=True)

            logger.info(
                "Propagated suspect status to %d artifacts from %s",
                len(dependent_ids),
                source_id,
            )
        except Exception:
            # SN-30 must not silently swallow failures: surface the full stack
            # trace and re-raise so callers (and the audit trail) see the error.
            logger.exception(
                "Error propagating suspect status for %s", source_id
            )
            raise



__all__ = [
    "TraceLinkService",
    "SimilarTraceLinkDTO",
    "VALID_LINK_TYPES",
]
