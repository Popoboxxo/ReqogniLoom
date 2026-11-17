"""Interview housekeeping and provenance (R2S-010).

Owns the explicit cancel path, workspace-level listing with the lazy stale
sweep, engine-state batch resolution and the artifact -> session provenance
lookup. Single-entity reads stay side-effect free (AUD-2026-09-169).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import F
from django.utils import timezone

from application.base import NotFoundError
from application.models import DomainEventOutbox
from persistence.models import InterviewSession, InterviewSessionArtifact
from persistence.transactions import atomic_transaction
from workflow import state_reader

# Keep the original log category: operators filter on it, and the split must
# not change observable logging behaviour.
logger = logging.getLogger("application.interview_service")

# spec §9 "verwaiste Sessions": a session untouched this long lazily flips
# to abandoned the next time anything reads it. No scheduled job (YAGNI).
ABANDONED_TTL = timedelta(days=30)

class InterviewHousekeepingMixin:
    """Cancel/list/provenance; mixed into :class:`InterviewService`."""

    @staticmethod
    def _lazily_abandon_if_stale(session: InterviewSession, ctx) -> None:
        """spec §9: flip a stale in_progress session to abandoned.

        System-driven, TTL-based, not a user-permission-gated action -- uses
        ``StateLifecycleManager.force_transition`` (the system escape hatch)
        with ``allow_system=True`` rather than the role-validated
        ``transition()``, since this can fire on behalf of a viewer-level
        ``ctx`` with no editor role. Mutates *session* in place when it fires
        so callers that already hold the returned object see the up-to-date
        status without re-fetching.

        AUD-2026-09-169: this method is a WRITE and must never run on a
        single-entity read path. It is invoked only from ``list_sessions``'s
        explicit bulk housekeeping sweep, where a write is expected, and from
        the explicit ``abandon()`` write. ``_get_session`` no longer calls it,
        so ``GET /interviews/{id}/state/`` is side-effect free.

        Datenmodell-Konsolidierung Phase 1: the guard reads the engine state
        (falling back to the column only for a session that was never wired
        into a ``WorkflowItemState``) rather than the ``status`` column
        directly -- the column is no longer written by a transition, so a
        session already moved past "in_progress" (e.g. completed) would
        otherwise still read "in_progress" here forever and get wrongly
        force-abandoned by every future stale read.

        The TTL check runs first, before the engine query: the common case
        (a session read well within its TTL window) is decided by a cheap
        in-memory comparison instead of a per-call query, cheaper for the
        majority of ``list_sessions`` calls this now gates. (This does not
        bound ``list_sessions``'s own pre-filter, whose candidate set is
        broader than before Phase 1 for a different reason -- accepted
        trade-off, see that method's docstring.)
        """
        if timezone.now() - session.modified_at < ABANDONED_TTL:
            return
        # Task 12: called before _get_session's own correction runs, on a
        # freshly-fetched *session* whose (now-dropped) `status` column can
        # no longer be a fallback -- resolve via the engine, or the
        # interview_default preset's initial state for an untracked session.
        current_status = state_reader.current_state(
            "Interview", session.id
        ) or state_reader.initial_state("Interview")
        if current_status != InterviewSession.STATUS_IN_PROGRESS:
            return
        from workflow.lifecycle_manager import StateLifecycleManager, WorkflowStateError
        from workflow.models import WorkflowItemState

        try:
            StateLifecycleManager().force_transition(
                item_id=session.id,
                item_type="Interview",
                workspace_id=session.workspace_id,
                target_state=InterviewSession.STATUS_ABANDONED,
                change_reason=f"Inactive for {ABANDONED_TTL.days}+ days (auto-abandon)",
                actor=str(getattr(ctx, "user_id", "") or "system"),
                allow_system=True,
            )
            session.refresh_from_db()
            # Correct the in-memory value (not persisted) so the caller sees
            # "abandoned" straight away instead of a stale pre-transition
            # value. Guaranteed to resolve via the engine here (the
            # transition above just succeeded) -- the initial-state fallback
            # is defensive symmetry only, it never actually triggers.
            session.status = state_reader.current_state(
                "Interview", session.id
            ) or state_reader.initial_state("Interview")
        except (WorkflowItemState.DoesNotExist, WorkflowStateError):
            # Expected, narrow case: no WorkflowItemState row (a session that
            # predates this feature, or workflow init failed at creation).
            # AUD-2026-09-169: this used to be a bare ``except Exception`` that
            # swallowed every DB/validation error at DEBUG level and then bumped
            # ``version`` without any state change (breaking the optimistic-lock
            # contract while persisting nothing). No row exists, so there is
            # nothing to abandon here -- leave the session untouched rather than
            # reporting a state change that was never written.
            logger.warning(
                "InterviewService: auto-abandon skipped for session=%s -- no "
                "WorkflowItemState",
                session.id,
            )

    @atomic_transaction
    def abandon(self, ctx, session_id: UUID) -> dict[str, Any]:
        """User-initiated cancel (2026-08-20 UI-visibility fix).

        Before this, the only path to STATUS_ABANDONED was the 30-day lazy
        sweep (spec §9) -- a user closing/cancelling an in-progress
        interview (e.g. the Hermes plugin's ``cancelInterview()``/the web
        widget's "Cancel" button) had no way to actually mark the session
        abandoned server-side; it just silently stayed "in_progress"
        forever and kept showing up in in-progress lists. Distinct from
        formalize(): explicit user action, not a completion.

        Review finding M2: the ``in_progress`` check is now taken through
        ``_lock_in_progress_session`` like both formalize paths, i.e. under the
        session's row lock. It used to read ``session.status`` from an unlocked
        ``_get_session`` and never lock, so abandon() was not serialised against
        formalize(): T1 formalized (``in_progress -> completed``), T2 had already
        read ``in_progress`` and then — after T1's commit — validated and applied
        ``completed -> abandoned``, a declared edge of the interview workflow. A
        just-formalized interview was silently flipped to ``abandoned`` while
        its artifacts stayed.
        """
        session = self._lock_in_progress_session(
            self._get_session(ctx, session_id), action="abandon"
        )

        from workflow.services import transition as workflow_transition

        # CR-07: same "did it reach the engine?" tracking as the formalize
        # paths -- the broad except below is a deliberate legacy-session
        # fallback and stays, but it must not read as a clean success.
        transition_applied = True
        try:
            workflow_transition(
                item_id=session.id,
                target_state=InterviewSession.STATUS_ABANDONED,
                change_reason="Cancelled by user",
                ctx=ctx,
                item_type="Interview",
                workspace_id=session.workspace_id,
            )
            session.refresh_from_db()
            # Task 12: the `status` column is dropped -- correct the
            # in-memory value (not persisted) for the dict below. Guaranteed
            # to resolve via the engine here (the transition above just
            # succeeded), so the initial-state fallback is defensive
            # symmetry only, it never actually triggers.
            session.status = state_reader.current_state(
                "Interview", session.id
            ) or state_reader.initial_state("Interview")
        except Exception:
            # Task 12: the `status` column is dropped, so there is no direct
            # field write left to fall back to -- the in-memory value below
            # is the only remaining record of this abandon call; a later
            # re-fetch with no engine state resolves to the
            # interview_default preset's initial state instead (documented,
            # reviewed data-loss tradeoff, see Task 12 report Finding 2).
            transition_applied = False
            # CR-07: the broad except is kept (it protects legacy sessions
            # without a WorkflowItemState), but the swallowed error becomes a
            # warning with exc_info and is flagged in the audit entry below.
            logger.warning(
                "InterviewService: workflow transition unavailable for session=%s, "
                "falling back to in-memory-only status", session.id, exc_info=True
            )
            session.status = InterviewSession.STATUS_ABANDONED
            session.version = F("version") + 1
            session.save(update_fields=["modified_at", "version"])

        # CR-07: abandon was the one interview write with NEITHER an audit
        # entry NOR an outbox event -- a user-cancelled session left no trace
        # in either seam. Both are written here, synchronously, inside the
        # @atomic_transaction above, so they commit or roll back with the
        # status change and can never claim a cancellation that did not
        # happen. `operation="transition"` / `entity_type="Interview"` match
        # WorkflowFacade.transition, so a session's audit trail reads as one
        # continuous series. m5: `resulting_artifact_ids` is carried (always
        # empty here) so the key is present on every formalize/abandon audit
        # entry -- a consumer can then branch on the key instead of guessing
        # from the operation's change_reason.
        self._audit(
            ctx=ctx,
            operation="transition",
            entity_type="Interview",
            entity_id=session.id,
            change_reason="Cancelled by user",
            details={
                "session_kind": session.session_kind,
                "artifact_type": session.artifact_type,
                "resulting_artifact_ids": [],
                "new_state": session.status,
                "workflow_transition_applied": transition_applied,
            },
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.INTERVIEW_ABANDONED,
                entity_id=session.id,
                workspace_id=session.workspace_id,
                payload={
                    "session_kind": session.session_kind,
                    "artifact_type": session.artifact_type,
                },
            )
        )
        return {"status": session.status}

    def propose(self, ctx, session_id: UUID) -> list[dict] | None:
        """Return the pending multi-artifact proposal for *session_id*, or None.

        Sourced from ``grounding_snapshot["pending_proposal"]`` -- written by
        ``generate_chat_turn()`` whenever the LLM emitted a parseable
        proposal; None until then (multi-artifact plan Task 5).
        """
        session = self._get_session(ctx, session_id)
        return session.grounding_snapshot.get("pending_proposal")

    def provenance_session_id(self, ctx, artifact_id: UUID) -> str | None:
        """Resolve the interview session that created *artifact_id*, if any.

        Reads the ``InterviewSessionArtifact`` provenance join row written by
        both ``_formalize_single`` (L2.3) and ``_formalize_multi`` -- the
        reverse lookup of "which interview produced this artifact".

        *artifact_id* may be **either** a ``persistence.Artifact`` PK (what
        the join row stores) **or** a business-entity/subtype id such as
        ``Requirement.id`` -- every artifact detail view holds the latter
        (see RightSidebar's ``artifactId`` prop), and the two are distinct
        UUIDs. Resolution goes through ``TraceLinkService``'s existing public
        10-type bridge rather than a second, drifting resolver.

        Tenant scoping comes from the thread-local manager via
        ``_set_tenant_context``, so an id from another tenant resolves to
        None rather than leaking the owning session.

        Returns the session's id as a string, or None when no provenance row
        exists -- a missing row is a normal answer ("not created by an
        interview"), not an error. An id that resolves to nothing at all is
        likewise None, not a raised NotFoundError: this backs a purely
        informational badge.
        """
        self._set_tenant_context(ctx)
        # No select_related("session"): only `row.session_id` is read below,
        # and that is a local FK column -- joining the session table would
        # fetch a row nothing touches.
        row = InterviewSessionArtifact.objects.filter(artifact_id=artifact_id).first()
        if row is None:
            from application.trace_link_service import TraceLinkService

            try:
                resolved = TraceLinkService().resolve_entity_to_artifact_id(
                    artifact_id, ctx=ctx
                )
            except NotFoundError:
                return None
            if resolved == artifact_id:
                # Already an Artifact PK -- the first probe was authoritative.
                return None
            row = InterviewSessionArtifact.objects.filter(artifact_id=resolved).first()
            if row is None:
                return None
        return str(row.session_id)

    def list_sessions(self, ctx, workspace_id: UUID, status: str | None = None):
        self._set_tenant_context(ctx)
        # Flip stale rows before filtering, so a "status=in_progress" list
        # doesn't include sessions that are stale-but-not-yet-read
        # individually (list_sessions has no single row to lazily patch the
        # way _get_session does).
        self._abandon_stale_sessions(ctx, workspace_id)

        qs = InterviewSession.objects.filter(workspace_id=workspace_id)
        if status:
            # Datenmodell-Konsolidierung Phase 1: the status column is no
            # longer written by the engine, so an explicit status filter is
            # matched through WorkflowItemState (batched). Task 12: ``status``
            # is dropped from the ``.values()`` projection -- a session never
            # wired into a WorkflowItemState falls back to the
            # interview_default preset's initial state.
            qs = qs.filter(id__in=self._ids_in_engine_state(workspace_id, status))
        return qs.order_by("-modified_at")

    def _abandon_stale_sessions(self, ctx, workspace_id: UUID) -> None:
        """Run the stale-session housekeeping sweep for one workspace.

        Per-row (not a bulk .update()) since each transition needs its own
        WorkflowItemState mutation + history entry -- an infrequent
        housekeeping sweep over a handful of stale rows, not a hot path.
        """
        for stale_id in self._ids_in_engine_state(
            workspace_id, InterviewSession.STATUS_IN_PROGRESS, stale_only=True
        ):
            stale_session = InterviewSession.objects.filter(id=stale_id).first()
            if stale_session is not None:
                self._lazily_abandon_if_stale(stale_session, ctx)

    def _ids_in_engine_state(
        self, workspace_id: UUID, expected_state: str, *, stale_only: bool = False
    ) -> list[UUID]:
        """IDs of the workspace's sessions whose *engine* state is *expected_state*.

        Datenmodell-Konsolidierung Phase 1: the ``status`` column is
        write-once at creation and never updates for a tracked session, so
        a SQL-level ``status=STATUS_IN_PROGRESS`` filter can no longer
        narrow this query -- every single-mode session that ever
        engine-completed would still match it, growing with total
        historical session count instead of the genuinely-stale count.
        With *stale_only* the query filters on ``modified_at`` alone
        (still reliable) to get the TTL candidates, then batch-resolves
        engine state for exactly that set in one query and only keeps rows
        whose *engine* state is still "in_progress" -- the expensive
        per-candidate fetch-then-check loop now runs only over the small,
        genuinely-stale subset, not every old session.
        Task 12: ``status`` is dropped from the ``.values()`` projection --
        a row with no WorkflowItemState falls back to the
        interview_default preset's initial state (documented, reviewed
        data-loss tradeoff, see Task 12 report Finding 2).
        """
        base = InterviewSession.objects.filter(workspace_id=workspace_id)
        if stale_only:
            base = base.filter(modified_at__lt=timezone.now() - ABANDONED_TTL)
        rows = list(base.values("id"))
        states = state_reader.current_states("Interview", (row["id"] for row in rows))
        initial_state = state_reader.initial_state("Interview")
        return [
            row["id"]
            for row in rows
            if (states.get(str(row["id"])) or initial_state) == expected_state
        ]

    def get(self, ctx, session_id: UUID) -> InterviewSession:
        return self._get_session(ctx, session_id)
