"""MainGoalService — LLM-aggregated Haupt-Ziel, immutable-row-per-version.

leaf_id : (Task 5 of feat/ziele-hauptziel-design)
req_id  : REQ-L2-TE-020

Mirrors GoalService's Artifact + workflow-init + audit + event pattern
(backend/application/goal_service.py), adapted for a single workspace-scoped
version chain instead of per-lineage versioning: every MainGoal row shares
the same workspace and is ordered purely by ``sequence_number``. The valid
MainGoal for a workspace is always the newest row in ``Freigegeben`` state
(``get_current`` — "newest Freigegeben row wins"), never mutated in place.

``generate_ai`` mirrors AiDerivationService's template-loading/_render/
_complete pattern (backend/application/ai_derivation_service.py) to
aggregate the workspace's current Goals (via ``GoalService.list_current``)
into a single LLM-authored MainGoal draft.

``approve`` MUST go through the generic WorkflowEngine (IF-WE-EXT-IN-001) —
no bespoke state machine. It mirrors RiskService.transition_status, which
delegates to ``application.workflow_facade.WorkflowFacade.transition``
(COMP-AS-007) rather than calling ``workflow.services.transition`` directly,
so the preset-level role gate (PresetPolicyService.validate_transition_roles),
the change_reason precondition, the engine-authoritative audit entry
(operation="transition") and the WorkflowTransitioned domain event all fire
identically to every other entity type's transitions.

Feature gate: the whole MainGoal feature is gated by
``Workspace.goals_enabled`` (default False) — both ``create_manual`` and
``generate_ai`` raise ``PermissionDeniedError`` when the flag is off, mirroring
``GoalService.create_version``'s exact gate pattern (#271 item 4). AI generation is gated
additionally (not instead) by ``Workspace.goals_ai_enabled``. Read/transition
methods (``approve``, ``get_current``, ``list_versions``) are ungated,
mirroring GoalService's decision to gate only the write-creation paths.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from persistence.transactions import atomic_transaction

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.models import MainGoal
from persistence.models import Artifact, Tenant, Workspace

logger = logging.getLogger(__name__)


class MainGoalService(ServiceBase):
    """MainGoal CRUD-ish service: manual create, AI aggregation, approval.

    leaf_id : (Task 5 of feat/ziele-hauptziel-design)
    req_id  : REQ-L2-TE-020
    """

    # ---------- Creation ----------

    @atomic_transaction
    def create_manual(
        self, *, workspace_id: uuid.UUID, content: str, ctx: Any
    ) -> dict:
        """Create a new, manually-authored MainGoal version.

        Args:
            workspace_id: Target workspace UUID.
            content: The MainGoal's free-text content.
            ctx: Resolved AuthContext.

        Returns:
            dict with the persisted MainGoal's id, sequence_number, content,
            source and status.

        Raises:
            PermissionDeniedError: ``Workspace.goals_enabled`` is False.
            ValidationError: ``content`` is empty.
            NotFoundError: Tenant or Workspace not found.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if not content:
            raise ValidationError("MainGoal content is required")

        tenant, workspace = self._resolve_tenant_and_workspace(workspace_id, ctx)

        # Feature gate (Global Constraint): the entire Goal/MainGoal feature is
        # off by default and must be explicitly enabled per workspace. Mirrors
        # GoalService.create_version's gate — checked here (the sole manual
        # write path) rather than on any read method.
        if not workspace.goals_enabled:
            # Feature-gate/authorization concern, not input validation (#271
            # item 4): the caller is not permitted to use this feature for
            # this workspace, regardless of how well-formed the request is.
            raise PermissionDeniedError(
                f"Goals are not enabled for workspace {workspace_id}"
            )

        return self._create_row(
            workspace=workspace,
            tenant=tenant,
            content=content,
            source="manual",
            generated_from_goal_ids=[],
            ctx=ctx,
        )

    @atomic_transaction
    def generate_ai(self, *, workspace_id: uuid.UUID, ctx: Any) -> dict:
        """Aggregate the workspace's current Goals into an AI-authored MainGoal.

        Loads the ``goal_aggregate`` prompt template (workspace override, else
        tenant-global, else factory default), renders it with the workspace's
        *approved* Goals (``GoalService.list_effective`` — the newest
        ``Freigegeben`` version of every lineage; drafts are excluded per
        design spec 3/4.2), and runs it through the configured LLM
        provider (``AiDerivationService._complete``, with caching, daily
        token-limit enforcement and mock-provider degradation baked in).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Returns:
            dict with the persisted MainGoal's id, sequence_number, content,
            source, status and the Goal ids it was generated from.

        Raises:
            PermissionDeniedError: ``Workspace.goals_enabled`` is False.
            ValidationError: ``Workspace.goals_ai_enabled`` is False, or no
                approved Goal exists yet.
            NotFoundError: Tenant or Workspace not found.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        tenant, workspace = self._resolve_tenant_and_workspace(workspace_id, ctx)

        if not workspace.goals_enabled:
            # Feature-gate/authorization concern, not input validation (#271
            # item 4): the caller is not permitted to use this feature for
            # this workspace, regardless of how well-formed the request is.
            raise PermissionDeniedError(
                f"Goals are not enabled for workspace {workspace_id}"
            )
        # Checked in addition to (not instead of) goals_enabled above: the
        # whole feature being on does not imply AI generation is allowed for
        # this workspace.
        if not workspace.goals_ai_enabled:
            raise ValidationError("AI generation is disabled for this workspace")

        from application.goal_service import GoalService

        # Design spec 3/4.2: ONLY Goal versions in the ``Freigegeben`` state
        # are valid aggregation input. ``list_current`` (latest non-archived
        # row per lineage, drafts included) powers the UI list and must NOT be
        # used here — an unapproved draft would otherwise silently steer the
        # MainGoal.
        goals = GoalService().list_effective(workspace_id, ctx)
        if not goals:
            raise ValidationError(
                "No approved (Freigegeben) Goals exist for this workspace to aggregate"
            )

        from application.ai_derivation_service import AiDerivationService

        ai_svc = AiDerivationService()
        goals_text = "\n".join(
            f"- {g.title}: {g.description}" if g.description else f"- {g.title}"
            for g in goals
        )
        template = ai_svc._get_template_content(ctx, "goal_aggregate", workspace_id)
        prompt = ai_svc._render(template, goals=goals_text)
        # AiDerivationService._complete() now returns a (text, cache_key)
        # tuple (fix #552) instead of stashing the cache key on
        # ``self._last_cache_key``; this flow has no eviction logic, so the
        # cache key is discarded here.
        content, _cache_key = ai_svc._complete(
            prompt,
            purpose="goal_aggregate",
            artifact_id=str(workspace_id),
            context={
                "workspace_id": str(workspace_id),
                "goal_titles": [g.title for g in goals],
            },
        )

        return self._create_row(
            workspace=workspace,
            tenant=tenant,
            content=content,
            source="ai",
            generated_from_goal_ids=[str(g.id) for g in goals],
            ctx=ctx,
        )

    def _resolve_tenant_and_workspace(
        self, workspace_id: uuid.UUID, ctx: Any
    ) -> tuple[Tenant, Workspace]:
        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        return tenant, workspace

    def _create_row(
        self,
        *,
        workspace: Workspace,
        tenant: Tenant,
        content: str,
        source: str,
        generated_from_goal_ids: list[str],
        ctx: Any,
    ) -> dict:
        last = (
            MainGoal.objects.filter(workspace_id=workspace.id)
            .order_by("-sequence_number")
            .first()
        )
        sequence_number = (last.sequence_number + 1) if last else 1

        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="MainGoal"
        )
        main_goal = MainGoal(
            artifact=artifact,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            sequence_number=sequence_number,
            content=content,
            source=source,
            generated_from_goal_ids=generated_from_goal_ids,
            status="Entwurf",
            created_by=str(ctx.user_id),
        )
        main_goal.save()

        # Initialize workflow state (best-effort, mirrors GoalService/
        # RiskService). Absent a provisioned WorkflowEngineDefinition for this
        # workspace/item_type, this is a silent no-op — the explicit
        # status="Entwurf" set above is authoritative for new MainGoals
        # regardless of workflow-init outcome.
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[main_goal.id],
                item_type="MainGoal",
                workspace_id=workspace.id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "MainGoalService: workflow init skipped for main_goal=%s",
                main_goal.id,
            )

        self._audit(
            ctx=ctx, operation="create", entity_type="MainGoal", entity_id=main_goal.id
        )
        self._emit_event(
            self._make_event(
                event_type="MainGoalCreated",
                entity_id=main_goal.id,
                workspace_id=workspace.id,
                payload={
                    "source": source,
                    "sequence_number": sequence_number,
                },
            )
        )

        return {
            "id": str(main_goal.id),
            "sequence_number": main_goal.sequence_number,
            "content": main_goal.content,
            "source": main_goal.source,
            "status": main_goal.status,
            "generated_from_goal_ids": list(main_goal.generated_from_goal_ids),
        }

    # ---------- Approval ----------

    @atomic_transaction
    def approve(
        self,
        main_goal_id: uuid.UUID,
        ctx: Any,
        *,
        change_reason: Optional[str] = None,
    ) -> dict:
        """Transition a MainGoal to ``Freigegeben`` via the generic WorkflowEngine.

        Delegates to ``WorkflowFacade.transition`` (COMP-AS-007) — the same
        entry point ``RiskService.transition_status`` uses — instead of a raw
        ``status`` field write, so the preset-level role gate, the
        engine's TransitionValidator (role/change_reason/signature checks),
        the authoritative audit entry and the ``WorkflowTransitioned`` domain
        event all run identically to every other entity type's transitions
        (IF-WE-EXT-IN-001).

        Args:
            main_goal_id: UUID of the MainGoal row to approve.
            ctx: Resolved AuthContext.
            change_reason: Optional reason recorded on the transition; the
                ``main_goal_default`` preset requires a non-empty reason for
                the ``Entwurf`` -> ``Freigegeben`` transition, so a reasonable
                default is supplied when the caller omits one.

        Returns:
            dict with the MainGoal's id, sequence_number and new status.

        Raises:
            NotFoundError: No such MainGoal in the active tenant.
            ValidationError: Transition rejected by the WorkflowEngine
                (invalid state, missing change_reason, role not permitted,
                ...). ``WorkflowFacade._remap_workflow_exc`` maps every
                ``WorkflowTransitionError`` to ``ValidationError`` — including
                role rejections — except the preset-level
                ``PresetPolicyService.validate_transition_roles`` gate
                (approval_workflows preset feature for "approved"/"accepted"
                target states), which still raises ``PermissionDeniedError``.
            PermissionDeniedError: Preset-level role gate blocked the
                transition (see above).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        main_goal = MainGoal.objects.filter(
            id=main_goal_id, tenant_id=ctx.tenant_id
        ).first()
        if main_goal is None:
            raise NotFoundError(f"MainGoal {main_goal_id} not found")

        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=main_goal.id,
            target_state="Freigegeben",
            change_reason=change_reason or "MainGoal approved by user",
            ctx=ctx,
            item_type="MainGoal",
            workspace_id=main_goal.workspace_id,
        )
        main_goal.refresh_from_db(fields=["status", "version"])

        # The transition audit entry is written authoritatively by the
        # WorkflowEngine (WorkflowFacade._audit, op="transition") inside the
        # same atomic transaction — a second service-level audit here would
        # duplicate that row, so it is intentionally omitted (mirrors
        # RiskService.transition_status).
        return {
            "id": str(main_goal.id),
            "sequence_number": main_goal.sequence_number,
            "status": main_goal.status,
        }

    # ---------- Read ----------

    def get(self, main_goal_id: uuid.UUID, ctx: Any) -> MainGoal:
        """Fetch a single MainGoal version (tenant-scoped).

        Added for the REST layer (Task 6, REQ-066): keeps ORM access for
        MainGoal out of ``rest_api/views.py`` (the ratchet in
        ``rest_api/tests/test_architecture.py`` caps ``views.py`` at 0
        tolerated direct-ORM lines), mirroring ``GoalService.get``.

        Args:
            main_goal_id: UUID of the MainGoal row to retrieve.
            ctx: Resolved AuthContext.

        Returns:
            MainGoal ORM instance.

        Raises:
            NotFoundError: No such MainGoal in the active tenant.
        """
        self._set_tenant_context(ctx)
        main_goal = MainGoal.objects.filter(
            id=main_goal_id, tenant_id=ctx.tenant_id
        ).first()
        if main_goal is None:
            raise NotFoundError(f"MainGoal {main_goal_id} not found")
        return main_goal

    def get_current(self, workspace_id: uuid.UUID, ctx: Any) -> Optional[MainGoal]:
        """Return the newest ``Freigegeben`` MainGoal row for the workspace.

        "Newest Freigegeben row wins": rows are never mutated or deleted, so
        the currently-valid MainGoal is always the highest-``sequence_number``
        row whose ``status`` is ``Freigegeben``.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Returns:
            The MainGoal ORM instance, or ``None`` if no version has ever
            been approved.
        """
        self._set_tenant_context(ctx)
        return (
            MainGoal.objects.filter(
                workspace_id=workspace_id, tenant_id=ctx.tenant_id, status="Freigegeben"
            )
            .order_by("-sequence_number")
            .first()
        )

    def list_versions(self, workspace_id: uuid.UUID, ctx: Any) -> list[dict]:
        """Return all MainGoal versions for a workspace, oldest first.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Returns:
            List of dicts, one per version, ordered by sequence_number.
        """
        self._set_tenant_context(ctx)
        qs = MainGoal.objects.filter(
            workspace_id=workspace_id, tenant_id=ctx.tenant_id
        ).order_by("sequence_number")
        return [
            {
                "id": str(mg.id),
                "version": mg.sequence_number,
                "sequence_number": mg.sequence_number,
                "label": f"v{mg.sequence_number}",
                "content": mg.content,
                "source": mg.source,
                "status": mg.status,
                "modified_at": mg.created_at.isoformat() if mg.created_at else None,
                # Immutable per-version rows — content always retrievable (#213).
                "content_available": True,
            }
            for mg in qs
        ]

    def list_all(self, workspace_id: uuid.UUID, ctx: Any) -> list[MainGoal]:
        """Return all MainGoal versions for a workspace, newest first.

        Added for the REST layer (Task 6 fix round 1, reviewer finding C1):
        powers ``GET /api/v1/main-goals/``, mirroring ``GoalService.list_current``
        in shape (keeps direct ORM access for MainGoal out of
        ``rest_api/views.py``, REQ-066 ratchet in
        ``rest_api/tests/test_architecture.py``).

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.

        Returns:
            List of MainGoal ORM instances ordered by descending
            sequence_number (newest version first).
        """
        self._set_tenant_context(ctx)
        return list(
            MainGoal.objects.filter(
                workspace_id=workspace_id, tenant_id=ctx.tenant_id
            ).order_by("-sequence_number")
        )


__all__ = ["MainGoalService"]
