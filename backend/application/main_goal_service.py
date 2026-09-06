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

from django.db import IntegrityError, transaction

from persistence.transactions import atomic_transaction

from application.artifact_version_service import (
    ArtifactVersionService,
    lineage_anchor_artifact_id,
    snapshot_fields,
)
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.models import MainGoal
from persistence.models import Artifact, Tenant, Workspace
from workflow import state_reader

logger = logging.getLogger(__name__)

# SA-16: how often ``_insert_with_next_sequence`` re-reads the maximum
# sequence_number after losing the UNIQUE-constraint race. Each retry only
# loses to a *committed* concurrent insert, so N attempts tolerate N-1
# simultaneous creators; beyond that the write is a genuine fault, not
# contention worth spinning on.
_SEQUENCE_ALLOCATION_ATTEMPTS = 5

# SYSTEMAUDIT-2026-08-27 AP-6 L-3: name of the constraint the retry loop below
# is allowed to absorb. Any other IntegrityError (an unrelated FK violation,
# a NOT NULL violation, ...) must propagate immediately instead of being
# retried 5x for a collision that will never resolve itself.
_SEQUENCE_CONSTRAINT_NAME = "uq_main_goal_workspace_sequence"


def _is_sequence_number_collision(exc: IntegrityError) -> bool:
    """Return True only if *exc* was raised by the sequence-number UNIQUE constraint.

    Prefers psycopg2's structured diagnostics
    (``exc.__cause__.diag.constraint_name``), which is what a real Postgres
    driver populates and cannot be spoofed by unrelated error text. Falls
    back to matching the constraint name in ``str(exc)`` for callers/tests
    that raise a bare ``IntegrityError`` with no ``__cause__`` (e.g. sqlite,
    or a mocked driver in a unit test).
    """
    diag = getattr(exc.__cause__, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name is not None:
        return constraint_name == _SEQUENCE_CONSTRAINT_NAME
    return _SEQUENCE_CONSTRAINT_NAME in str(exc)


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

    def generate_ai(self, *, workspace_id: uuid.UUID, ctx: Any) -> dict:
        """Aggregate the workspace's current Goals into an AI-authored MainGoal.

        Loads the ``goal_aggregate`` prompt template (workspace override, else
        tenant-global, else factory default), renders it with the workspace's
        *approved* Goals (``GoalService.list_effective`` — the newest
        ``Freigegeben`` version of every lineage; drafts are excluded per
        design spec 3/4.2), and runs it through the configured LLM
        provider (``AiDerivationService._complete``, with caching, daily
        token-limit enforcement and mock-provider degradation baked in).

        Transaction scope (Systemaudit 2026-08-27 item 14): unlike every
        other write method on this service, this one is deliberately NOT
        decorated with ``@atomic_transaction``. The provider call below is a
        synchronous outbound HTTP request with its own retry/timeout budget
        (seconds, and up to the longer ``resolve_timeout_seconds`` cap),
        which under the decorator ran with a DB transaction — and therefore a
        pooled connection — held open for its full duration, for nothing: the
        LLM call performs no DB work that could need rolling back. Only the
        persistence step is wrapped in ``transaction.atomic()`` now, which
        keeps ``_create_row``'s sequence-number read and its inserts in one
        atomic unit exactly as before while cutting connection-hold time from
        "however long the provider takes" down to the write itself.

        This is safe for tenant isolation: RLS binds ``app.current_tenant``
        with a session-scoped ``SET`` (not ``SET LOCAL``) in
        ``persistence.middleware``, precisely because ``ATOMIC_REQUESTS`` is
        off — so the tenant binding spans transaction boundaries and the
        narrower block is still tenant-scoped. The trade-off is that the
        feature-gate and Goal reads above now happen outside the write's
        transaction; a workspace deleted in that window fails the insert on
        its foreign key and rolls the write back, which is the same net
        outcome the wider transaction produced.

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

        from application.ai_derivation_service import (
            MOCK_FALLBACK_MARKER,
            AiDerivationService,
        )

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
        # Runs OUTSIDE any transaction on purpose — see this method's
        # docstring (Systemaudit item 14): a multi-second outbound HTTP call
        # must not hold a DB connection/transaction open, and it has nothing
        # to roll back.
        content, _cache_key = ai_svc._complete(
            prompt,
            purpose="goal_aggregate",
            artifact_id=str(workspace_id),
            context={
                "workspace_id": str(workspace_id),
                "goal_titles": [g.title for g in goals],
            },
        )

        # UI-28 (Systemaudit 2026-08-27 AP-5): `_complete()` signals a
        # degraded/mock answer by prefixing the text with
        # `MOCK_FALLBACK_MARKER` (same contract `ai_review_service`,
        # `architecture_decompose_service` and `traceability_suggest_service`
        # already rely on) instead of a separate flag, because this is the
        # single-text `_complete()` path, not the JSON-list one that already
        # returns `is_mock_fallback` explicitly. Strip the marker before
        # persisting it as the MainGoal's actual content — a saved MainGoal
        # must never carry the debug marker in its stored text — and surface
        # the flag itself on the returned dict so the caller (the REST view)
        # can pass it through to the client without a DB migration; it is
        # deliberately NOT a persisted field, only a signal about how *this*
        # generation call was served.
        is_mock_fallback = content.startswith(MOCK_FALLBACK_MARKER)
        if is_mock_fallback:
            content = content[len(MOCK_FALLBACK_MARKER):].strip()

        # Only the persistence step is atomic (REQ-L3-PL003-001/002):
        # _create_row derives the next sequence_number from a read and then
        # writes an Artifact + MainGoal, so those must stay in one unit.
        with transaction.atomic():
            result = self._create_row(
                workspace=workspace,
                tenant=tenant,
                content=content,
                source="ai",
                generated_from_goal_ids=[str(g.id) for g in goals],
                ctx=ctx,
            )
        result["is_mock_fallback"] = is_mock_fallback
        return result

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

    def _insert_with_next_sequence(
        self,
        *,
        workspace: Workspace,
        tenant: Tenant,
        content: str,
        source: str,
        generated_from_goal_ids: list[str],
        ctx: Any,
    ) -> MainGoal:
        """Insert the Artifact + MainGoal pair under the next free sequence number.

        SA-16 (Systemaudit 2026-08-27): the number is derived from a
        ``MAX(sequence_number) + 1`` read, so two concurrent creates in the same
        workspace can read the same value. The authoritative guard is the
        ``uq_main_goal_workspace_sequence`` UNIQUE constraint on the table (see
        ``MainGoal.Meta``) — a lock cannot serialise the first-ever insert,
        because there is no row yet to lock. The loser of the race therefore
        hits an IntegrityError; this loop absorbs it by re-reading the maximum
        and retrying, so a concurrent create yields v1/v2 instead of a 500.
        Only an ``IntegrityError`` matched to THIS constraint by
        ``_is_sequence_number_collision`` is absorbed (AP-6 L-3) — any other
        IntegrityError (e.g. an unrelated FK violation) propagates immediately.

        The whole read/insert unit runs inside a nested ``atomic`` block, i.e. a
        savepoint: an IntegrityError marks the surrounding transaction as
        needing rollback, and only the savepoint release/rollback lets the outer
        transaction (opened by the callers, which must keep the audit entry and
        the domain event in the same unit) survive the retry.

        Args:
            workspace: Target workspace (already resolved and gated).
            tenant: Owning tenant.
            content: MainGoal body text.
            source: ``"manual"`` or ``"ai"``.
            generated_from_goal_ids: Source Goal ids for the AI path.
            ctx: Request context (used for ``created_by``).

        Returns:
            The persisted MainGoal with its allocated ``sequence_number``.

        Raises:
            IntegrityError: If every attempt lost the race — treated as a real
                fault rather than retried forever.
        """
        last_error: IntegrityError | None = None
        for _ in range(_SEQUENCE_ALLOCATION_ATTEMPTS):
            last = (
                MainGoal.objects.filter(workspace_id=workspace.id)
                .order_by("-sequence_number")
                .first()
            )
            sequence_number = (last.sequence_number + 1) if last else 1
            try:
                with transaction.atomic():
                    artifact = Artifact.objects.create(
                        tenant=tenant, workspace=workspace, artifact_type="MainGoal"
                    )
                    # Datenmodell-Konsolidierung: `status` is no longer written
                    # explicitly — WorkflowItemState.current_state (seeded
                    # below from the workflow definition's initial_state) is
                    # the authority; the model field's own default ("Entwurf")
                    # keeps the column non-null until it is dropped (Task 12).
                    main_goal = MainGoal(
                        artifact=artifact,
                        tenant_id=tenant.id,
                        workspace_id=workspace.id,
                        sequence_number=sequence_number,
                        content=content,
                        source=source,
                        generated_from_goal_ids=generated_from_goal_ids,
                        created_by_name=str(ctx.user_id),
                    )
                    main_goal.save()
                return main_goal
            except IntegrityError as exc:
                if not _is_sequence_number_collision(exc):
                    # SYSTEMAUDIT-2026-08-27 AP-6 L-3: not our race — a
                    # different constraint violation must not be silently
                    # retried and re-raised as a misleading "lost the race".
                    raise
                last_error = exc
                logger.info(
                    "MainGoalService: sequence_number=%s already taken for "
                    "workspace=%s, retrying with a freshly read maximum",
                    sequence_number,
                    workspace.id,
                )

        assert last_error is not None  # loop body either returns or sets it
        raise last_error

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
        main_goal = self._insert_with_next_sequence(
            workspace=workspace,
            tenant=tenant,
            content=content,
            source=source,
            generated_from_goal_ids=generated_from_goal_ids,
            ctx=ctx,
        )
        sequence_number = main_goal.sequence_number

        # Datenmodell-Konsolidierung Phase 5 (spec §6.1): anchor the lineage's
        # revisions on the sequence-1 Artifact so `list_revisions(anchor)`
        # returns the whole lineage. Recording against main_goal.artifact_id
        # would store one revision per Artifact (a new one is created for every
        # version), which is storage without history. MainGoal has no
        # lineage_id column — its lineage is the workspace, whose
        # (workspace_id, sequence_number) pair is unique by DB constraint.
        # Recorded here rather than inside _insert_with_next_sequence, whose
        # nested atomic block is rolled back and retried on a sequence
        # collision.
        anchor_artifact_id = (
            main_goal.artifact_id
            if sequence_number == 1
            else lineage_anchor_artifact_id(MainGoal, workspace_id=workspace.id)
        )
        if anchor_artifact_id is not None:
            ArtifactVersionService().record(
                anchor_artifact_id,
                snapshot_fields(main_goal, "MainGoal"),
                ctx,
                revision=sequence_number,
            )

        # Initialize workflow state (best-effort, mirrors GoalService/
        # RiskService). Absent a provisioned WorkflowEngineDefinition for this
        # workspace/item_type, this is a silent no-op — the MainGoal has no
        # WorkflowItemState row and the still-present `status` column (via
        # the model default above) is the fallback the dict below reads.
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[main_goal.id],
                item_type="MainGoal",
                workspace_id=workspace.id,
                ctx=ctx,
            )
        except Exception:
            # WARNING (not DEBUG, unlike the sibling Adr/Risk/Issue services):
            # MainGoal has no WorkflowItemState backfill, so a row stranded
            # here can never self-heal (transition() requires an existing
            # row) and would silently drop out of get_current.
            logger.warning(
                "MainGoalService: workflow init skipped for main_goal=%s",
                main_goal.id,
                exc_info=True,
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
            # Datenmodell-Konsolidierung Phase 1 (Task 12): the `status`
            # column is dropped, so a MainGoal with no WorkflowItemState row
            # yet reports the main_goal_default preset's initial state
            # instead (documented, reviewed data-loss tradeoff, see Task 12
            # report Finding 2). The MCP main_goal.create_manual tool returns
            # this dict straight to the wire without a serializer fallback in
            # between.
            "status": state_reader.current_state("MainGoal", main_goal.id)
            or state_reader.initial_state("MainGoal"),
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
        main_goal.refresh_from_db(fields=["version"])

        # The transition audit entry is written authoritatively by the
        # WorkflowEngine (WorkflowFacade._audit, op="transition") inside the
        # same atomic transaction — a second service-level audit here would
        # duplicate that row, so it is intentionally omitted (mirrors
        # RiskService.transition_status).
        return {
            "id": str(main_goal.id),
            "sequence_number": main_goal.sequence_number,
            # Datenmodell-Konsolidierung Phase 1 (Task 12): ``status`` is
            # dropped — resolve the real current state via the engine, same
            # fallback convention as the read-side DTO builder above. The
            # engine state is guaranteed to exist here (the transition above
            # just succeeded), so ``state_reader.initial_state`` never
            # actually triggers.
            "status": state_reader.current_state("MainGoal", main_goal.id)
            or state_reader.initial_state("MainGoal"),
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
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                id__in=state_reader.item_ids_in_state(
                    "MainGoal", "Freigegeben", tenant_id=ctx.tenant_id
                ),
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
        qs = list(
            MainGoal.objects.filter(
                workspace_id=workspace_id, tenant_id=ctx.tenant_id
            ).order_by("sequence_number")
        )
        # Batch-resolve status for all versions in one query instead of one
        # engine lookup per version (N+1 avoidance). Falls back to the
        # main_goal_default preset's initial state (not the dropped `status`
        # column, Task 12) for any version with no WorkflowItemState row.
        status_map = state_reader.current_states("MainGoal", [mg.id for mg in qs])
        main_goal_initial_state = state_reader.initial_state("MainGoal")
        return [
            {
                "id": str(mg.id),
                "version": mg.sequence_number,
                "sequence_number": mg.sequence_number,
                "label": f"v{mg.sequence_number}",
                "content": mg.content,
                "source": mg.source,
                "status": status_map.get(str(mg.id)) or main_goal_initial_state,
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
