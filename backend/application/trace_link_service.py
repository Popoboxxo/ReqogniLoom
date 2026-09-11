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

GH-484: TestService and IssueService/RiskService used to call
cascade_delete_trace_links(...) on soft-delete (formerly IF-AS-INT-005) —
removed, TraceLinks now survive soft-delete like every other entity so
reactivate() (GH-443) restores them intact. cascade_delete_trace_links()
itself is unchanged and still used by ArtifactService.delete_artifact()
(hard delete, IF-AS-INT-001).

Interfaces consumed:
  IF-AS-EXT-OUT-003  TraceabilityEngine:
      create_trace_link, delete_trace_link, batch_delete_trace_links, query
  link_types.catalog.validate_link_pair:
      always-on, per-workspace endpoint validation for every link type
      (replaces traceability.types.check_se_link_semantics and its se_mode gate)

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
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from django.db.models import Q

from auth_tenancy.context import AuthContext

from application.base import NotFoundError, ServiceBase, ValidationError
from persistence.transactions import atomic_transaction
# VALID_LINK_TYPES/MANUAL_LINK_TYPES are re-exported for backwards
# compatibility only (application.services re-exports them again, and the MCP
# tool schemas still publish MANUAL_LINK_TYPES as their enum). Neither is a
# validation authority any more: link_types.catalog.validate_link_pair is,
# per workspace. See _check_link_pair.
from traceability.types import (  # noqa: F401 — re-exported via __all__
    VALID_LINK_TYPES,
    MANUAL_LINK_TYPES,
    LinkType,
)

if TYPE_CHECKING:  # pragma: no cover — import cycle at runtime
    from persistence.models import Artifact, TraceLink

logger = logging.getLogger(__name__)


class AgentSelfConfirmError(PermissionError):
    """An AI agent tried to confirm or discard a proposal (spec §4.3/§5).

    Mirrors ``workflow.transition_validator``'s rule 0 for the one artifact
    kind that has no workflow state: a trace link.
    """


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

    ``create_trace_link``/``delete_trace_link`` wrap themselves in
    ``@atomic_transaction`` so a failed domain-event outbox insert (SA-02)
    rolls the mutation back instead of silently losing the event.
    ``cascade_delete_trace_links`` is the one exception: per
    ADR-L3-AS005-02 it deliberately runs inside the *caller's* transaction
    context (its only caller, ``ArtifactService.delete_artifact``, is
    itself ``@atomic_transaction``-wrapped) rather than nesting its own —
    the ADR rejects an internal wrapper on complexity grounds (nested
    savepoints), not because atomicity is unwanted there.
    """

    # ---------- IF-AS-INT-002 ----------

    def _resolve_artifact_id(self, entity_id: UUID) -> UUID:
        """Resolve a business-entity ID to its backing Artifact ID.

        Thin wrapper around :meth:`_resolve_artifact` for callers that only
        need the id and would throw the resolved instance away.
        """
        return self._resolve_artifact(entity_id)[0]

    def _resolve_artifact(self, entity_id: UUID) -> tuple[UUID, Optional["Artifact"]]:
        """Resolve a business-entity ID to its backing Artifact (id + row).

        The TraceabilityEngine stores links between Artifact IDs.  Callers may
        pass the more user-facing Requirement, ArchitectureElement, ADR, Goal
        or MainGoal IDs; this helper transparently maps those to their
        backing Artifact.

        Returns the resolved Artifact id **and**, when this method happened to
        read the Artifact row itself, that row — so the caller does not have to
        re-SELECT a row that was just fetched and thrown away (#625).

        The row is only returned for step 1, the "*entity_id* is already an
        Artifact id" case, because that is the only probe that reads
        ``pl_artifact`` at all; it is also the shape every bulk producer uses
        (seeders, importers, and both Layer-3 transports, which resolve ids
        before delegating). The remaining probes read a *business entity* and
        would need an extra join to also produce its Artifact, so they return
        ``None`` and the caller falls back to its own lookup — one query on a
        single interactive request, versus a join on every resolution.

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
          7. If it matches a TestCase, return TestCase.artifact_id (fix #264).
          8. If it matches a StakeholderNeed, return its artifact_id (#264).
          9. If it matches a Risk, return Risk.artifact_id (fix #407).
          10. If it matches an Issue, return Issue.artifact_id (fix #407).
          11. Otherwise raise NotFoundError.

        Fix #264: TestCase and StakeholderNeed were missing from this chain
        even though both are plain ``OneToOneField(Artifact)`` entities like
        Requirement. Every caller that passes the user-facing id — the one
        ``GET /testcases/{id}`` and ``GET /needs/{id}`` return — therefore got
        NotFoundError, which surfaced as a 404 on ``traceability.create_link``
        for ``verifies`` (Requirement -> TestCase) and ``derives-from``
        (Requirement -> StakeholderNeed), i.e. exactly the pairs the SE
        endpoint matrix in ``traceability.types`` advertises as legal.

        Fix #407: Risk and Issue have the same ``OneToOneField(Artifact)``
        shape (see ``application.models.Risk``/``Issue``) but were never
        added here, so a Risk<->Requirement trace link (needed for
        trade-study support) raised NotFoundError on the Risk/Issue side
        even though both are already linkable *targets* once resolved (the
        gap was purely in resolving their business-entity id to an
        Artifact id).

        They are appended at the end rather than next to Requirement so the
        earlier steps keep their established probe order; the id spaces are
        disjoint UUIDs, so order is irrelevant for correctness.
        """
        from persistence.models import (
            ArchitectureElement,
            Artifact,
            Requirement,
        )

        # 1. Already an Artifact ID?
        artifact = Artifact.objects.filter(id=entity_id).first()
        if artifact is not None:
            return entity_id, artifact

        # 2. Requirement -> Artifact
        req = Requirement.objects.filter(id=entity_id).first()
        if req is not None:
            return UUID(str(req.artifact_id)), None

        # 3. ArchitectureElement -> Artifact
        arch = ArchitectureElement.objects.filter(id=entity_id).first()
        if arch is not None:
            return UUID(str(arch.artifact_id)), None

        # 4. ADR -> Artifact (REQ-L2-TE-020). Adr lives in the application app
        # and is not tenant-scoped, so it is imported locally to avoid a
        # circular import (adr_service imports TraceLinkService).
        from application.models import Adr, Goal, MainGoal

        adr = Adr.objects.filter(id=entity_id).first()
        if adr is not None and adr.artifact_id is not None:
            return UUID(str(adr.artifact_id)), None

        # 5. Goal -> Artifact (fix #237).
        goal = Goal.objects.filter(id=entity_id).first()
        if goal is not None:
            return UUID(str(goal.artifact_id)), None

        # 6. MainGoal -> Artifact (fix #237).
        main_goal = MainGoal.objects.filter(id=entity_id).first()
        if main_goal is not None:
            return UUID(str(main_goal.artifact_id)), None

        # 7./8. TestCase / StakeholderNeed -> Artifact (fix #264). Imported
        # locally to keep the module-level import list stable; both are
        # tenant-scoped models, so ``objects`` already applies the tenant
        # filter — a foreign-tenant id stays invisible and still raises below.
        from persistence.models import StakeholderNeed, TestCase

        test_case = TestCase.objects.filter(id=entity_id).first()
        if test_case is not None:
            return UUID(str(test_case.artifact_id)), None

        need = StakeholderNeed.objects.filter(id=entity_id).first()
        if need is not None:
            return UUID(str(need.artifact_id)), None

        # 9./10. Risk / Issue -> Artifact (fix #407). Imported locally, same
        # rationale as Adr/Goal/MainGoal above: application.models imports
        # trace_link_service transitively (risk_service/issue_service ->
        # application.services), so a module-level import would cycle.
        from application.models import Issue, Risk

        risk = Risk.objects.filter(id=entity_id).first()
        if risk is not None and risk.artifact_id is not None:
            return UUID(str(risk.artifact_id)), None

        issue = Issue.objects.filter(id=entity_id).first()
        if issue is not None and issue.artifact_id is not None:
            return UUID(str(issue.artifact_id)), None

        raise NotFoundError(f"Entity {entity_id} not found")

    def resolve_entity_to_artifact_id(
        self, entity_id: UUID, ctx: Optional[AuthContext] = None
    ) -> UUID:
        """Public wrapper around :meth:`_resolve_artifact_id` (fix #264).

        Layer 3 (rest_api, mcp_server) needs the entity -> Artifact mapping to
        report and re-query the endpoints of a link it just created, but must
        not reach into a private method to get it (ADR-01 single entry point).

        Args:
            entity_id: Artifact, Requirement, ArchitectureElement, ADR, Goal,
                MainGoal, TestCase, StakeholderNeed, Risk or Issue UUID.
            ctx: AuthContext; when given, the tenant context is set first.

        Returns:
            The backing Artifact UUID.

        Raises:
            NotFoundError: *entity_id* matches none of the known tables.
        """
        if ctx is not None:
            self._set_tenant_context(ctx)
        return self._resolve_artifact_id(entity_id)

    def _check_link_pair(
        self,
        source_artifact_id: UUID,
        target_artifact_id: UUID,
        link_type: str,
        *,
        source_artifact: Optional["Artifact"] = None,
        target_artifact: Optional["Artifact"] = None,
        manual: bool = True,
    ) -> None:
        """Validate a link against the workspace's link-type catalog.

        Replaces the former ``_check_se_semantics``. Three escape hatches are
        gone on purpose (spec section 3.2, "gilt immer"):

        * the ``se_mode`` probe — a dev_mode or unconfigured workspace used to
          skip enforcement entirely;
        * the ``SE_CORE_ARTIFACT_TYPES`` allow-list — a Risk endpoint used to
          pass unchecked, which is audit finding U2 exactly;
        * the blanket ``except Exception: return`` — a resolution failure used
          to wave the link through instead of failing.

        The ids stay authoritative: a passed-in row is an optimisation, never
        a substitute. A mismatch drops the row and re-reads the real one —
        this is a validation gate, and checking the wrong endpoints silently
        is worse than one extra SELECT.

        Args:
            source_artifact_id: Resolved source Artifact id.
            target_artifact_id: Resolved target Artifact id.
            link_type: The catalog key under validation.
            source_artifact: Already-loaded source row, if the caller has one.
            target_artifact: Same for the target endpoint.
            manual: False only for system writers (the diagram reconciler),
                which may write ``system_owned`` types.

        Raises:
            ValidationError: Unknown/inactive type, a system-owned type on the
                manual path, or a disallowed endpoint pair.
            NotFoundError: Either endpoint does not exist.
        """
        from link_types.catalog import validate_link_pair
        from persistence.models import Artifact

        source = source_artifact
        if source is not None and str(source.id) != str(source_artifact_id):
            source = None
        if source is None:
            source = Artifact.objects.filter(id=source_artifact_id).first()

        target = target_artifact
        if target is not None and str(target.id) != str(target_artifact_id):
            target = None
        if target is None:
            target = Artifact.objects.filter(id=target_artifact_id).first()

        # Unlike the old permissive fallback, a missing endpoint is no longer
        # a reason to skip the gate: it is a hard error raised here rather
        # than an opaque IntegrityError further down.
        if source is None:
            raise NotFoundError("Source entity not found")
        if target is None:
            raise NotFoundError("Target entity not found")

        validate_link_pair(
            source.workspace_id,
            link_type,
            source.artifact_type,
            target.artifact_type,
            manual=manual,
        )

    @atomic_transaction
    def create_trace_link(
        self,
        source_id: UUID,
        target_id: UUID,
        link_type: str,
        ctx: AuthContext,
        rationale: str = "",
    ):
        """Create a single TraceLink after validation.

        REQ-L2-AS-010: validates existence, workspace membership, link type.
        Accepts Artifact, Requirement or ArchitectureElement IDs for
        *source_id* and *target_id* and resolves them to Artifact IDs before
        delegating to the TraceabilityEngine.

        Args:
            source_id: UUID of the source artifact or derived entity.
            target_id: UUID of the target artifact or derived entity.
            link_type: A key of this workspace's link-type catalog.
            ctx: Resolved AuthContext.
            rationale: Q1.6 — why *these two* artifacts are linked. Optional
                free text; empty string means "not stated".

        Returns:
            Created TraceLink ORM instance.

        Raises:
            ValidationError: Unknown/inactive link_type, a system-managed type
                ('diagram-ref') on the manual path, an endpoint pair the type
                does not allow, or a cross-workspace link.
            NotFoundError:   Source or target entity does not exist.
        """
        self._set_tenant_context(ctx)

        # Resolve Requirement/ArchitectureElement IDs to Artifact IDs. The
        # Artifact rows come back with the ids so the checks below can reuse
        # them instead of re-SELECTing the same two rows (see #625: seeding the
        # E2E fixture workspace issued ~13k single-row pl_artifact SELECTs,
        # because each link creation read its two endpoints up to six times).
        resolved_source, source_artifact = self._resolve_artifact(source_id)
        resolved_target, target_artifact = self._resolve_artifact(target_id)

        # Catalog validation: link type must exist, be active, be manually
        # creatable, and allow this endpoint pair. Applies to every workspace
        # and every artifact type — the se_mode gate and the "non-core types
        # pass unchecked" escape are gone (spec section 3.2). This is also
        # what rejects a hand-authored 'diagram-ref' (system_owned, see
        # link_types/builtin.py), which used to be a hardcoded branch here.
        self._check_link_pair(
            resolved_source,
            resolved_target,
            link_type,
            source_artifact=source_artifact,
            target_artifact=target_artifact,
            manual=True,
        )

        # REQ-L1-044 I4: allocated-to must not target an ancestor of the
        # source (Extended rigor only, gated inside the validator).
        if link_type == LinkType.ALLOCATED_TO:
            self._check_allocation_invariant(resolved_source, resolved_target)

        from django.db import IntegrityError

        from traceability.services import (
            CrossTenantLinkError,
            SourceNotFoundError,
            TargetNotFoundError,
            TraceLinkError,
            create_trace_link as te_create,
        )

        try:
            result = te_create(
                source_id=resolved_source,
                target_id=resolved_target,
                link_type=link_type,
                created_by_id=ctx.user_id,
                rationale=rationale,
            )
        except SourceNotFoundError as exc:
            raise NotFoundError("Source entity not found") from exc
        except TargetNotFoundError as exc:
            raise NotFoundError("Target entity not found") from exc
        except IntegrityError as exc:
            # uq_tracelink_edge (issue #126): the identical edge already
            # exists. A duplicate is a client error, not a server fault.
            raise ValidationError(
                f"A '{link_type}' link between these two artifacts already exists"
            ) from exc
        except TraceLinkError as exc:
            # Fix #264 (Befund C): CycleDetectedError / CrossTenantLinkError /
            # InvalidLinkTypeError derive from Exception, not from this
            # layer's ValidationError, so they used to travel unmapped through
            # Layer 2 and out of the MCP tool — which only catches
            # NotFound/Validation/PermissionDenied — and became an opaque
            # HTTP 500 (-32603). They are all rejected *inputs*, so they map
            # to ValidationError and the caller gets a 400 with the reason.
            if isinstance(exc, CrossTenantLinkError):
                raise ValidationError(
                    "Cross-workspace TraceLinks are not permitted"
                ) from exc
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            # Re-map cross-tenant errors as ValidationError
            msg = str(exc)
            if "cross" in msg.lower() or "tenant" in msg.lower():
                raise ValidationError(
                    "Cross-workspace TraceLinks are not permitted"
                ) from exc
            raise

        # Spec §5: a link an agent created is a proposal until a human
        # confirms it. ``api_key_id`` is the proposing key; a bearer-token
        # (human) request leaves both fields NULL. Stamped as a targeted
        # update rather than threaded through traceability.services.create_
        # trace_link / TraceLinkManager.create, which are shared by every
        # other caller and have no notion of "proposal".
        if ctx.actor_type == "agent" and ctx.api_key_id is not None:
            from django.utils import timezone

            from persistence.models import TraceLink

            proposed_at = timezone.now()
            TraceLink.objects.filter(id=result.id).update(
                proposed_by_id=ctx.api_key_id, proposed_at=proposed_at
            )
            result.proposed_by_id = ctx.api_key_id
            result.proposed_at = proposed_at

        # REQ-L2-VS-004: best-effort semantic embedding for similarity search.
        self._generate_and_store_embedding(result)

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="TraceLink",
            entity_id=result.id if hasattr(result, "id") else source_id,
        )
        self._emit_trace_link_event(
            event_type_name="TRACE_LINK_CREATED",
            link_id=getattr(result, "id", None),
            source_artifact_id=resolved_source,
            target_artifact_id=resolved_target,
            source_artifact=source_artifact,
        )
        return result

    def confirm_proposed_link(self, link_id: UUID, ctx: AuthContext) -> "TraceLink":
        """Accept an agent-proposed trace link (spec §5).

        Clears ``proposed_by``/``proposed_at`` — the link becomes an ordinary,
        human-owned edge. Idempotent: confirming an already-confirmed link is a
        no-op that returns it unchanged.

        Args:
            link_id: TraceLink primary key.
            ctx: The confirming principal.

        Returns:
            The refreshed TraceLink.

        Raises:
            AgentSelfConfirmError: ``ctx`` is an agent.
            NotFoundError: no such link in the active tenant.
        """
        from persistence.models import TraceLink

        self._set_tenant_context(ctx)
        if ctx.actor_type == "agent":
            raise AgentSelfConfirmError(
                "An AI agent may not confirm a proposed trace link."
            )
        link = TraceLink.objects.filter(id=link_id).first()
        if link is None:
            raise NotFoundError(f"TraceLink {link_id} not found")
        if link.proposed_at is not None or link.proposed_by_id is not None:
            link.proposed_by = None
            link.proposed_at = None
            link.save(update_fields=["proposed_by", "proposed_at", "modified_at"])
            self._audit(
                ctx=ctx,
                operation="update",
                entity_type="TraceLink",
                entity_id=link.id,
                details={"proposal": "confirmed"},
            )
        return link

    def discard_proposed_link(self, link_id: UUID, ctx: AuthContext) -> None:
        """Reject an agent-proposed trace link by deleting it (spec §5).

        Args:
            link_id: TraceLink primary key.
            ctx: The rejecting principal.

        Raises:
            AgentSelfConfirmError: ``ctx`` is an agent.
            NotFoundError: no such link in the active tenant.
            ValueError: the link is not a proposal — deleting a confirmed link
                goes through the normal delete path, not this one.
        """
        from persistence.models import TraceLink

        self._set_tenant_context(ctx)
        if ctx.actor_type == "agent":
            raise AgentSelfConfirmError(
                "An AI agent may not discard a proposed trace link."
            )
        link = TraceLink.objects.filter(id=link_id).first()
        if link is None:
            raise NotFoundError(f"TraceLink {link_id} not found")
        if not link.is_proposal:
            raise ValueError(
                "TraceLink is not a proposal; use the regular delete endpoint."
            )
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="TraceLink",
            entity_id=link.id,
            details={"proposal": "discarded"},
        )
        link.delete()

    def _emit_trace_link_event(
        self,
        *,
        event_type_name: str,
        link_id: Optional[UUID],
        source_artifact_id: UUID,
        target_artifact_id: UUID,
        source_artifact: Optional["Artifact"] = None,
    ) -> None:
        """Emit a TraceLink* domain event (Issue #377, context_graph Task 2).

        A link has a source AND a target artifact, so unlike every other
        producer's ``payload["artifact_id"]``, TraceLink events carry
        ``source_artifact_id``/``target_artifact_id`` — the projector
        re-derives both endpoints (Task 4). ``entity_id`` is the TraceLink's
        own id (falls back to the source artifact id if the link row is
        unavailable, e.g. a caller that only has the ids post-delete).

        Best-effort resolution, like :meth:`_generate_and_store_embedding`
        below: looking up the workspace id must never fail (or need an
        active tenant context in unit tests, most of which mock
        ``_set_tenant_context`` away entirely per this file's own test
        suite convention) the surrounding create/delete it's attached to —
        see Task 2's "Must not break" clause. That guarantee covers only
        the *lookup*: once a workspace id is known, the actual outbox
        insert (:meth:`_emit_event`) runs unguarded, so a real write
        failure there propagates and rolls back the enclosing
        ``@atomic_transaction`` (SA-02) instead of being swallowed here.
        """
        try:
            from application.models import DomainEventOutbox
            from persistence.models import Artifact

            workspace_id = None
            if source_artifact is not None:
                workspace_id = source_artifact.workspace_id
            if workspace_id is None:
                workspace_id = (
                    Artifact.objects.filter(id=source_artifact_id)
                    .values_list("workspace_id", flat=True)
                    .first()
                )
        except Exception as exc:  # noqa: BLE001 — best-effort, see docstring
            logger.debug(
                "TraceLinkService: %s workspace lookup failed for link=%s: %s",
                event_type_name,
                link_id,
                exc,
            )
            return

        if workspace_id is None:
            # Source artifact already gone (hard-delete cascade) — nothing
            # left to scope the event to; skip rather than emit a
            # malformed event with no workspace.
            return

        self._emit_event(
            self._make_event(
                event_type=getattr(DomainEventOutbox.EventType, event_type_name),
                entity_id=link_id or source_artifact_id,
                workspace_id=workspace_id,
                payload={
                    "source_artifact_id": str(source_artifact_id),
                    "target_artifact_id": str(target_artifact_id),
                },
            )
        )

    # ---------- Semantic similarity (REQ-L2-VS-004) ----------

    @staticmethod
    def _generate_and_store_embedding(trace_link) -> None:
        """Best-effort: generate and persist the trace link's embedding.

        REQ-L2-VS-004. Uses a bare ``.update()`` so it neither bumps the
        version nor emits a domain event. Never raises: the embedding is
        supplementary, so a provider/network failure must not fail the
        surrounding create transaction. Mirrors
        RequirementService._generate_and_store_embedding.

        The embedding text is built from the two endpoint *titles*, which live
        on the reverse OneToOne ``artifact.requirement`` /
        ``artifact.architecture_element`` relations. On a freshly created link
        none of those are cached, so ``get_tracelink_embedding_text`` used to
        trigger up to four extra single-row SELECTs per link (#625). One
        ``select_related`` re-read collapses them into a single joined query.
        """
        try:
            from persistence.models import TraceLink
            from llm_adapter.embedding_service import (
                generate_embedding,
                get_tracelink_embedding_text,
                warn_dimension_mismatch,
            )

            if not getattr(trace_link, "id", None):
                return
            joined = (
                TraceLink.objects.filter(id=trace_link.id)
                .select_related(
                    "source__requirement",
                    "source__architecture_element",
                    "target__requirement",
                    "target__architecture_element",
                )
                # Neither the link's own vector nor the endpoints' are read
                # here — only their titles. Leaving them in would drag three
                # embedding vectors per link through the ORM, the #571 shape.
                .defer(
                    "embedding",
                    "source__requirement__embedding",
                    "target__requirement__embedding",
                )
                .first()
            )
            embedding = generate_embedding(
                get_tracelink_embedding_text(joined or trace_link)
            )
            field_dimensions = TraceLink._meta.get_field("embedding").dimensions
            if embedding is not None and len(embedding) == field_dimensions:
                TraceLink.objects.filter(id=trace_link.id).update(embedding=embedding)
            elif embedding is not None:
                # Dimension mismatch (a non-default EMBEDDING_PROVIDER whose
                # native width differs from EMBEDDING_VECTOR_DIMENSIONS — see
                # RequirementService._generate_and_store_embedding and #794
                # for the full rationale): skip the write rather than let a
                # Postgres-level DataError poison the ambient transaction.
                warn_dimension_mismatch(
                    "TraceLinkService", len(embedding), field_dimensions
                )
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

    # ---------- IF-AS-INT-001 (hard delete only, GH-484) ----------

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

        # Snapshot endpoints before delete (Issue #377 Task 2) — batch paths
        # emit one event per affected link, not one batched event, so the
        # projector's per-artifact re-derivation stays simple (Task 4).
        # Best-effort like _emit_trace_link_event itself (see its docstring):
        # this must never block the actual deletion.
        from persistence.models import TraceLink

        try:
            endpoints = list(
                TraceLink.objects.filter(id__in=link_ids).values("id", "source_id", "target_id")
            )
        except Exception:  # noqa: BLE001 — best-effort, see comment above
            endpoints = []

        deleted = batch_delete_trace_links(link_ids)

        for row in endpoints:
            self._emit_trace_link_event(
                event_type_name="TRACE_LINK_DELETED",
                link_id=row["id"],
                source_artifact_id=row["source_id"],
                target_artifact_id=row["target_id"],
            )
        return deleted

    @atomic_transaction
    def delete_trace_link(self, link_id: UUID, ctx: AuthContext) -> None:
        """Delete a single TraceLink by its own id (Codeberg #336).

        Unlike :meth:`cascade_delete_trace_links` (which deletes links whose
        source/target matches an *entity* id), this deletes the TraceLink
        identified by *link_id* itself, e.g. for ``DELETE
        /api/v1/trace-links/{id}/``.

        Raises:
            NotFoundError: *link_id* does not exist in the active tenant.
            AgentSelfConfirmError: ``ctx`` is an agent and the link is still a
                proposal (Rule 0, security review M1).
        """
        from persistence.models import TraceLink
        from traceability.trace_link_manager import TraceLinkManager

        self._set_tenant_context(ctx)

        # Snapshot endpoints before delete (Issue #377 Task 2) — gone once
        # TraceLinkManager().delete() removes the row. Best-effort, same as
        # above: must never block the actual deletion.
        try:
            row = (
                TraceLink.objects.filter(id=link_id)
                .values("source_id", "target_id", "proposed_by_id", "proposed_at")
                .first()
            )
        except Exception:  # noqa: BLE001 — best-effort, see comment above
            row = None

        # Rule 0 (security review M1): ``discard_proposed_link`` refuses an
        # agent, but this generic delete reaches the very same row and used to
        # let the proposing agent erase its own proposal — the human review
        # disappears either way, so the same rule has to hold on both paths.
        # Deliberately NOT best-effort: a security guard that silently skips on
        # a lookup failure is not a guard.
        if ctx.actor_type == "agent" and row is not None and (
            row["proposed_by_id"] is not None or row["proposed_at"] is not None
        ):
            raise AgentSelfConfirmError(
                "An AI agent may not delete a proposed trace link. A human "
                "principal must confirm or discard it."
            )

        try:
            TraceLinkManager().delete(link_id)
        except TraceLink.DoesNotExist as exc:
            raise NotFoundError(f"TraceLink {link_id} not found") from exc

        if row is not None:
            self._emit_trace_link_event(
                event_type_name="TRACE_LINK_DELETED",
                link_id=link_id,
                source_artifact_id=row["source_id"],
                target_artifact_id=row["target_id"],
            )

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

    def list_links_for_entity(
        self,
        entity_id: UUID,
        direction: str,
        ctx: AuthContext,
        link_type: Optional[str] = None,
    ) -> list:
        """Return the real TraceLink rows attached to *entity_id* (fix #264).

        Unlike :meth:`query_trace_links`, which returns ``NeighborResult``
        projections carrying only the *neighbour* endpoint, this returns the
        persisted TraceLink ORM instances — with their own primary key and
        both endpoints. That is what a caller needs to prove that a link
        created via :meth:`create_trace_link` actually reached the database
        (Befund B in #264: the write succeeded but every read-back path
        reported nothing, which looked like silent data loss).

        Args:
            entity_id: Artifact or business-entity UUID (resolved internally).
            direction: ``"upstream"`` (entity is the link target) or
                ``"downstream"`` (entity is the link source).
            ctx: AuthContext for tenant scoping.
            link_type: Optional link-type filter.

        Returns:
            List of TraceLink ORM instances.

        Raises:
            NotFoundError: *entity_id* resolves to no known entity.
            ValidationError: *direction* is neither upstream nor downstream.
        """
        if direction not in ("upstream", "downstream"):
            raise ValidationError(
                f"Invalid direction '{direction}'. "
                "Valid directions: ['downstream', 'upstream']"
            )

        self._set_tenant_context(ctx)
        resolved_id = self._resolve_artifact_id(entity_id)

        from traceability.services import list_trace_links

        key = "target_id" if direction == "upstream" else "source_id"
        return list_trace_links(
            filters={key: resolved_id}, link_type=link_type
        )

    def list_links_for_workspace(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        link_type: Optional[str] = None,
    ) -> list:
        """Return every TraceLink whose source lives in *workspace_id* (#264).

        Backs the workspace-level listing of ``GET /api/v1/tracelinks/``,
        which previously returned an unconditional empty page — so a caller
        verifying a freshly created link that way always saw ``count: 0``
        regardless of what was in the database (Befund B in #264).
        """
        self._set_tenant_context(ctx)

        from traceability.services import list_trace_links

        return list_trace_links(workspace_id=workspace_id, link_type=link_type)

    def list_links_for_workspace_queryset(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        link_type: Optional[str] = None,
    ):
        """Lazy variant of :meth:`list_links_for_workspace` (fix #571).

        Returns the queryset itself (not materialized) so the REST layer can
        apply DB-level pagination instead of loading every TraceLink in the
        workspace into memory before slicing — see
        ``traceability.services.list_trace_links_queryset``.
        """
        self._set_tenant_context(ctx)

        from traceability.services import list_trace_links_queryset

        return list_trace_links_queryset(workspace_id=workspace_id, link_type=link_type)

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

    def propagate_suspect_status(
        self,
        source_id: UUID,
        ctx: AuthContext,
        *,
        audit_entry_id: Optional[UUID] = None,
    ) -> int:
        """Flag the artifacts a change to *source_id* makes questionable (SN-30).

        Dispatches on each link type's ``suspect_rule`` from the workspace
        catalog rather than flooding a direction-agnostic transitive hull.
        This is the mechanism behind P0 issue #849: the ``suspect`` column and
        its serializer field already existed, but nothing ever consulted the
        link type, so ``allocated-to`` (which propagates source -> target)
        never fired at all and ``references`` fired when it should not have.

        Rule dispatch (direction convention: ``decomposes`` runs
        parent -> child, ``derives-from`` runs child -> parent — see
        ``traceability/audit/hierarchy.py``)::

            target_change_flags_source     changed == link.target -> flag source
            source_change_flags_target     changed == link.source -> flag target
            parent_change_flags_children   changed == link.source (the parent)
                                                            -> flag target (child)
            none                           nothing

        ``parent_change_flags_children`` shares the ``source_change_flags_target``
        branch on purpose: for a hierarchy link the parent *is* the source, so
        the two are the same traversal. It stays a distinct configurable value
        because it documents intent for hierarchy types.

        **One hop only.** The previous implementation walked the full recursive
        CTE closure; the spec describes a single hop, and each flagged artifact
        propagates further when *it* is edited. ``SUSPECT_PROPAGATION_MAX_DEPTH``
        is consequently no longer read.

        Args:
            source_id: The artifact (or business entity) that changed.
            ctx: Resolved AuthContext.
            audit_entry_id: ``audit.AuditEntry.id`` of the triggering change,
                recorded on every link that actually *caused a flag* — not on
                every link whose rule matched. A link whose far end is a type
                with no ``suspect`` column, or is already suspect, fires no
                flag and is therefore left unstamped.

        Returns:
            Number of artifacts newly flagged suspect.
        """
        if ctx is not None:
            self._set_tenant_context(ctx)

        try:
            resolved_id = self._resolve_artifact_id(source_id)
        except NotFoundError:
            return 0

        from django.utils import timezone

        from link_types.catalog import resolve_catalog
        from persistence.models import (
            ArchitectureElement,
            Artifact,
            Requirement,
            TestCase,
            TraceLink,
        )

        artifact = Artifact.objects.filter(id=resolved_id).only("workspace_id").first()
        if artifact is None:
            return 0
        catalog = resolve_catalog(artifact.workspace_id)

        # One query for both directions; the rule decides which side counts.
        links = list(
            TraceLink.objects.filter(
                Q(source_id=resolved_id) | Q(target_id=resolved_id)
            ).only("id", "source_id", "target_id", "link_type")
        )

        dependent_ids: set[UUID] = set()
        # (link id, the artifact id at the *other* end). The second element is
        # what decides whether the link may carry the provenance stamp below.
        fired: list[tuple[UUID, UUID]] = []

        for link in links:
            definition = catalog.get(link.link_type)
            if definition is None:
                continue  # unknown or deactivated type: no propagation
            rule = definition.get("suspect_rule", "none")
            if rule == "none":
                continue

            if rule == "target_change_flags_source":
                if link.target_id != resolved_id:
                    continue
                other_id = link.source_id
            elif rule in ("source_change_flags_target", "parent_change_flags_children"):
                # Identical traversal: for a hierarchy link the parent is the
                # source (see the direction table in the docstring).
                if link.source_id != resolved_id:
                    continue
                other_id = link.target_id
            else:
                logger.warning(
                    "Unknown suspect_rule '%s' on link type '%s'; skipping.",
                    rule,
                    link.link_type,
                )
                continue

            if other_id == resolved_id:
                continue  # self-link: never flag the changed artifact itself
            dependent_ids.add(other_id)
            fired.append((link.id, other_id))

        if not dependent_ids:
            return 0

        # Only these three models carry a `suspect` column today (see the
        # Merkposten in the Task 14 ledger entry: it belongs on `Artifact`).
        # An `Adr`/`Risk`/`StakeholderNeed`/`Goal`/`Issue` at the far end is
        # silently skipped — and so is an artifact that was already suspect.
        flagged = 0
        newly_flagged_ids: set[UUID] = set()
        for model in (Requirement, ArchitectureElement, TestCase):
            candidate_ids = set(
                model.objects.filter(
                    artifact_id__in=dependent_ids, suspect=False
                ).values_list("artifact_id", flat=True)
            )
            if not candidate_ids:
                continue
            written = model.objects.filter(
                artifact_id__in=candidate_ids, suspect=False
            ).update(suspect=True)
            if written:
                flagged += written
                newly_flagged_ids |= candidate_ids

        # `suspect_flagged_at`'s own help_text says it is set "when this link
        # caused the other endpoint to be flagged suspect", so only links that
        # actually did may be stamped. Stamping every link whose *rule* matched
        # wrote that provenance marker for links whose far end was a
        # non-flaggable type, or was already suspect — a false audit trail
        # pointing at a flag that never happened.
        stamped_link_ids = [
            link_id for link_id, other_id in fired if other_id in newly_flagged_ids
        ]
        if stamped_link_ids:
            TraceLink.objects.filter(id__in=stamped_link_ids).update(
                suspect_flagged_at=timezone.now(),
                suspect_source_change=audit_entry_id,
            )

        logger.info(
            "Suspect propagation from %s: %d artifact(s) flagged; "
            "%d of %d matching link(s) stamped.",
            resolved_id,
            flagged,
            len(stamped_link_ids),
            len(fired),
        )
        return flagged


__all__ = [
    "TraceLinkService",
    "SimilarTraceLinkDTO",
    "VALID_LINK_TYPES",
    "MANUAL_LINK_TYPES",
]
