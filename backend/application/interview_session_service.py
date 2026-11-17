"""Interview session lifecycle (R2S-010 split from interview_service).

Owns the read/write lifecycle of one session: creation, shape gates,
read-only state projection, typed answers, protocol field validation and
grounding target selection. Stale-sweep/housekeeping lives in
``interview_housekeeping_service``.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.db.models import F

from application.base import NotFoundError, ValidationError
from application.interview_protocol import (
    IN_SCOPE_ARTIFACT_TYPES,
    get_protocol,
    normalize_artifact_type,
)
from persistence.models import InterviewSession, Workspace
from persistence.transactions import atomic_transaction
from workflow import state_reader

# Keep the original log category: operators filter on it, and the split must
# not change observable logging behaviour.
logger = logging.getLogger("application.interview_service")

class InterviewSessionMixin:
    """Session CRUD/state machine; mixed into :class:`InterviewService`."""

    @atomic_transaction
    def start(
        self,
        ctx,
        artifact_type: str | None,
        workspace_id: UUID,
        session_kind: str = InterviewSession.SESSION_KIND_SINGLE,
        seed_context: dict | None = None,
    ) -> InterviewSession:
        """Start an interview session (multi-artifact plan Task 6).

        ``session_kind="single"`` (default) drives one typed artifact via
        the classic per-type protocol and requires *artifact_type*;
        ``session_kind="multi"`` starts a type-less discovery session
        (*artifact_type* must be None) whose artifacts are proposed during
        chat and created later by ``_formalize_multi``.
        """
        self._assert_known_session_kind(session_kind)
        # #1611: resolve the caller's spelling ("requirement", "need", ...) to
        # the canonical type before the shape gate below, which still compares
        # against the exact canonical tuple. An unknown value is refused here
        # with `allowed_values`; a *known* type without a protocol (MainGoal)
        # falls through to the shape gate's own "not available" answer.
        artifact_type = normalize_artifact_type(artifact_type)
        self._assert_session_shape(session_kind, artifact_type)
        self._set_tenant_context(ctx)
        # Fail fast with a clean NotFoundError (same pattern as
        # RequirementService.create_requirement) rather than letting
        # InterviewSession's FK constraint raise a bare IntegrityError on an
        # unknown workspace_id, which the MCP layer's generic exception
        # handler would otherwise surface as an opaque INTERNAL_ERROR.
        if not Workspace.objects.filter(id=workspace_id).exists():
            raise NotFoundError(f"Workspace {workspace_id} not found")
        if session_kind == InterviewSession.SESSION_KIND_MULTI:
            return self._start_multi_session(ctx, workspace_id, session_kind, seed_context)
        return self._start_single_session(
            ctx, artifact_type, workspace_id, session_kind, seed_context
        )

    @staticmethod
    def _assert_known_session_kind(session_kind: str) -> None:
        """Whitelist gate for the session kind (runs before any other gate)."""
        # Review-2 fix m2a: whitelist gate. An unknown session_kind used to
        # fall through every kind-specific gate below and be silently
        # created as a broken single-ish row (Django choices are not DB
        # constraints) -- reject it cleanly instead.
        if session_kind not in (
            InterviewSession.SESSION_KIND_SINGLE,
            InterviewSession.SESSION_KIND_MULTI,
        ):
            raise ValidationError(
                f"Unknown session_kind {session_kind!r}; must be "
                f"'{InterviewSession.SESSION_KIND_SINGLE}' or "
                f"'{InterviewSession.SESSION_KIND_MULTI}'."
            )

    @staticmethod
    def _assert_session_shape(session_kind: str, artifact_type: str | None) -> None:
        """Mode/shape gates -- pure input validation that must run before
        anything below can mis-read a cross-kind combination (e.g. multi +
        a leftover artifact_type)."""
        if session_kind == InterviewSession.SESSION_KIND_MULTI and artifact_type is not None:
            raise ValidationError(
                "artifact_type must not be set for a multi-mode interview"
            )
        if session_kind == InterviewSession.SESSION_KIND_SINGLE and not artifact_type:
            raise ValidationError(
                "artifact_type is required for a single-mode interview"
            )
        # Unchanged single-mode gate -- guarded with != MULTI so the multi
        # branch (artifact_type=None by definition) can never reach it;
        # for every non-multi kind this is the exact same check in the
        # exact same position as before Task 6.
        #
        # #1611: by now the value has been resolved by
        # ``normalize_artifact_type``, so reaching this branch means the type
        # is *known* but has no interview protocol (MainGoal). The old message
        # lumped that together with unknown values ("other unknown types are
        # unsupported"), which is why a lowercase ``requirement`` looked like a
        # product limitation instead of a spelling problem.
        if session_kind != InterviewSession.SESSION_KIND_MULTI and (
            artifact_type not in IN_SCOPE_ARTIFACT_TYPES
        ):
            raise ValidationError(
                f"Interviews are not available for artifact_type={artifact_type!r}: "
                f"it is a known artifact type without an interview protocol "
                f"(MainGoal stays read-only). Supported types: "
                f"{', '.join(IN_SCOPE_ARTIFACT_TYPES)}."
            )

    @staticmethod
    def _start_multi_session(
        ctx, workspace_id: UUID, session_kind: str, seed_context: dict | None
    ) -> InterviewSession:
        """Create the type-less multi-mode session and return it."""
        # Multi-mode sessions are not bound to one artifact type: no
        # per-type protocol applies (get_protocol has no answer for
        # artifact_type=None) and there is no single backing Artifact yet
        # -- but the "Interview" workflow item_type is the same state
        # machine for both kinds (state_reader.current_state("Interview",
        # session.id) does not care about session_kind), and
        # initialize_workflow_states needs neither artifact_type nor a
        # backing Artifact. Datenmodell-Konsolidierung Task 12: a
        # multi-mode session used to record its completion directly on the
        # (now-dropped) `status` column with no engine tracking at
        # all -- that was the only record of completion, and dropping
        # the column would have made it unrecoverable. Registering here,
        # same best-effort try/except convention as the single-mode
        # branch below, closes that gap instead of accepting it.
        session = InterviewSession.objects.create(
            workspace_id=workspace_id,
            artifact_type=None,
            session_kind=session_kind,
            collected_fields=(seed_context or {}),
        )
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[session.id],
                item_type="Interview",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:  # noqa: BLE001 — best-effort workflow init; logged at debug
            logger.debug(
                "InterviewService: workflow init skipped for multi-mode "
                "session=%s", session.id
            )
        return session

    @staticmethod
    def _start_single_session(
        ctx,
        artifact_type: str | None,
        workspace_id: UUID,
        session_kind: str,
        seed_context: dict | None,
    ) -> InterviewSession:
        """Create the single-mode session (backing Artifact + session) and return it.

        2026-08-20 UI-visibility fix: register with the workflow engine so
        the session is discoverable/transitionable the same way every
        other tracked entity is (workspace-defaults 'interview_default'
        preset, see workflow/definition_store.py). Best-effort -- a
        missing/misconfigured definition must not block session creation
        (mirrors *_service.py's workflow-init try/except convention, e.g.
        RequirementService.create_requirement).
        """
        # Fail fast if the protocol config is missing/broken rather than
        # creating a session that can never progress past get_state.
        get_protocol(ctx, artifact_type, workspace_id)
        from persistence.models import Artifact
        from workflow.services import initialize_workflow_states

        artifact = Artifact.objects.create(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            artifact_type="Interview",
            custom_fields={},
        )
        session = InterviewSession.objects.create(
            workspace_id=workspace_id,
            artifact=artifact,
            artifact_type=artifact_type,
            session_kind=session_kind,
            collected_fields=(seed_context or {}),
        )
        try:
            initialize_workflow_states(
                item_ids=[session.id],
                item_type="Interview",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:  # noqa: BLE001 — best-effort workflow init; logged at debug
            logger.debug(
                "InterviewService: workflow init skipped for session=%s", session.id
            )
        return session

    def _get_session(self, ctx, session_id: UUID) -> InterviewSession:
        self._set_tenant_context(ctx)
        session = InterviewSession.objects.filter(id=session_id).first()
        if session is None:
            raise NotFoundError(f"InterviewSession {session_id} not found")
        # AUD-2026-09-169: this method is strictly read-only. It used to run
        # the stale-auto-abandon sweep, so ``GET /interviews/{id}/state/`` (and
        # every other read) mutated ``WorkflowItemState`` behind the caller's
        # back. The sweep now lives only in the explicit bulk housekeeping
        # path (``list_sessions``) where a write is expected; single-entity
        # reads never touch the database.
        #
        # Datenmodell-Konsolidierung Phase 1: root-cause fix for every guard
        # in this service that compares ``session.status`` (answer/set_target/
        # formalize/abandon/chat all call this method first) -- resolve the
        # in-memory value through the engine here, once, instead of at each
        # call site. Task 12: the `status` column is dropped, so there is no
        # column left to fall back to. ``getattr(..., None)`` picks up a
        # value ``_lazily_abandon_if_stale`` may already have set in-memory
        # (its own except-branch has no column to persist to either, so its
        # correction must survive this line, not be clobbered by it); when
        # neither the engine nor that already-resolved value exist, the
        # session reports the interview_default preset's initial state
        # (documented, reviewed data-loss tradeoff, see Task 12 report
        # Finding 2).
        session.status = (
            state_reader.current_state("Interview", session.id)
            or getattr(session, "status", None)
            or state_reader.initial_state("Interview")
        )
        return session

    def _current_phase_and_missing(self, ctx, session: InterviewSession):
        protocol = get_protocol(ctx, session.artifact_type, session.workspace_id)
        for phase in protocol.phases:
            missing = [
                f for f in phase.required_fields
                if f.name not in session.collected_fields
            ]
            if missing:
                return phase, missing
        # Every field of every phase is answered.
        return protocol.phases[-1], []

    @staticmethod
    def _serialise_field(f) -> dict[str, Any]:
        # Spec 2 (Hermes plugin, §3-4): InterviewFormView renders one input
        # per missing field and needs its type/choices to pick the right
        # control (text/textarea/enum/number) -- a bare field-name string
        # would lose exactly the information the protocol config's `type`
        # amendment was added for. Every host consumes this same shape;
        # skill-driven hosts (Claude Code/Opencode/Antigravity) just read
        # `.name` and ignore `.type`/`.choices`.
        return {"name": f.name, "type": f.type, "choices": f.choices}

    def get_state(self, ctx, session_id: UUID) -> dict[str, Any]:
        session = self._get_session(ctx, session_id)
        # _get_session already resolves session.status through the engine.
        status = session.status
        if session.session_kind == InterviewSession.SESSION_KIND_MULTI:
            # Multi sessions have artifact_type=None: the per-type protocol
            # resolver (get_protocol) has no answer for that and would raise
            # ProtocolValidationError -- an unhandled 500 at every facade
            # (review finding B1). Multi mode has no phase/missing_fields
            # concept, so the state shape omits both keys by design.
            return {
                "session_id": str(session.id),
                "status": status,
                # Final-review finding B2: the only discriminator a consumer
                # has for "is this a multi session". Without it the web UI's
                # chat pane gates the whole proposal/confirm flow away (it
                # treats a missing key as "single"), leaving a multi session
                # able to chat but never able to formalise anything. Additive,
                # same precedent as `transcript`/`transcript_summary` below.
                "session_kind": session.session_kind,
                "collected_fields": session.collected_fields,
                "grounding_snapshot": session.grounding_snapshot,
                "transcript": session.transcript,
            }
        phase, missing = self._current_phase_and_missing(ctx, session)
        return {
            "session_id": str(session.id),
            "status": status,
            # Emitted in BOTH branches on purpose: a consumer that has to
            # check `"session_kind" in state` before trusting it is exactly
            # the ambiguity finding B2 was about.
            "session_kind": session.session_kind,
            "phase": phase.name,
            "collected_fields": session.collected_fields,
            "missing_fields": [self._serialise_field(f) for f in missing],
            "grounding_snapshot": session.grounding_snapshot,
            # Web Widget spec §9 -- the chat pane needs the full transcript
            # to render conversation history on mount/resume. Additive and
            # harmless to the Hermes plugin's form view, which ignores it.
            "transcript": session.transcript,
            # L2.4 review fix F5: `transcript` is only the sliding window, so
            # without this key every consumer silently loses the older half of
            # the conversation the moment compression fires -- not just on
            # resume, but live (InterviewChatPane renders `state.transcript`
            # after every turn). Additive for the same reason `transcript`
            # itself was: hosts that don't know the key ignore it. Every
            # single-mode facade (REST _state_dict, MCP _handle_get_state,
            # generate_chat_turn's own return) reads this one dict, so this
            # is the only place it needs to be added. Multi-mode state dicts
            # deliberately omit it -- compression only runs on the single-mode
            # chat path, so their summary is always "".
            "transcript_summary": session.transcript_summary,
        }

    @atomic_transaction
    def answer(self, ctx, session_id: UUID, field: str, value: Any) -> InterviewSession:
        session = self._get_session(ctx, session_id)
        if session.session_kind == InterviewSession.SESSION_KIND_MULTI:
            # Field-by-field answering is a single-mode protocol concept
            # (review finding B1): without this guard the call would fall
            # through to get_protocol(artifact_type=None) and raise an
            # unhandled ProtocolValidationError. Multi sessions take free-
            # form chat input instead.
            raise ValidationError(
                f"InterviewSession {session_id} is a multi-mode session; "
                "field answers are not applicable -- use chat()."
            )
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot answer."
            )
        # issue #542: validate against the protocol's declared field type
        # before storing. issue #738 (supersedes #542's "permissive about
        # unknown field names" decision): a field name that resolves to no
        # protocol field across any phase is rejected outright instead of
        # being echoed back into collected_fields unvalidated -- letting an
        # arbitrary caller-supplied field name persist into session state
        # (and from there into the LLM context / eventually the formalized
        # artifact) is confusing session state at best and a prompt-shaping
        # attack surface at worst. Answering an already-collected field
        # again is still allowed: _find_protocol_field looks across every
        # phase's required_fields, not just the current phase's still-
        # missing ones.
        protocol = get_protocol(ctx, session.artifact_type, session.workspace_id)
        protocol_field = self._find_protocol_field(protocol, field)
        if protocol_field is None:
            valid_names = sorted(
                {f.name for phase in protocol.phases for f in phase.required_fields}
            )
            raise ValidationError(
                f"Unknown field {field!r} for artifact_type={session.artifact_type!r}; "
                f"valid fields are {valid_names!r}."
            )
        self._validate_field_value_type(protocol_field, value)
        session.collected_fields = {**session.collected_fields, field: value}
        session.version = F("version") + 1
        session.save(update_fields=["collected_fields", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])
        return session

    @staticmethod
    def _find_protocol_field(protocol, field_name: str):
        """Look up a field by name across every phase of *protocol*.

        Same traversal ``_current_phase_and_missing`` already does over
        ``phase.required_fields``, factored out here (issue #542) so
        ``answer()`` can resolve a single field by name without
        reimplementing the nested loop.

        Returns ``None`` if no phase declares a field with that name.
        """
        for phase in protocol.phases:
            for candidate in phase.required_fields:
                if candidate.name == field_name:
                    return candidate
        return None

    @staticmethod
    def _validate_field_value_type(field, value: Any) -> None:
        """Validate *value* against *field*'s declared protocol type -- issue #542.

        Only called for fields that resolve to a real protocol field (see
        ``_find_protocol_field``); raises ``ValidationError`` naming the
        field, its expected type, and what was actually received.
        Dispatches to one validator per declared protocol type; an
        unknown type validates nothing (same as before the split).
        """
        if field.type == "number":
            InterviewSessionMixin._validate_number_value(field, value)
        elif field.type == "enum":
            InterviewSessionMixin._validate_enum_value(field, value)
        elif field.type in ("text", "textarea"):
            InterviewSessionMixin._validate_text_value(field, value)

    @staticmethod
    def _validate_number_value(field, value: Any) -> None:
        """Number-typed protocol field validator (see ``_validate_field_value_type``)."""
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValidationError(
                f"Field {field.name!r} expects a number, got "
                f"{type(value).__name__}."
            )
        if isinstance(value, str):
            try:
                float(value)
            except ValueError:
                raise ValidationError(
                    f"Field {field.name!r} expects a number, got a "
                    f"non-numeric string {value!r}."
                )

    @staticmethod
    def _validate_enum_value(field, value: Any) -> None:
        """Enum-typed protocol field validator (see ``_validate_field_value_type``)."""
        if value not in (field.choices or []):
            raise ValidationError(
                f"Field {field.name!r} expects one of {field.choices!r}, "
                f"got {value!r}."
            )

    @staticmethod
    def _validate_text_value(field, value: Any) -> None:
        """Text/textarea protocol field validator (see ``_validate_field_value_type``)."""
        if not isinstance(value, str):
            raise ValidationError(
                f"Field {field.name!r} expects a string ({field.type}), "
                f"got {type(value).__name__}."
            )

    @atomic_transaction
    def set_target(self, ctx, session_id: UUID, artifact_id: UUID) -> dict[str, Any]:
        """Confirm a ``grounding_context()`` candidate (or any already-known
        artifact_id) as the session's ``formalize()`` update target --
        issue #540.

        Without this, ``target_artifact_id`` was write-only dead code:
        ``grounding_context()`` surfaces candidates but nothing ever set the
        field, so ``formalize()``'s "update an existing artifact" branch was
        unreachable through the real MCP surface. This is that missing
        write path.

        Requirement only: formalize()'s grounded-UPDATE branch is
        Requirement-only (its CREATE branch handles all 8 in-scope types,
        via ARTIFACT_CREATION_ADAPTERS) -- setting a target on a session
        whose ``artifact_type`` formalize() can't update yet would be a
        target formalize() can never use, so reject it here instead of
        silently accepting a value that goes nowhere.

        Re-checks that ``artifact_id`` resolves to a real ``Requirement``
        right now, mirroring ``formalize()``'s own target re-check
        (``Requirement.objects.filter(artifact_id=...).first()``) rather
        than trusting the caller's possibly-stale ``grounding_context()``
        snapshot -- same spec §9 staleness concern formalize() already
        guards against at write time.
        """
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot set target."
            )
        if session.artifact_type != "Requirement":
            raise ValidationError(
                f"set_target() for artifact_type={session.artifact_type!r} is not "
                "supported -- formalize()'s grounded-UPDATE branch is "
                "Requirement-only (its CREATE branch handles all 8 in-scope "
                "types), so a target on any other artifact_type could never "
                "be used. Start a session without a target instead."
            )

        from persistence.models import Requirement

        if not Requirement.objects.filter(artifact_id=artifact_id).exists():
            raise NotFoundError(f"Requirement with artifact_id={artifact_id} not found")

        session.target_artifact_id = artifact_id
        session.version = F("version") + 1
        session.save(update_fields=["target_artifact_id", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])
        # Reuse get_state()'s shape rather than hand-rolling a parallel one
        # (see this method's judgment-call note in the issue #540 report):
        # every other read of "session state" already goes through
        # get_state(), and returning it here means a host sees the
        # newly-set target reflected immediately without a second round
        # trip, the same way formalize()/grounding_context() return a
        # ready-to-use result dict rather than the bare ORM object.
        return self.get_state(ctx, session_id)
