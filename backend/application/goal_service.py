"""
GoalService — Goal CRUD with lineage-based versioning (Variante A).

leaf_id : (Task 4 of feat/ziele-hauptziel-design)
req_id  : REQ-L2-TE-020

Every edit of a Goal creates a brand-new ``Goal`` row (and a brand-new
dedicated ``Artifact`` row) instead of mutating the existing one in place.
All versions of the same logical goal share a ``lineage_id``; the
``sequence_number`` is a per-lineage monotonic counter starting at 1.

Mirrors RiskService.create_risk's Artifact + workflow-init + audit + event
pattern (backend/application/risk_service.py), adapted for lineage-based
versioning instead of in-place update.

Feature gate: the whole Goal feature is gated by ``Workspace.goals_enabled``
(default False, added in Task 2 / commit f419a23). ``create_version`` raises
``ValidationError`` when the flag is off. AI-specific generation is gated
separately by ``Workspace.goals_ai_enabled`` — out of scope here, enforced by
whichever AI-derivation service consumes GoalService in a later task.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from persistence.transactions import atomic_transaction

from application.base import NotFoundError, ServiceBase, ValidationError
from application.models import Goal
from persistence.models import Artifact, Tenant, Workspace

logger = logging.getLogger(__name__)


class GoalService(ServiceBase):
    """Goal CRUD with lineage-based, immutable-row-per-version storage.

    leaf_id : (Task 4 of feat/ziele-hauptziel-design)
    req_id  : REQ-L2-TE-020
    """

    @atomic_transaction
    def create_version(
        self,
        *,
        workspace_id: uuid.UUID,
        title: str,
        description: str = "",
        lineage_id: Optional[uuid.UUID] = None,
        ctx: Any,
    ) -> dict:
        """Create a new Goal version, starting or continuing a lineage.

        Args:
            workspace_id: Target workspace UUID.
            title: Goal title.
            description: Optional goal description.
            lineage_id: When ``None``, starts a brand-new lineage (sequence
                1). When given, appends the next version to that lineage.
            ctx: Resolved AuthContext.

        Returns:
            dict with the persisted Goal's id, lineage_id, sequence_number,
            title, description and status.

        Raises:
            ValidationError: ``Workspace.goals_enabled`` is False, or
                ``title`` is empty.
            NotFoundError: Tenant or Workspace not found.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if not title:
            raise ValidationError("Goal title is required")

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        # Feature gate (Global Constraint, Task 2/f419a23): the entire Goal
        # feature is off by default and must be explicitly enabled per
        # workspace. Checked here (the sole write path) rather than in every
        # read method, mirroring the absence of any comparable feature-toggle
        # gate on RiskService's read methods (list_risks/get_risk are
        # ungated; only the mutating create/update/delete paths enforce
        # preconditions such as role and validation).
        if not workspace.goals_enabled:
            raise ValidationError(
                f"Goals are not enabled for workspace {workspace_id}"
            )

        if lineage_id is None:
            resolved_lineage_id = uuid.uuid4()
            sequence_number = 1
        else:
            resolved_lineage_id = lineage_id
            last = (
                Goal.objects.filter(
                    workspace_id=workspace.id, lineage_id=resolved_lineage_id
                )
                .order_by("-sequence_number")
                .first()
            )
            sequence_number = (last.sequence_number + 1) if last else 1

        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Goal"
        )
        goal = Goal(
            artifact=artifact,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            lineage_id=resolved_lineage_id,
            sequence_number=sequence_number,
            title=title,
            description=description,
            status="Entwurf",
            created_by=str(ctx.user_id),
        )
        goal.save()

        # Initialize workflow state (best-effort, mirrors RiskService).
        # Absent a provisioned WorkflowEngineDefinition for this
        # workspace/item_type (only backfilled for pre-existing workspaces
        # via migration 0012), this is a silent no-op — the explicit
        # status="Entwurf" set above is authoritative for new Goals
        # regardless of workflow-init outcome.
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[goal.id],
                item_type="Goal",
                workspace_id=workspace.id,
                ctx=ctx,
            )
        except Exception:
            logger.debug("GoalService: workflow init skipped for goal=%s", goal.id)

        self._audit(
            ctx=ctx, operation="create", entity_type="Goal", entity_id=goal.id
        )
        self._emit_event(
            self._make_event(
                event_type="GoalCreated",
                entity_id=goal.id,
                workspace_id=workspace.id,
                payload={
                    "title": title,
                    "lineage_id": str(resolved_lineage_id),
                    "sequence_number": sequence_number,
                },
            )
        )

        return {
            "id": str(goal.id),
            "lineage_id": str(goal.lineage_id),
            "sequence_number": goal.sequence_number,
            "title": goal.title,
            "description": goal.description,
            "status": goal.status,
        }

    def get(self, goal_id: uuid.UUID, ctx: Any) -> Goal:
        """Fetch a single Goal version (tenant-scoped).

        Args:
            goal_id: UUID of the Goal row to retrieve.
            ctx: Resolved AuthContext.

        Returns:
            Goal ORM instance.

        Raises:
            NotFoundError: No such Goal in the active tenant.
        """
        self._set_tenant_context(ctx)
        goal = Goal.objects.filter(id=goal_id, tenant_id=ctx.tenant_id).first()
        if goal is None:
            raise NotFoundError(f"Goal {goal_id} not found")
        return goal

    def list_versions(self, lineage_id: uuid.UUID, ctx: Any) -> list[dict]:
        """Return all versions of a Goal lineage, oldest first.

        Args:
            lineage_id: The lineage UUID shared by all versions.
            ctx: Resolved AuthContext.

        Returns:
            List of dicts, one per version, ordered by sequence_number.
        """
        self._set_tenant_context(ctx)
        qs = Goal.objects.filter(
            lineage_id=lineage_id, tenant_id=ctx.tenant_id
        ).order_by("sequence_number")
        return [
            {
                "id": str(g.id),
                "version": g.sequence_number,
                "sequence_number": g.sequence_number,
                "label": f"v{g.sequence_number}",
                "title": g.title,
                "status": g.status,
                "modified_at": g.created_at.isoformat() if g.created_at else None,
                # Immutable per-version rows — content always retrievable (#213).
                "content_available": True,
            }
            for g in qs
        ]

    def list_current(self, workspace_id: uuid.UUID, ctx: Any) -> list[Goal]:
        """Return the latest, non-archived version of every lineage.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Returns:
            List of Goal ORM instances, one per lineage (the highest
            sequence_number, excluding "Archiviert").
        """
        self._set_tenant_context(ctx)
        latest_ids = (
            Goal.objects.filter(workspace_id=workspace_id, tenant_id=ctx.tenant_id)
            .exclude(status="Archiviert")
            .order_by("lineage_id", "-sequence_number")
            .distinct("lineage_id")
            .values_list("id", flat=True)
        )
        return list(Goal.objects.filter(id__in=list(latest_ids)))

    def list_effective(self, workspace_id: uuid.UUID, ctx: Any) -> list[Goal]:
        """Return the *effective* (approved) version of every lineage.

        Design spec sections 2.3/3/4.2: only Goal versions in the
        ``Freigegeben`` workflow state count as the "gültige Version" of their
        lineage and are therefore the only ones allowed to flow into MainGoal
        aggregation. A newer ``Entwurf`` row supersedes nothing until it is
        itself approved, so per lineage the highest-``sequence_number``
        ``Freigegeben`` row wins. Lineages that have never been approved
        contribute nothing (not "the previous version", but "no effective
        version" — same rule ``MainGoalService.get_current`` applies).

        Deliberately kept separate from ``list_current`` rather than filtering
        that method: ``list_current`` powers the UI/REST list, which must keep
        showing drafts. ``status`` is the denormalized mirror the
        WorkflowEngine writes (StateLifecycleManager._sync_status_mirror), so
        it is authoritative for reads.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Returns:
            List of Goal ORM instances, at most one per lineage.
        """
        self._set_tenant_context(ctx)
        approved_ids = (
            Goal.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                status="Freigegeben",
            )
            .order_by("lineage_id", "-sequence_number")
            .distinct("lineage_id")
            .values_list("id", flat=True)
        )
        return list(Goal.objects.filter(id__in=list(approved_ids)))

    def transition_status(
        self,
        goal_id: uuid.UUID,
        target_status: str,
        ctx: Any,
        change_reason: Optional[str] = None,
        credential: Optional[str] = None,
    ) -> Goal:
        """Transition a Goal version's workflow state via the WorkflowEngine.

        Mirrors ``RiskService.transition_status``: the WorkflowEngine (through
        ``WorkflowFacade``, COMP-AS-007) is the sole authority — role,
        change_reason and signature gates are enforced there and their errors
        propagate. The engine also writes the denormalized ``status`` mirror,
        so no direct field assignment happens here. Target-state validation is
        left to the engine as well, because a workspace may override the
        ``goal_default`` preset's state set.

        Args:
            goal_id: UUID of the Goal version to transition.
            target_status: Target workflow state (e.g. ``"Freigegeben"``).
            ctx: Resolved AuthContext.
            change_reason: Reason recorded on the transition. The
                ``goal_default`` preset requires a non-empty reason for
                ``Entwurf`` -> ``Freigegeben``.
            credential: Password/TOTP token for signature-gated transitions.

        Returns:
            The refreshed Goal ORM instance.

        Raises:
            NotFoundError: No such Goal in the active tenant.
            ValidationError: Transition rejected by the WorkflowEngine.
            PermissionDeniedError: Preset-level role gate blocked the move.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        goal = Goal.objects.filter(id=goal_id, tenant_id=ctx.tenant_id).first()
        if goal is None:
            raise NotFoundError(f"Goal {goal_id} not found")

        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=goal.id,
            item_type="Goal",
            target_state=target_status,
            workspace_id=goal.workspace_id,
            ctx=ctx,
            change_reason=change_reason or "",
            credential=credential or "",
        )
        # The transition audit entry is written authoritatively by the
        # WorkflowEngine inside the same atomic transaction (mirrors
        # RiskService.transition_status) — no second service-level audit here.
        goal.refresh_from_db(fields=["status", "version"])
        return goal


__all__ = ["GoalService"]
