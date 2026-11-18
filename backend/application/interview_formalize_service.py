"""Single-mode interview formalization (R2S-010 split from interview_service).

Owns the single-artifact completion pipeline: lock, guards, artifact write,
workflow transition and audit/event recording. Imported by the core facade,
never called directly by transports -- the public entry point stays
``InterviewService.formalize``.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F

from application.base import NotFoundError, ValidationError
from application.models import DomainEventOutbox
from persistence.models import InterviewSession, InterviewSessionArtifact
from persistence.transactions import atomic_transaction
from workflow import state_reader

# Keep the original log category: operators filter on it, and the split must
# not change observable logging behaviour.
logger = logging.getLogger("application.interview_service")

class InterviewFormalizationMixin:
    """Single-kind formalize path; mixed into :class:`InterviewService`."""

    @atomic_transaction
    def formalize(
        self, ctx, session_id: UUID, confirmed_proposal: list[dict] | None = None
    ) -> dict[str, Any]:
        """Turn the session's collected answers into real artifact(s) --
        spec §5 point 4.

        Single-kind sessions drive one typed artifact through the classic
        protocol, dispatching through ``ARTIFACT_CREATION_ADAPTERS`` for all
        8 in-scope artifact types (L2.1). ``_structural_candidates``
        (grounding, a separate concern) is out of scope for the
        Interview-Engine-Fix spec and stays as-is.

        Multi-kind sessions take a caller-confirmed ``confirmed_proposal``
        (list of ``{"type", "fields", "links"}`` items) and create every
        artifact in ONE transaction via ARTIFACT_CREATION_ADAPTERS, writing
        provenance rows and proposed trace links atomically -- any failure
        rolls back the whole batch.

        The WRITE-permission check runs centrally here, BEFORE the dispatch:
        several adapters call services that perform no WRITE check of their
        own (e.g. GlossaryService.create), so this is the single enforcement
        point for every type created by an interview.

        If the single-mode session was grounded onto an existing artifact
        (``target_artifact_id`` set, e.g. by a future grounding-confirmation
        flow), that artifact is updated instead of creating a new one. Its
        existence is re-checked here, at write time -- spec §9: grounding
        may be stale by the time formalize() runs, so a deleted target must
        raise ``NotFoundError`` rather than silently creating a new artifact
        (wrong outcome) or updating a row that no longer exists (impossible).

        ``target_artifact_id`` is an ``Artifact`` PK, not a ``Requirement``
        PK -- ``Requirement.artifact`` is a ``OneToOneField`` with its own
        id (see ``reqif_import_service.py``'s identical
        ``Requirement.objects.filter(artifact_id=...)`` lookup), so it has
        to be resolved through that FK rather than passed straight to
        ``RequirementService.get_requirement``/``update_requirement``, which
        both take the Requirement's own id.
        """
        self._assert_write_permission(ctx)
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot formalize."
            )

        if session.session_kind == InterviewSession.SESSION_KIND_MULTI:
            return self._formalize_multi(ctx, session, confirmed_proposal or [])
        return self._formalize_single(ctx, session)

    def _formalize_single(self, ctx, session) -> dict[str, Any]:
        """Single-kind path: lock the session, then run the writer.

        CR-06: this wrapper takes the same row lock + status recheck that
        ``_formalize_multi`` has had since its M2 review finding. The
        ``in_progress`` guard in ``formalize()`` reads the row UNLOCKED, so
        without the lock two concurrent single-mode ``formalize()`` calls
        could both observe ``in_progress`` and go on to create an artifact,
        bump ``version`` and emit a successful ``INTERVIEW_FORMALIZED`` event
        for one session -- a check-then-act race. ``select_for_update()``
        makes the loser block until the winner commits, after which the
        recheck below fails it deterministically (exactly one completion,
        exactly one audit entry, exactly one outbox event).

        The writer itself lives in ``_write_single_artifact`` so the lock
        wraps the *whole* mutation -- lock and recheck are only useful if
        they span the writes they protect.
        """
        with transaction.atomic():
            locked_session = self._lock_in_progress_session(session)
            return self._write_single_artifact(ctx, locked_session)

    @staticmethod
    def _lock_in_progress_session(
        session: InterviewSession, action: str = "formalize"
    ) -> InterviewSession:
        """Re-read *session* under a row lock and re-validate ``in_progress``.

        Returns the locked row, with its engine-resolved ``status``
        corrected in memory. Raises ``ValidationError`` when the session is
        no longer ``in_progress`` -- which is how the losing racer learns it
        lost. Must be called inside an active ``transaction.atomic()`` block;
        the lock is released by COMMIT/ROLLBACK of that block.

        Single owner of the guard (M4): the row lock, the engine-resolved
        status re-read and the ``in_progress`` precondition live HERE and
        nowhere else. ``_formalize_multi`` used to carry a byte-identical
        inline copy; two owners of one invariant drift, and the message text
        had already started to. ``action`` only shapes the error message so
        ``abandon()`` (M2) does not report "cannot formalize" for a cancel.

        Callers beyond the two formalize paths: ``abandon()`` must take this
        lock too. It read ``session.status`` unlocked and never locked, so
        ``abandon()`` could interleave with ``formalize()``'s engine
        transition ``in_progress -> completed`` and — having read
        ``in_progress`` first, then validated after that commit — move a
        JUST-formalized session to ``abandoned``. ``completed -> abandoned``
        is a declared edge of the interview workflow, so the graph validator
        accepts it: a formalized interview was silently un-completed.

        Deferred DB-level follow-up (this lock is the *application-level* half
        of a two-layer guard; the database half is planned, not yet written):

        * Intended: a ``UniqueConstraint(fields=["session", "artifact"])`` on
          ``persistence.models.InterviewSessionArtifact``
          (``pl_interview_session_artifact``).
        * Shape: expand-only. The table already has a plain index on
          ``artifact``; the constraint adds a uniqueness rule on top of the
          existing ``(session, artifact)`` columns and needs no data rewrite,
          no backfill and no contract step to be reverted. It is scoped to the
          *pair* rather than to ``session`` alone on purpose -- a multi-kind
          session legitimately produces one row per created artifact
          (``_formalize_multi``), so a per-session uniqueness rule would reject
          valid multi-formalize results. A repeated provenance row for the very
          same session *and* artifact is never legitimate.
        * Precondition before writing the migration: a duplicate pre-check over
          existing rows (group by ``session_id, artifact_id``, expect zero
          groups with ``count(*) > 1``). The constraint cannot be created on a
          table that already violates it, and this table predates the current
          formalize locking, so duplicates would fail the migration at apply
          time rather than at review time. Purge any duplicates found before
          adding the constraint; do not let the migration decide.
        * Why deferred: the formalize paths are already serialised by this
          lock, and adding a schema migration was out of scope for this pass --
          it was to be introduced only with a separate migration approval. Until
          the constraint lands, duplicate provenance stays possible for any
          write path that does not take this lock (backfills, re-entrant
          service calls, ad-hoc scripts), which is precisely what the constraint
          is meant to make impossible.
        """
        locked_session = InterviewSession.objects.select_for_update().get(pk=session.pk)
        # Datenmodell-Konsolidierung Phase 1: the row-locked re-fetch bypasses
        # _get_session's correction -- resolve through the engine again. Task 12:
        # the `status` column is dropped, so a session with no WorkflowItemState
        # row (init failed, or predates the Task 12 fix that registers
        # multi-mode sessions too) falls back to the interview_default preset's
        # initial state -- same fallback _formalize_multi applies.
        locked_status = state_reader.current_state(
            "Interview", locked_session.id
        ) or state_reader.initial_state("Interview")
        if locked_status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session.pk} is {locked_status}, cannot {action}."
            )
        locked_session.status = locked_status
        return locked_session

    def _write_single_artifact(self, ctx, session) -> dict[str, Any]:
        """Single-kind writer: one typed artifact from collected_fields.

        Dispatches through ARTIFACT_CREATION_ADAPTERS -- the same registry
        the multi-kind path uses -- so all 8 in-scope artifact types work
        through their production ``create_X()`` service method (workflow
        state initialization included). This replaced a hardcoded
        ``if session.artifact_type != "Requirement": raise`` (spec L2.1).

        The *update* branch (``target_artifact_id`` set) stays
        Requirement-only: generalizing it needs a second, update-flavoured
        adapter registry, which the spec does not ask for -- see
        ``set_target()``'s matching guard.

        Caller contract: must run inside a transaction that holds the row
        lock taken by ``_lock_in_progress_session`` (see ``_formalize_single``).

        Staged into ``_assert_interview_complete`` / ``_require_formalization_title``
        (guards), ``_write_formalization_artifacts`` (the write),
        ``_complete_single_formalization_workflow`` (engine transition) and
        ``_record_single_formalization`` (audit + event); the stage order and
        every side effect below are the original inline sequence.
        """
        self._assert_interview_complete(ctx, session)
        title = self._require_formalization_title(session)
        resulting_ids = self._write_formalization_artifacts(ctx, session, title)

        session.resulting_artifact_ids = resulting_ids
        session.version = F("version") + 1
        session.save(update_fields=["resulting_artifact_ids", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])

        transition_applied = self._complete_single_formalization_workflow(ctx, session)
        self._record_single_formalization(ctx, session, resulting_ids, transition_applied)
        return {"resulting_artifact_ids": resulting_ids, "status": session.status}

    def _assert_interview_complete(self, ctx, session) -> None:
        """Guard stage: reject an incomplete interview before any artifact
        is written.

        Reuses ``get_state()``'s exact missing-fields computation: a
        non-empty ``missing`` from ``_current_phase_and_missing`` means the
        interview is not actually complete yet (see that method's
        docstring/semantics -- it returns the first phase still short a
        required field, or the last phase with an empty list once
        everything is answered). Do not proceed to create/update a real
        artifact -- e.g. an empty-string ``title`` -- off an incomplete
        session.
        """
        _, missing = self._current_phase_and_missing(ctx, session)
        if missing:
            missing_names = ", ".join(f.name for f in missing)
            raise ValidationError(
                f"InterviewSession {session.id} is not complete yet -- missing "
                f"required field(s): {missing_names}. Cannot formalize."
            )

    @staticmethod
    def _require_formalization_title(session) -> str:
        """Guard stage: return the normalized collected ``title``.

        The protocol-completeness guard in ``_assert_interview_complete``
        only trusts the *protocol*: if a workspace's custom
        interview.protocol.<Type> override never declares a ``title``
        field in required_fields, ``missing`` there is trivially empty
        even though ``title`` resolves to "" here. No artifact type may be
        created/updated with an empty title regardless of what the
        protocol says. ``str(...)`` coercion is defense-in-depth (issue
        #542): answer() now rejects non-string title values up front, but
        a stray non-string could still reach here via old rows or a
        future caller that bypasses answer().
        """
        title = str(session.collected_fields.get("title") or "").strip()
        if not title:
            raise ValidationError(
                f"InterviewSession {session.id} has no non-empty 'title' in "
                f"collected_fields; cannot formalize a {session.artifact_type} "
                "without a title."
            )
        return title

    @staticmethod
    def _write_formalization_artifacts(ctx, session, title: str) -> list[str]:
        """Write stage: create or update the backing artifact and return its
        user-facing id(s).

        With ``target_artifact_id`` set (grounded update, issue #540) the
        Requirement-only update branch runs -- generalizing it needs a
        second, update-flavoured adapter registry, which the spec does not
        ask for (see ``set_target()``'s matching guard). The target's
        existence is re-checked here, at write time (spec §9: grounding
        may be stale by the time formalize() runs), so a deleted target
        raises NotFoundError rather than silently creating a new artifact
        (wrong outcome) or updating a row that no longer exists.

        Without a target the artifact is created through
        ``ARTIFACT_CREATION_ADAPTERS`` -- the same registry the multi-kind
        path uses -- so all 8 in-scope artifact types work through their
        production ``create_X()`` service method (workflow state
        initialization included, spec L2.1), plus the provenance join row
        ``_formalize_multi`` writes, so provenance_session_id()/the
        InterviewProvenanceBadge work for single-kind sessions too (L2.3).
        A missing required service field (KeyError) or a protocol field
        name the create_X() signature does not accept (TypeError) is
        caller/config input, not a server fault -- it must never escape as
        an unhandled 500 (same contract as _formalize_multi).
        """
        from application.interview_artifact_adapters import (
            ARTIFACT_CREATION_ADAPTERS,
            build_adapter_fields,
        )

        resulting_ids: list[str] = []

        if session.target_artifact_id is not None:
            from application.requirement_service import RequirementService
            from persistence.models import Requirement

            if session.artifact_type != "Requirement":
                raise ValidationError(
                    f"formalize() cannot update an existing "
                    f"{session.artifact_type!r}: the grounded-update branch is "
                    "Requirement-only. Start a session without a target to "
                    "create a new artifact instead."
                )
            svc = RequirementService()
            target = Requirement.objects.filter(
                artifact_id=session.target_artifact_id
            ).first()
            if target is None:
                raise NotFoundError(
                    f"Target artifact {session.target_artifact_id} no longer "
                    "exists; cannot formalize an update against it."
                )
            updated = svc.update_requirement(
                target.id,
                ctx,
                title=title,
                # C-1: the definition-derived protocol (interview_protocol.py
                # ::protocol_from_definition) elicits whatever attribute the
                # definition marks ai_elicit -- for the bootstrapped
                # Requirement definition that is `description`, never the old
                # hardcoded `rationale` field. Reading only `rationale` here
                # silently formalized every such session with an empty
                # description. `rationale` is kept as a fallback for a
                # hand-written admin protocol override that still names the
                # old field.
                description=(
                    session.collected_fields.get("description")
                    or session.collected_fields.get("rationale")
                    or None
                ),
            )
            # Issue #736: resulting_artifact_ids must carry the Requirement's
            # own id (the "user-facing" id returned by
            # requirement.create/get, resolvable via
            # RequirementService.get_requirement's ``id=`` lookup), not the
            # backing Artifact's id -- the two are distinct UUIDs (see
            # Requirement.artifact OneToOneField). artifact.get_tree() still
            # resolves this id too, via TraceLinkService._resolve_artifact.
            resulting_ids.append(str(updated.id))
        else:
            adapter = ARTIFACT_CREATION_ADAPTERS.get(session.artifact_type)
            if adapter is None:
                raise ValidationError(
                    f"No artifact creation adapter for "
                    f"artifact_type={session.artifact_type!r}."
                )
            fields = build_adapter_fields(session.collected_fields)
            fields["title"] = title  # the normalised/stripped value wins
            try:
                created_ref = adapter(fields, ctx, session.workspace_id)
            except (KeyError, TypeError) as exc:
                # Same contract as _formalize_multi: a missing required
                # service field (KeyError) or a protocol field name the
                # create_X() signature does not accept (TypeError) is
                # caller/config input, not a server fault -- it must never
                # escape as an unhandled 500.
                raise ValidationError(
                    f"cannot formalize {session.artifact_type!r} from the "
                    f"collected answers: {exc}"
                ) from exc
            # Issue #736: report the user-facing subtype id, not the
            # Artifact PK.
            resulting_ids.append(str(created_ref.entity_id))
            # L2.3: the same provenance join row _formalize_multi writes, so
            # provenance_session_id()/the InterviewProvenanceBadge work for
            # single-kind sessions too -- previously only multi-kind
            # artifacts could ever show "created via interview".
            # artifact_id (the Artifact PK), never entity_id: this is an
            # Artifact FK.
            InterviewSessionArtifact.objects.create(
                session=session,
                artifact_id=created_ref.artifact_id,
                artifact_type=created_ref.artifact_type,
            )
        return resulting_ids

    @staticmethod
    def _complete_single_formalization_workflow(ctx, session) -> bool:
        """Workflow stage: best-effort transition to completed; report
        whether the engine actually moved (CR-07).

        The engine transition is best-effort by contract (see the
        except-branch below), so "did it actually reach the engine?" must
        not be inferred from the call having returned. Tracked explicitly
        and recorded in the audit entry's details, so a completion that
        only exists in memory is distinguishable from a real one.
        """
        from workflow.services import transition as workflow_transition

        transition_applied = True
        try:
            workflow_transition(
                item_id=session.id,
                target_state=InterviewSession.STATUS_COMPLETED,
                change_reason="Interview formalized into a real artifact",
                ctx=ctx,
                item_type="Interview",
                workspace_id=session.workspace_id,
            )
            session.refresh_from_db()
            # Task 12: the `status` column is dropped -- correct the
            # in-memory value (not persisted) so the dict returned below
            # reports "completed". Guaranteed to resolve via the engine here
            # (the transition above just succeeded), so the initial-state
            # fallback is defensive symmetry only, it never actually
            # triggers.
            session.status = state_reader.current_state(
                "Interview", session.id
            ) or state_reader.initial_state("Interview")
        except Exception:
            # Same best-effort fallback as _lazily_abandon_if_stale -- a
            # session created before this feature (or with a failed
            # workflow init) has no WorkflowItemState row to transition.
            # Task 12: the `status` column is dropped, so there is no direct
            # field write left to fall back to -- the in-memory value below
            # is the only remaining record of completion for this call; a
            # later re-fetch with no engine state resolves to the
            # interview_default preset's initial state instead (documented,
            # reviewed data-loss tradeoff, see Task 12 report Finding 2).
            transition_applied = False
            # CR-07: the broad except stays (it protects legacy sessions
            # without a WorkflowItemState), but the swallowed error is no
            # longer DEBUG-level silence: warning + exc_info makes the
            # failure path greppable in production logs, and the
            # transition_applied=False return value marks the audit entry so
            # it can never be read as a clean engine transition.
            logger.warning(
                "InterviewService: workflow transition unavailable for session=%s, "
                "falling back to in-memory-only status", session.id, exc_info=True
            )
            session.status = InterviewSession.STATUS_COMPLETED
            session.version = F("version") + 1
            session.save(update_fields=["modified_at", "version"])
        return transition_applied

    def _record_single_formalization(
        self, ctx, session, resulting_ids: list[str], transition_applied: bool
    ) -> None:
        """Record stage: write the audit entry and the
        INTERVIEW_FORMALIZED event.

        formalize() (the caller) wraps this whole method in
        @atomic_transaction, so this is already inside an active
        transaction -- the audit entry and the outbox INSERT below run
        inline in that same transaction (SA-02, and ServiceBase._audit /
        _emit_event are both synchronous writes), and a failed/partial
        formalization above never reaches here.

        CR-07: InterviewService wrote no AuditEntry at all before this --
        every write in this service was invisible to the audit trail, while
        its sibling WorkflowFacade._audit covered the same transition for
        every other item type. ``operation="transition"`` /
        ``entity_type="Interview"`` mirror WorkflowFacade.transition exactly,
        so one entity_id query returns the whole interview lifecycle.
        """
        self._audit(
            ctx=ctx,
            operation="transition",
            entity_type="Interview",
            entity_id=session.id,
            change_reason="Interview formalized into a real artifact",
            details={
                "session_kind": InterviewSession.SESSION_KIND_SINGLE,
                "artifact_type": session.artifact_type,
                "resulting_artifact_ids": resulting_ids,
                "new_state": session.status,
                # False => the completion exists in memory only; the engine
                # has no WorkflowItemState for this session.
                "workflow_transition_applied": transition_applied,
            },
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.INTERVIEW_FORMALIZED,
                entity_id=session.id,
                workspace_id=session.workspace_id,
                payload={
                    # m4: INTERVIEW_FORMALIZED had three payload shapes — single
                    # {artifact_type, resulting_artifact_ids}, multi
                    # {artifact_type, created}, abandon {session_kind,
                    # artifact_type}. session_kind existed only on the abandon
                    # event, so a consumer could not tell a single formalize
                    # from a multi one. It is carried on both formalize payloads
                    # now, so the discriminator is on the event that needs it.
                    "session_kind": InterviewSession.SESSION_KIND_SINGLE,
                    "artifact_type": session.artifact_type,
                    "resulting_artifact_ids": resulting_ids,
                },
            )
        )
