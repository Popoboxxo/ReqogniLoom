"""
COMP-AS-014 RiskService — Risk CRUD with Score Calculation.

leaf_id : COMP-AS-014
req_id  : REQ-L1-029

Orchestrates:
  IF-AS-INT-002   TraceLinkService.create_trace_link
  IF-AS-INT-003   WorkflowFacade.transition (status transitions)
  IF-AS-INT-016   DomainEventBus → RiskCreated/Updated/Deleted (Outbox)
  IF-AS-EXT-OUT-007  application.models.Risk (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-014_RiskService/
      L3_COMP-AS-014_RiskService_Architecture.md

ADR-L3-RISK-01: Automatic risk score calculation (probability × impact).
ADR-L3-RISK-02: Enum probability/impact (low=1, medium=2, high=3).
ADR-L3-RISK-03: Score-range query support for SeMetrics integration.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from django.db.models import F, QuerySet
from persistence.transactions import atomic_transaction

from application.artifact_service import (
    has_field_changes,
    snapshot_versioned_fields,
)
from application.base import NotFoundError, ServiceBase, ValidationError
from application.models import DomainEventOutbox, Risk
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)
from workflow import state_reader

logger = logging.getLogger(__name__)

# Supported TraceLink types for Risks (REQ-L3-RISK-006)
RISK_LINK_TYPES = frozenset({"threatens", "mitigated-by", "related-to"})


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class RiskDTO:
    """Read-oriented DTO returned by RiskService methods.

    leaf_id : COMP-AS-014
    req_id  : REQ-L1-029
    """

    id: UUID
    workspace_id: UUID
    tenant_id: UUID
    title: str
    description: str
    category: str
    probability: str
    impact: str
    risk_score: int
    severity: str
    owner: str
    mitigation_strategy: str
    status: str
    version: int

    @classmethod
    def from_orm(cls, risk: Risk, *, status: str = "") -> "RiskDTO":
        """Build a DTO. ``status`` comes from the workflow engine (Phase 1)."""
        resolved_status = status
        return cls(
            id=risk.id,
            workspace_id=risk.workspace_id,
            tenant_id=risk.tenant_id,
            title=risk.title,
            description=risk.description,
            category=risk.category,
            probability=risk.probability,
            impact=risk.impact,
            risk_score=risk.risk_score,
            severity=risk.severity,
            owner=risk.owner,
            mitigation_strategy=risk.mitigation_strategy,
            status=resolved_status,
            version=risk.version,
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class RiskValidator:
    """Schema validation for Risk payloads (REQ-L3-RISK-002).

    leaf_id : COMP-AS-014
    req_id  : REQ-L1-029
    """

    VALID_PROBABILITIES = frozenset(Risk.Probability.values)
    VALID_IMPACTS = frozenset(Risk.Impact.values)
    VALID_CATEGORIES = frozenset(Risk.Category.values)
    # Datenmodell-Konsolidierung Phase 1: still used by transition_status()'s
    # target-state validation — unrelated to create-time status, which is
    # retired below (no longer a validate_create input).
    VALID_STATUSES = frozenset(Risk.RiskStatus.values)

    @classmethod
    def validate_create(
        cls,
        title: str,
        probability: str,
        impact: str,
        category: str = "technical",
    ) -> None:
        """Validate fields for Risk creation. Status is not an input (Phase 1)."""
        if not title:
            raise ValidationError("Risk title is required")
        if probability not in cls.VALID_PROBABILITIES:
            raise ValidationError(
                f"Risk probability '{probability}' invalid; "
                f"must be one of {sorted(cls.VALID_PROBABILITIES)}"
            )
        if impact not in cls.VALID_IMPACTS:
            raise ValidationError(
                f"Risk impact '{impact}' invalid; "
                f"must be one of {sorted(cls.VALID_IMPACTS)}"
            )
        if category not in cls.VALID_CATEGORIES:
            raise ValidationError(
                f"Risk category '{category}' invalid; "
                f"must be one of {sorted(cls.VALID_CATEGORIES)}"
            )


# ---------------------------------------------------------------------------
# RiskService
# ---------------------------------------------------------------------------


class RiskService(ServiceBase):
    """COMP-AS-014 — Risk CRUD with automatic score calculation and TraceLinks.

    leaf_id : COMP-AS-014
    req_id  : REQ-L1-029
    """

    def __init__(
        self,
        trace_link_service=None,
    ) -> None:
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- CRUD ----------

    @atomic_transaction
    def create_risk(
        self,
        workspace_id: UUID,
        title: str,
        probability: str,
        impact: str,
        ctx: AuthContext,
        description: str = "",
        category: str = "technical",
        owner: str = "",
        mitigation_strategy: str = "",
        uid: Optional[str] = None,
        detection: int = 5,
        owner_user_id: Optional[UUID] = None,
    ) -> Risk:
        """Create a Risk with automatic score calculation (REQ-L3-RISK-001/002/007).

        The initial state comes from the workflow definition, not from the
        caller (Datenmodell-Konsolidierung Phase 1).

        Args:
            workspace_id: Target workspace UUID.
            title: Risk title.
            probability: One of {"low", "medium", "high"}.
            impact: One of {"low", "medium", "high"}.
            ctx: Resolved AuthContext.
            description: Optional description.
            category: One of {"technical", "operational", "organizational", "business"}.
            owner: Optional owner identifier.
            mitigation_strategy: Optional mitigation description.
            detection: FMEA detection score, 1 (easy) .. 10 (impossible). Default 5
                (REQ-L1-029).
            owner_user_id: Optional User FK for structured risk assignment
                (REQ-L1-029), kept alongside the legacy free-text `owner` field.

        Returns:
            Persisted Risk ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        RiskValidator.validate_create(
            title=title, probability=probability, impact=impact, category=category
        )
        if not 1 <= detection <= 10:
            raise ValidationError(
                f"Risk detection '{detection}' invalid; must be between 1 and 10"
            )

        # REQ-L2-TE-020: create the backing Artifact first so the Risk can
        # participate in the Artifact-to-Artifact TraceLink graph. Mirrors
        # AdrService.create_adr. Replaces the former UUID-identity hack.
        from persistence.models import Artifact, Tenant, Workspace

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Risk",
        )

        # Datenmodell-Konsolidierung Phase 1: `status` is no longer a create
        # parameter at all — WorkflowItemState.current_state (seeded below
        # from the workflow definition's initial_state) is the sole
        # authority. The model field's own default keeps the column non-null
        # until it is dropped (Task 12).
        risk = Risk(
            artifact=artifact,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            category=category,
            probability=probability,
            impact=impact,
            owner=owner,
            mitigation_strategy=mitigation_strategy,
            uid=uid,
            detection=detection,
            owner_user_id=owner_user_id,
            created_by=str(ctx.user_id),
        )
        # Calculate score before save (ADR-L3-RISK-01)
        score = risk.compute_score()
        risk.risk_score = score
        risk.severity = Risk.score_to_severity(score)
        risk.save()

        # Initialize workflow state
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[risk.id],
                item_type="Risk",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug("RiskService: workflow init skipped for risk=%s", risk.id)

        self._audit(ctx=ctx, operation="create", entity_type="Risk", entity_id=risk.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.RISK_CREATED,
                entity_id=risk.id,
                workspace_id=workspace_id,
                payload={"title": title, "risk_score": score, "severity": risk.severity},
            )
        )
        return risk

    @atomic_transaction
    def update_risk(
        self,
        risk_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        probability: Optional[str] = None,
        impact: Optional[str] = None,
        category: Optional[str] = None,
        owner: Optional[str] = None,
        mitigation_strategy: Optional[str] = None,
        change_reason: Optional[str] = None,
        detection: Optional[int] = None,
        owner_user_id: Optional[UUID] = None,
        expected_version: Optional[int] = None,
    ) -> Risk:
        """Update a Risk, recomputing score when probability/impact change (REQ-L3-RISK-003).

        Args:
            risk_id: UUID of the Risk to update.
            ctx: Resolved AuthContext.
            title: New title (optional).
            description: New description (optional).
            probability: New probability (optional, recalculates score).
            impact: New impact (optional, recalculates score).
            category: New category (optional).
            owner: New owner (optional).
            mitigation_strategy: New mitigation text (optional).
            change_reason: Optional change rationale for audit.
            detection: New FMEA detection score, 1..10 (optional, REQ-L1-029).
            owner_user_id: New User FK for structured risk assignment (optional,
                REQ-L1-029).
            expected_version: Caller's last-seen ``version``. When supplied and
                stale, the update is refused with ``OptimisticLockError`` (409)
                instead of overwriting a concurrent edit. Omitting it keeps the
                previous last-writer-wins behaviour.

        Returns:
            Updated Risk ORM instance.

        Raises:
            OptimisticLockError: *expected_version* does not match the stored one.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        risk = lock_for_version_check(
            Risk.objects.filter(id=risk_id, tenant_id=ctx.tenant_id), expected_version
        ).first()
        if risk is None:
            raise NotFoundError(f"Risk {risk_id} not found")
        assert_expected_version(risk, expected_version, entity_type="Risk")

        # #269 finding 5: snapshot BEFORE any assignment so the version bump
        # below can be gated on a real value change. Taken before the
        # score/severity recomputation too, so a recompute that lands on the
        # same values is correctly treated as a no-op.
        _before = snapshot_versioned_fields(risk)

        if title is not None:
            risk.title = title
        if description is not None:
            risk.description = description
        if probability is not None:
            if probability not in RiskValidator.VALID_PROBABILITIES:
                raise ValidationError(f"Invalid probability '{probability}'")
            risk.probability = probability
        if impact is not None:
            if impact not in RiskValidator.VALID_IMPACTS:
                raise ValidationError(f"Invalid impact '{impact}'")
            risk.impact = impact
        if category is not None:
            if category not in RiskValidator.VALID_CATEGORIES:
                raise ValidationError(f"Invalid category '{category}'")
            risk.category = category
        if owner is not None:
            risk.owner = owner
        if mitigation_strategy is not None:
            risk.mitigation_strategy = mitigation_strategy
        if detection is not None:
            if not 1 <= detection <= 10:
                raise ValidationError(
                    f"Risk detection '{detection}' invalid; must be between 1 and 10"
                )
            risk.detection = detection
        if owner_user_id is not None:
            risk.owner_user_id = owner_user_id

        # Recompute score whenever probability or impact changed (ADR-L3-RISK-01)
        score = risk.compute_score()
        risk.risk_score = score
        risk.severity = Risk.score_to_severity(score)
        # Atomic version increment (REQ-L3-PL001-002): save payload fields first,
        # then issue a single SQL UPDATE that increments version at the database
        # level — avoids the read-modify-write race condition of `version += 1`.
        # #269 finding 5: only a real value change is a new revision.
        risk.save()
        if has_field_changes(risk, _before):
            Risk.objects.filter(id=risk.id).update(version=F("version") + 1)
            risk.refresh_from_db(fields=["version"])

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Risk",
            entity_id=risk_id,
            change_reason=change_reason,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.RISK_UPDATED,
                entity_id=risk_id,
                workspace_id=risk.workspace_id,
                payload={
                    "change_reason": change_reason,
                    "risk_score": score,
                    "severity": risk.severity,
                    "version": risk.version,
                },
            )
        )
        return risk

    @atomic_transaction
    def delete_risk(self, risk_id: UUID, ctx: AuthContext) -> None:
        """Soft-delete a Risk via the workflow engine (REQ-L3-RISK-004).

        GH-484: TraceLinks are no longer hard-deleted on soft-delete — they
        survive alongside the outdated Risk, symmetric with
        Requirement/ADR/Need/etc., so ``reactivate()`` (GH-443) restores the
        record with its links intact instead of silently losing them.

        Args:
            risk_id: UUID of the Risk to delete.
            ctx: Resolved AuthContext.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        risk = Risk.objects.filter(id=risk_id, tenant_id=ctx.tenant_id).first()
        if risk is None:
            raise NotFoundError(f"Risk {risk_id} not found")

        workspace_id = risk.workspace_id

        # REQ-006/Phase 0: route soft-delete through the workflow engine's
        # outdate() escape hatch instead of hard-deleting the row.
        from workflow.services import outdate

        outdate(
            item_id=risk.id,
            item_type="Risk",
            workspace_id=workspace_id,
            ctx=ctx,
            reason="deleted via risk.delete",
        )

        self._audit(ctx=ctx, operation="delete", entity_type="Risk", entity_id=risk_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.RISK_DELETED,
                entity_id=risk_id,
                workspace_id=workspace_id,
            )
        )

    def get_risk(self, risk_id: UUID, ctx: AuthContext) -> Risk:
        """Fetch a single Risk (tenant-scoped, REQ-L3-RISK-010).

        Args:
            risk_id: UUID of the Risk to retrieve.
            ctx: Resolved AuthContext.

        Returns:
            Risk ORM instance.
        """
        self._set_tenant_context(ctx)
        risk = Risk.objects.filter(id=risk_id, tenant_id=ctx.tenant_id).first()
        if risk is None:
            raise NotFoundError(f"Risk {risk_id} not found")
        return risk

    def list_risks(
        self, workspace_id: UUID, ctx: AuthContext, include_deleted: bool = False
    ) -> QuerySet[Risk]:
        """Return all Risks in *workspace_id* (tenant-scoped, REQ-L3-RISK-010).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.
            include_deleted: When False (default), excludes Risks soft-deleted
                via ``workflow.services.outdate()`` (REQ-006, Phase 0). ``Risk``
                is registered in
                ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``, so
                ``outdate()`` writes ``"outdated"`` into the mirrored
                ``status`` field.

        Returns:
            QuerySet of Risk ORM instances ordered by risk_score descending.

        REQ-088: Returns a lazy ``QuerySet`` so the paginating ViewSet
        (REQ-034) slices with LIMIT/OFFSET instead of materialising all rows.
        """
        self._set_tenant_context(ctx)
        qs = Risk.objects.filter(workspace_id=workspace_id, tenant_id=ctx.tenant_id)
        if not include_deleted:
            # Datenmodell-Konsolidierung Phase 1: soft-delete routes through
            # workflow.services.outdate(); the state is read from
            # WorkflowItemState now that Risk.status is no longer the seam.
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Risk", "outdated", tenant_id=ctx.tenant_id
                )
            )
        return qs.order_by("-risk_score")

    def list_risks_by_status(
        self, workspace_id: UUID, status: str, ctx: AuthContext
    ) -> List[Risk]:
        """Return Risks filtered by workflow *status* (REQ-L3-RISK-010).

        Args:
            workspace_id: Target workspace UUID.
            status: Workflow state name to match.
            ctx: Resolved AuthContext.

        Returns:
            Filtered list of Risk ORM instances ordered by risk_score descending.
        """
        self._set_tenant_context(ctx)
        return list(
            Risk.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                id__in=state_reader.item_ids_in_state(
                    "Risk", status, tenant_id=ctx.tenant_id
                ),
            ).order_by("-risk_score")
        )

    def query_risks_by_severity(
        self, workspace_id: UUID, severity: str, ctx: AuthContext
    ) -> List[Risk]:
        """Query risks filtered by severity label (for SeMetrics integration).

        This method is the SeMetrics contract: SeMetrics calls
        ``query_risks_by_severity(workspace_id, severity, ctx)`` to retrieve
        risks grouped by their derived severity (ADR-L3-RISK-03).

        Signature (stable contract for SeMetrics):
            query_risks_by_severity(
                workspace_id: UUID,
                severity: str,   # "low" | "medium" | "high"
                ctx: AuthContext,
            ) -> List[Risk]

        Args:
            workspace_id: Target workspace UUID.
            severity: One of {"low", "medium", "high"}.
            ctx: Resolved AuthContext.

        Returns:
            List of Risk ORM instances with the given severity, ordered by
            risk_score descending.
        """
        self._set_tenant_context(ctx)
        if severity not in Risk.Severity.values:
            raise ValidationError(
                f"Invalid severity '{severity}'; must be one of "
                f"{sorted(Risk.Severity.values)}"
            )
        return list(
            Risk.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                severity=severity,
            ).order_by("-risk_score")
        )

    def query_risks_by_score_range(
        self, workspace_id: UUID, min_score: int, max_score: int, ctx: AuthContext
    ) -> List[Risk]:
        """Query risks by risk_score range (REQ-L3-RISK-010, ADR-L3-RISK-03).

        Args:
            workspace_id: Target workspace UUID.
            min_score: Minimum risk score (inclusive).
            max_score: Maximum risk score (inclusive).
            ctx: Resolved AuthContext.

        Returns:
            Filtered and score-ordered list of Risk ORM instances.
        """
        self._set_tenant_context(ctx)
        return list(
            Risk.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                risk_score__gte=min_score,
                risk_score__lte=max_score,
            ).order_by("-risk_score")
        )

    # ---------- Status Transition (REQ-L3-RISK-005, IF-AS-INT-003) ----------

    @atomic_transaction
    def transition_status(
        self,
        risk_id: UUID,
        target_status: str,
        ctx: AuthContext,
        change_reason: Optional[str] = None,
        credential: Optional[str] = None,
    ) -> Risk:
        """Transition a Risk's workflow status (REQ-L3-RISK-005).

        Args:
            risk_id: UUID of the Risk.
            target_status: Target status from Risk.RiskStatus choices.
            ctx: Resolved AuthContext.
            change_reason: Optional reason for audit.

        Returns:
            Updated Risk ORM instance.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        risk = Risk.objects.filter(id=risk_id, tenant_id=ctx.tenant_id).first()
        if risk is None:
            raise NotFoundError(f"Risk {risk_id} not found")

        if target_status not in RiskValidator.VALID_STATUSES:
            raise ValidationError(
                f"Invalid Risk status '{target_status}'; "
                f"must be one of {sorted(RiskValidator.VALID_STATUSES)}"
            )

        # REQ-165/REQ-167: the WorkflowEngine is the SOLE authority for the
        # transition (IF-AS-INT-003). Role, change_reason and signature gates are
        # enforced by the engine; their errors propagate and abort this atomic
        # transaction instead of being swallowed (the previous bare
        # ``except Exception: pass`` silently flipped the status even when a gate
        # denied the move). A workflow transition is not a content edit, so
        # ``version`` is not bumped.
        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=risk_id,
            item_type="Risk",
            target_state=target_status,
            workspace_id=risk.workspace_id,
            ctx=ctx,
            change_reason=change_reason or "",
            credential=credential or "",
        )
        risk.refresh_from_db(fields=["version"])
        # Datenmodell-Konsolidierung Phase 1 (Task 12): the ``status`` column
        # is dropped, so it can no longer be refreshed or read as a fallback.
        # Set the in-memory (not persisted) ``.status`` from the engine so the
        # returned Risk instance still exposes the real current state, same
        # fallback convention as GoalService.transition_status. The engine
        # state is guaranteed to exist here (the transition above just
        # succeeded), so ``state_reader.initial_state`` never actually
        # triggers.
        risk.status = state_reader.current_state(
            "Risk", risk.id
        ) or state_reader.initial_state("Risk")

        # The transition audit entry is written authoritatively by the
        # WorkflowEngine (WorkflowFacade._audit, op="transition") inside the same
        # atomic transaction — a second service-level audit here would duplicate
        # that row (details are v1-ignored), so it is intentionally omitted.
        return risk

    # ---------- TraceLink management (REQ-L3-RISK-006, IF-AS-INT-002) ----------

    def create_tracelink(
        self,
        risk_id: UUID,
        target_id: UUID,
        link_type: str,
        ctx: AuthContext,
    ):
        """Create a TraceLink from a Risk to another artifact (REQ-L3-RISK-006).

        Args:
            risk_id: UUID of the source Risk.
            target_id: UUID of the target artifact.
            link_type: One of {"threatens", "mitigated-by", "related-to"}.
            ctx: Resolved AuthContext.

        Returns:
            Created TraceLink ORM instance.
        """
        self._set_tenant_context(ctx)
        if link_type not in RISK_LINK_TYPES:
            raise ValidationError(
                f"Invalid Risk link type '{link_type}'; "
                f"must be one of {sorted(RISK_LINK_TYPES)}"
            )

        risk = Risk.objects.filter(id=risk_id, tenant_id=ctx.tenant_id).first()
        if risk is None:
            raise NotFoundError(f"Risk {risk_id} not found")

        return self._trace_link_service.create_trace_link(
            source_id=risk_id,
            target_id=target_id,
            link_type=link_type,
            ctx=ctx,
        )


__all__ = [
    "RiskService",
    "RiskDTO",
    "RISK_LINK_TYPES",
]
