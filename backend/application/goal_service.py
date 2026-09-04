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
``PermissionDeniedError`` when the flag is off (#271 item 4 — this is an
authorization concern, not input validation). AI-specific generation is gated
separately by ``Workspace.goals_ai_enabled`` — out of scope here, enforced by
whichever AI-derivation service consumes GoalService in a later task.
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
from application.models import Goal
from persistence.models import Artifact, Tenant, Workspace
from workflow import state_reader

logger = logging.getLogger(__name__)

# Fallbacks for the ``goal_default`` preset's states (workflow/definition_store.py).
# Only used when a workspace has no Goal workflow document at all — every code
# path that can resolve the workspace's actual definition prefers that, so a
# customised state machine (ADR-06) keeps working.
DRAFT_STATE = "Entwurf"
APPROVED_STATE = "Freigegeben"
ARCHIVED_STATE = "Archiviert"


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
            PermissionDeniedError: ``Workspace.goals_enabled`` is False.
            ValidationError: ``title`` is empty.
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
            # Feature-gate/authorization concern, not input validation (#271
            # item 4): the caller is not permitted to use this feature for
            # this workspace, regardless of how well-formed the request is.
            raise PermissionDeniedError(
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
            if last is None:
                # Issue #270 finding 4: an unknown lineage_id used to silently
                # start a *second* lineage at sequence 1 under the caller's
                # UUID. Clients that mistakenly pass a Goal *version* id then
                # get a response whose lineage_id equals that version id and
                # believe the lineage changed. Fail loudly instead, and name
                # the real lineage when the UUID is recognisably a Goal id.
                raise NotFoundError(self._unknown_lineage_message(workspace.id, lineage_id))
            sequence_number = last.sequence_number + 1

        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Goal"
        )
        # Datenmodell-Konsolidierung: `status` is no longer written explicitly —
        # WorkflowItemState.current_state (seeded below from the workflow
        # definition's initial_state) is the authority; the model field's own
        # default ("Entwurf") keeps the column non-null until it is dropped
        # (Task 12).
        goal = Goal(
            artifact=artifact,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            lineage_id=resolved_lineage_id,
            sequence_number=sequence_number,
            title=title,
            description=description,
            created_by=str(ctx.user_id),
        )
        goal.save()

        # Initialize workflow state (best-effort, mirrors RiskService).
        # Absent a provisioned WorkflowEngineDefinition for this
        # workspace/item_type (only backfilled for pre-existing workspaces
        # via migration 0012), this is a silent no-op — the Goal has no
        # WorkflowItemState row and the still-present `status` column (via
        # the model default above) is the fallback the dict below reads.
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[goal.id],
                item_type="Goal",
                workspace_id=workspace.id,
                ctx=ctx,
            )
        except Exception:
            # WARNING (not DEBUG, unlike the sibling Adr/Risk/Issue services):
            # Goal has no WorkflowItemState backfill, so a row stranded here
            # can never self-heal (transition() requires an existing row) and
            # would silently drop out of list_current's archive exclusion,
            # list_effective and MainGoalService.get_current.
            logger.warning(
                "GoalService: workflow init skipped for goal=%s", goal.id, exc_info=True
            )

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
            # Artifact backing PK (Variante A: one dedicated Artifact per Goal
            # version). Exposed so callers that need the Artifact row -- e.g.
            # InterviewSessionArtifact provenance / TraceLink endpoints --
            # never have to re-derive it from the Goal row id.
            "artifact_id": str(goal.artifact_id),
            "lineage_id": str(goal.lineage_id),
            "sequence_number": goal.sequence_number,
            "title": goal.title,
            "description": goal.description,
            # Falls back to the still-present `status` column (model default,
            # see above) when the engine has no WorkflowItemState row yet —
            # e.g. workflow-init above was a silent no-op. Goal has no
            # item-state backfill, so this is not a hypothetical case; several
            # MCP tools (goal.create/goal.create_version) return this dict
            # straight to the wire without a serializer fallback in between.
            "status": state_reader.current_state("Goal", goal.id) or goal.status,
        }

    @staticmethod
    def _unknown_lineage_message(
        workspace_id: uuid.UUID, lineage_id: uuid.UUID
    ) -> str:
        """Build the NotFoundError message for an unknown ``lineage_id``.

        Adds a hint when the supplied UUID is in fact a Goal *version* id —
        the mix-up issue #270 finding 4 reported.
        """
        message = f"Goal lineage {lineage_id} not found in workspace {workspace_id}"
        stray = Goal.objects.filter(id=lineage_id, workspace_id=workspace_id).first()
        if stray is not None:
            message += (
                f" — {lineage_id} is the id of Goal version v"
                f"{stray.sequence_number}; its lineage_id is {stray.lineage_id}"
            )
        return message

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

    def list_current(
        self, workspace_id: uuid.UUID, ctx: Any, *, include_archived: bool = False
    ) -> list[Goal]:
        """Return the latest version of every lineage in a workspace.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext.
            include_archived: When False (default), lineages whose newest
                version is "Archiviert" are omitted (UI/REST default listing
                behaviour, unchanged). When True, the latest version of every
                lineage is returned regardless of status — the basis for the
                MCP ``goal.query`` tool's ``include_archived`` param
                (issue #216), which mirrors ``{prefix}.query``'s
                ``include_outdated`` flag in ``mcp_server/tools/generic.py``.

        Returns:
            List of Goal ORM instances, one per lineage (the highest
            sequence_number).
        """
        self._set_tenant_context(ctx)
        qs = Goal.objects.filter(workspace_id=workspace_id, tenant_id=ctx.tenant_id)
        if not include_archived:
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Goal", ARCHIVED_STATE, tenant_id=ctx.tenant_id
                )
            )
        latest_ids = (
            qs.order_by("lineage_id", "-sequence_number")
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
        showing drafts. The workflow engine (``WorkflowItemState.current_state``
        via ``state_reader``) is the authority for reads.

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
                id__in=state_reader.item_ids_in_state(
                    "Goal", APPROVED_STATE, tenant_id=ctx.tenant_id
                ),
            )
            .order_by("lineage_id", "-sequence_number")
            .distinct("lineage_id")
            .values_list("id", flat=True)
        )
        return list(Goal.objects.filter(id__in=list(approved_ids)))

    def update(
        self,
        goal_id: uuid.UUID,
        ctx: Any,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Update a Goal by appending a new version to its lineage.

        Goals are immutable-row-per-version (see module docstring), so there is
        no in-place update: this reads the addressed version, merges the given
        fields over it and delegates to :meth:`create_version` with the same
        ``lineage_id``. The result is a fresh version at ``Entwurf`` — the
        previous version keeps its own status and stays readable, which is what
        makes the lineage an audit trail.

        Omitted fields are carried over unchanged, so a caller may send only
        the field it wants to change (PATCH semantics).

        Args:
            goal_id: UUID of the Goal *version* to base the new version on
                (any version of the lineage; the new version is always
                appended after the lineage's newest one).
            ctx: Resolved AuthContext.
            title: New title, or ``None`` to keep the current one.
            description: New description, or ``None`` to keep the current one.

        Returns:
            dict describing the newly created Goal version (same shape as
            :meth:`create_version`).

        Raises:
            NotFoundError: No such Goal in the active tenant.
            ValidationError: ``Workspace.goals_enabled`` is False, or the
                resulting title would be empty.
            PermissionDeniedError: Caller lacks write permission.
        """
        goal = self.get(goal_id, ctx)
        return self.create_version(
            workspace_id=goal.workspace_id,
            title=goal.title if title is None else title,
            description=goal.description if description is None else description,
            lineage_id=goal.lineage_id,
            ctx=ctx,
        )

    def get_available_transitions(
        self, goal_id: uuid.UUID, ctx: Any
    ) -> tuple[Optional[str], list[str]]:
        """Return ``(current_state, allowed target states)`` for a Goal version.

        Read-only, and the single seam both the REST ``transitions/`` endpoint
        and the MCP error paths use to answer "what may this Goal do next?" —
        it delegates to ``WorkflowFacade.get_available_transitions`` rather than
        re-deriving the state machine, so a workspace that customised its Goal
        workflow (ADR-06) is reflected automatically.

        Never raises for "no workflow configured": that degrades to an empty
        target list, matching ``workflow.services.get_available_transitions``.

        Args:
            goal_id: UUID of the Goal version.
            ctx: Resolved AuthContext.

        Returns:
            Tuple of the current state (``None`` when no workflow state exists)
            and the list of states reachable from it.

        Raises:
            NotFoundError: No such Goal in the active tenant.
        """
        goal = self.get(goal_id, ctx)

        from application.workflow_facade import WorkflowFacade

        available = WorkflowFacade().get_available_transitions(
            goal.id, ctx, item_type="Goal", workspace_id=goal.workspace_id
        )
        return available.current_state, [t.to_state for t in available.transitions]

    def _resolve_archive_state(self, goal: Goal) -> str:
        """Return the workflow state that means "archived" for this workspace.

        The ``goal_default`` preset flags ``Archiviert`` with
        ``is_outdated_equivalent`` (workflow/definition_store.py). Resolving the
        flag instead of hardcoding the German label keeps archiving working for
        a workspace whose Goal workflow was renamed or customised (ADR-06), and
        falls back to ``"Archiviert"`` when the workspace has no workflow
        document at all (then the transition itself decides).
        """
        from workflow.definition_store import get_state_meta
        from workflow.services import get_workflow_json

        workflow_json = get_workflow_json(goal.workspace_id, "Goal")
        for state in workflow_json.get("states", []) or []:
            if get_state_meta(workflow_json, state).get("is_outdated_equivalent"):
                return str(state)
        return ARCHIVED_STATE

    def _resolve_initial_state(self, goal: Goal, ctx: Any) -> str:
        """Return the Goal workflow's initial state for this workspace."""
        from application.workflow_facade import WorkflowFacade

        definition = WorkflowFacade().get_definition(
            ctx, item_type="Goal", workspace_id=goal.workspace_id
        )
        if definition is None:
            return DRAFT_STATE
        return definition.initial_state

    def archive(
        self,
        goal_id: uuid.UUID,
        ctx: Any,
        change_reason: Optional[str] = None,
    ) -> Goal:
        """Archive (soft-delete) a Goal version via the WorkflowEngine.

        Immutable lineage rows must never be hard-deleted — that would tear a
        hole in the version history and in MainGoal aggregation. Archiving is
        therefore an ordinary, fully gated workflow transition into the state
        flagged ``is_outdated_equivalent`` (``Archiviert`` by default), i.e. the
        exact same path :meth:`transition_status` takes. It is reversible via
        :meth:`restore`.

        Args:
            goal_id: UUID of the Goal version to archive.
            ctx: Resolved AuthContext.
            change_reason: Optional audit reason recorded on the transition.

        Returns:
            The refreshed Goal ORM instance.

        Raises:
            NotFoundError: No such Goal in the active tenant.
            ValidationError: The workspace's Goal workflow has no transition
                from the version's current state into the archived state.
            PermissionDeniedError: Preset-level role gate blocked the move.
        """
        goal = self.get(goal_id, ctx)
        return self.transition_status(
            goal.id,
            self._resolve_archive_state(goal),
            ctx,
            change_reason=change_reason,
        )

    def restore(
        self,
        goal_id: uuid.UUID,
        ctx: Any,
        change_reason: Optional[str] = None,
    ) -> Goal:
        """Restore an archived Goal version to the workflow's initial state.

        Deliberately restores to ``initial_state`` (``Entwurf`` by default)
        rather than to whatever state the version held before it was archived:
        only ``Freigegeben`` versions are the *effective* version of their
        lineage and may feed MainGoal aggregation (see :meth:`list_effective`),
        so silently handing an un-archived Goal its old approval back would let
        content re-enter the aggregation without anyone approving it. A restored
        Goal is a draft and must be approved again.

        Uses the same gated :meth:`transition_status` path as every other Goal
        state change — not the ``workflow.services.outdate``/``reactivate``
        escape hatch, whose forced ``"outdated"`` state is foreign to the Goal
        state machine and would be mirrored into ``Goal.status``, making the
        row invisible to the ``Archiviert`` filters in :meth:`list_current`.

        Args:
            goal_id: UUID of the archived Goal version.
            ctx: Resolved AuthContext.
            change_reason: Reason recorded on the transition. Defaults to
                ``"reactivated"`` because the default ``Archiviert -> Entwurf``
                transition requires a non-empty reason.

        Returns:
            The refreshed Goal ORM instance.

        Raises:
            NotFoundError: No such Goal in the active tenant.
            ValidationError: The version is not in a state from which the
                workflow allows a move back to the initial state.
            PermissionDeniedError: Preset-level role gate blocked the move.
        """
        goal = self.get(goal_id, ctx)
        return self.transition_status(
            goal.id,
            self._resolve_initial_state(goal, ctx),
            ctx,
            change_reason=change_reason or "reactivated",
        )

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


__all__ = [
    "APPROVED_STATE",
    "ARCHIVED_STATE",
    "DRAFT_STATE",
    "GoalService",
]
