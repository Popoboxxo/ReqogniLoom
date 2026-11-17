"""InterviewService facade + chat-turn orchestration (R2S-010).

SIZE CAP: one interview unit stays at or below 600 lines (docstring through
last method). The former 2776-line god-service was split along existing
cohesion seams; each move is a mixin imported below, so the public class,
method set, DTOs, tool names, exceptions and import paths are unchanged.

Responsibilities moved (all re-exported above):
  * interview_session_service.py -- start/answer/get_state/set_target +
    protocol field validation (active session lifecycle).
  * interview_formalize_service.py -- single-mode formalize pipeline.
  * interview_multi_formalize_service.py -- multi-mode formalize + the
    confirmed_proposal validation gate.
  * interview_grounding_service.py -- grounding candidates + AI ranking.
  * interview_housekeeping_service.py -- abandon/list/provenance/stale sweep.
  * interview_transcript_service.py -- overflow transcript digest.

Kept here on purpose: chat-turn prompt construction and orchestration.
The ``build_memory_context`` emission in ``_chat_turn_prompt`` is pinned to
this module by backend/memory/tests/test_build_memory_context_callers.py;
moving it would require a separate architecture-gate change, which is out
of scope for a behaviour-preserving split.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta  # noqa: F401 - pre-split namespace, kept for callers
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from application.base import NotFoundError, ServiceBase, ValidationError  # noqa: F401
from application.interview_protocol import (
    IN_SCOPE_ARTIFACT_TYPES,  # noqa: F401
    get_protocol,
    normalize_artifact_type,  # noqa: F401
)
from application.models import DomainEventOutbox
from persistence.models import (
    InterviewSession,
    InterviewSessionArtifact,  # noqa: F401
    Workspace,  # noqa: F401
)
from persistence.transactions import atomic_transaction  # noqa: F401
from workflow import state_reader  # noqa: F401

logger = logging.getLogger(__name__)

# Backwards-compatibility re-exports (R2S-010): every public name and the
# externally imported private validator keep their original import path.
from application.interview_formalize_service import InterviewFormalizationMixin
from application.interview_grounding_service import (
    GROUNDING_RANK_PROMPT_TEMPLATE_NAME,  # noqa: F401
    InterviewGroundingMixin,
)
from application.interview_housekeeping_service import (
    ABANDONED_TTL,  # noqa: F401
    InterviewHousekeepingMixin,
)
from application.interview_multi_formalize_service import (
    _DIAGRAM_REF_LINK_TYPE,  # noqa: F401
    _RESERVED_PROPOSAL_FIELDS,  # noqa: F401
    _SHORT_STRING_FIELDS,  # noqa: F401
    MAX_PROPOSAL_CONTAINER_ITEMS,  # noqa: F401
    MAX_PROPOSAL_STRING_LENGTH,  # noqa: F401
    MAX_PROPOSAL_TITLE_LENGTH,  # noqa: F401
    InterviewMultiFormalizationMixin,
    _tenant_custom_attribute_names,  # noqa: F401
    _validate_confirmed_proposal,  # noqa: F401
    _validate_confirmed_proposal_item,  # noqa: F401
    _validate_confirmed_proposal_link,  # noqa: F401
    _validate_proposal_field_value,  # noqa: F401
    validate_confirmed_proposal_fields,  # noqa: F401
)
from application.interview_session_service import InterviewSessionMixin
from application.interview_transcript_service import (
    TRANSCRIPT_WINDOW_TURNS,  # noqa: F401
    InterviewTranscriptMixin,
)


class InterviewService(
    InterviewFormalizationMixin,
    InterviewMultiFormalizationMixin,
    InterviewGroundingMixin,
    InterviewSessionMixin,
    InterviewHousekeepingMixin,
    InterviewTranscriptMixin,
    ServiceBase,
):
    """Single entry point for the interview engine (ADR-01).

    Domain methods are composed from the cohesive mixins above; this class
    contributes the single/multi chat-turn orchestration only. Composition
    keeps one object identity, so every ``self._helper()`` call resolves
    exactly as it did before the split.
    """

    def _chat_turn_prompt(
        self,
        ctx,
        session: InterviewSession,
        user_message: str,
        phase,
        missing: list,
    ) -> str:
        """Build the single-mode chat-turn prompt -- memory + template render.

        Composes the best-effort memory context and renders the
        ``interview.chat_turn`` template with the phase/missing-field
        fragments the protocol still needs. Pure prompt construction: no
        provider call, no persistence, no event.
        """
        from application.ai_derivation_service import AiDerivationService
        from application.prompt_resolver import resolve_config_values
        from memory.context_builder import (
            MemoryRenderConfig,
            build_memory_context,
            wrap_memory_block,
        )

        # Best-effort retrieval-augmentation (memory plan Task 6): degrades to
        # "" on any backend failure, never blocks the chat turn (see
        # build_memory_context's own docstring for the Fehlerfälle contract).
        # RFC #1002 PR C: the session's backing Artifact (single mode only)
        # is passed so artifact-scoped memory is searched and rendered first.
        #
        # Plan A T-A1-6 (PR-A14 review, finding B1): this bypass consumer used
        # to splice the RAW block into its prompt. It now resolves the
        # ``memory_*`` config for this workspace (scopes/top_k/format/max_chars/
        # ...) exactly like the central resolver and wraps the result with
        # ``wrap_memory_block`` -- the single place the ``<memory>`` data
        # boundary is built. The config lookup is inside the fail-open guard
        # because it touches the database.
        try:
            render_config = MemoryRenderConfig.from_values(
                resolve_config_values(ctx, session.workspace_id)
            )
            memory_context = wrap_memory_block(
                build_memory_context(
                    ctx.tenant_id,
                    session.workspace_id,
                    ctx.user_id,
                    user_message,
                    # Plan A T-A1-2: slot-level policy (workspace/user
                    # switches). This bypass path builds its own prompt instead
                    # of going through resolve_and_render, so it must name its
                    # slot explicitly.
                    slot_name="interview.chat_turn",
                    config=render_config,
                    artifact_id=session.artifact_id,
                    entity_type=session.artifact_type or "",
                )
            )
        except Exception as exc:  # noqa: BLE001 -- fail-open, see docstring
            logger.warning(
                "interview.chat_turn: memory context unavailable, continuing "
                "without it: %s",
                exc,
            )
            memory_context = ""
        template = AiDerivationService._get_template_content(
            ctx, "interview.chat_turn", session.workspace_id
        )
        return AiDerivationService._render(
            template,
            artifact_type=session.artifact_type,
            transcript_json=json.dumps(session.transcript),
            # L2.4: the digest of turns already folded out of `transcript`.
            # `transcript` itself is now the sliding window, not the whole
            # history, so without this the prompt would silently lose context.
            transcript_summary=session.transcript_summary or "",
            current_phase_fragment=phase.prompt_fragment,
            missing_fields_json=json.dumps([self._serialise_field(f) for f in missing]),
            grounding_snapshot_json=json.dumps(session.grounding_snapshot),
            user_message=user_message,
            memory_context=memory_context,
        )

    def _complete_chat_turn(
        self,
        provider,
        provider_name: str,
        audit_logger,
        entity_id: str,
        prompt: str,
    ) -> str:
        """Run the single-mode chat-turn LLM call and return the raw response.

        Deliberately NOT fail-open (spec §5): a failed provider call surfaces
        as ValidationError after the failure audit row is written, exactly as
        when this code still sat inline in ``generate_chat_turn``. On success
        the success audit row and the client-side token estimate (SA-26) are
        written here too, preserving the pre-parse ordering.
        """
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import (
            approximate_token_count,
            record_token_usage,
        )

        timeout = resolve_timeout_seconds("interview.chat_turn")
        try:
            raw_response = provider.complete(
                prompt, purpose="interview.chat_turn", timeout=timeout
            )
        except Exception as error:  # noqa: BLE001 -- not fail-open, see docstring
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.chat_turn",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            raise ValidationError(f"Interview chat LLM call failed: {error}") from error

        audit_logger.log_llm_call(
            provider=provider_name,
            capability="interview.chat_turn",
            artifact_id=entity_id,
            token_usage=None,
            success=True,
            error=None,
        )
        # SA-26: this used to hardcode input_tokens=0, leaving the daily
        # budget (is_over_daily_limit above) blind to this call's real
        # spend. Estimate both sides client-side, matching every other
        # free-form path (see ``approximate_token_count``).
        record_token_usage(
            provider=provider_name,
            capability="interview.chat_turn",
            input_tokens=approximate_token_count(prompt),
            output_tokens=approximate_token_count(raw_response),
        )
        return raw_response

    @staticmethod
    def _parse_chat_turn_reply(raw_response: str) -> tuple[dict[str, Any], str]:
        """Split the model response into ``(extracted_fields, reply)``.

        The JSON contract is lenient by design: a response-shape failure
        (not a provider failure -- that already raised) degrades to "no
        fields extracted, relay the raw text" instead of crashing the chat.
        """
        try:
            parsed = json.loads(raw_response)
            extracted = parsed.get("extracted_fields", {}) or {}
            reply = parsed.get("reply", "")
        except (ValueError, AttributeError):
            # Model didn't follow the JSON contract -- degrade to "no fields
            # extracted, relay the raw text" rather than crashing the chat.
            # This is a response-shape leniency, distinct from the provider-
            # availability contract above: the call itself succeeded.
            extracted = {}
            reply = raw_response
        return extracted, reply

    def _apply_extracted_interview_fields(
        self, ctx, session: InterviewSession, extracted: dict[str, Any]
    ) -> None:
        """Record extracted values for protocol-declared fields only.

        Only values for fields the protocol actually declares are stored
        (mirrors answer()'s own permissive-but-typed-when-known behavior)
        -- an unresolved field name is silently skipped rather than stored,
        since the prompt explicitly instructs the model to only extract
        fields from the "still needed" list.
        """
        protocol = get_protocol(ctx, session.artifact_type, session.workspace_id)
        for field_name, value in extracted.items():
            if self._find_protocol_field(protocol, field_name) is not None:
                self.answer(ctx, session.id, field_name, value)

    def generate_chat_turn(self, ctx, session_id: UUID, user_message: str) -> dict[str, Any]:
        """Server-generated conversational turn -- Web Widget spec §5.

        Unlike grounding_context()'s AI-ranking layer, this is NOT fail-open:
        the web widget has no AI agent of its own to drive the interview
        dialogue (spec §5, Global Constraints), so "no LLM provider
        available" must surface as a ValidationError the widget can show,
        not silently do nothing. A *configured* mock provider (the default
        dev deployment shape, ``LLM_PROVIDER=mock``) is still called though
        -- only a failed provider *resolution* (``_resolve_provider()``
        returning ``None``) raises.

        Appends the user message and the assistant's reply to
        ``session.transcript`` regardless of whether any fields were
        extracted, so a resumed session always shows the full conversation.
        """
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.token_tracking import is_over_daily_limit

        session = self._get_session(ctx, session_id)
        # Status guard BEFORE the kind dispatch (review-2 fix M1): it used
        # to sit after the multi branch, which let a completed/abandoned
        # multi session reach a live LLM call. Hoisting it here rejects
        # both kinds with the same ValidationError; for single sessions the
        # order swap is semantically neutral -- they never entered the
        # multi branch, so they hit this exact check either way.
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(f"InterviewSession {session_id} is {session.status}, cannot chat.")
        if session.session_kind == InterviewSession.SESSION_KIND_MULTI:
            return self._generate_multi_chat_turn(ctx, session, user_message)

        provider, provider_name, resolve_error = self._resolve_provider()
        if provider is None:
            # NOT fail-open (spec §5) -- unlike grounding, there is no
            # meaningful degraded behavior for "have a conversation" without
            # an LLM, so this surfaces as an error rather than silently
            # doing nothing.
            raise ValidationError(f"No LLM provider available for interview chat: {resolve_error}")

        audit_logger = LlmAuditLogger()
        entity_id = str(session.id)

        # REQ-106: per-tenant daily token budget. This free-form flow
        # bypasses CapabilityRouter, so nothing else enforces it -- same
        # reasoning as _rank_candidates_with_ai / BundleCompressionService.
        # Not fail-open here either: an exhausted budget still means "cannot
        # chat right now", not "chat silently does nothing".
        if is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.chat_turn",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise ValidationError(
                "Daily LLM token limit exceeded for this tenant. Try again later "
                "or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        phase, missing = self._current_phase_and_missing(ctx, session)
        prompt = self._chat_turn_prompt(ctx, session, user_message, phase, missing)
        raw_response = self._complete_chat_turn(
            provider, provider_name, audit_logger, entity_id, prompt
        )
        extracted, reply = self._parse_chat_turn_reply(raw_response)
        self._apply_extracted_interview_fields(ctx, session, extracted)

        now = timezone.now().isoformat()
        # The DB write and the event publish are grouped in their own short
        # atomic block (rather than wrapping the whole method, which would
        # hold a transaction open across the blocking LLM call above) so
        # _emit_event's inline outbox INSERT (SA-02, REQ-L2-AS-029) commits
        # atomically with this write specifically.
        with transaction.atomic():
            session.refresh_from_db()
            session.transcript = [
                *session.transcript,
                {"role": "user", "text": user_message, "timestamp": now},
                {"role": "assistant", "text": reply, "timestamp": now},
            ]
            session.version = F("version") + 1
            session.save(update_fields=["transcript", "modified_at", "version"])
            session.refresh_from_db(fields=["version"])

            self._emit_event(
                self._make_event(
                    event_type=DomainEventOutbox.EventType.INTERVIEW_CHAT_TURN,
                    entity_id=session.id,
                    workspace_id=session.workspace_id,
                    payload={
                        "session_kind": session.session_kind,
                        "user_message": user_message,
                        "reply": reply,
                        "extracted_fields": list(extracted.keys()),
                        # memory.projector's MemoryProjector reads this to
                        # resolve who the consolidated fact belongs to
                        # (DomainEvent carries no actor identity of its own,
                        # see application/base.py::_make_event) -- final
                        # whole-branch review Finding 2.
                        "user_id": str(ctx.user_id),
                        # Stamped here, at emission time, because THIS is the
                        # only place real request-scoped tenant context is
                        # available -- the projector runs in a Celery worker
                        # outside any request/tenant context, and resolving
                        # workspace_id -> tenant_id there via a DB query would
                        # be RLS-blocked (no app.current_tenant session
                        # variable armed yet, chicken-and-egg -- see
                        # memory/projector.py's module docstring, final
                        # whole-branch review round-2 Finding A). Same fix
                        # shape as user_id above.
                        "tenant_id": str(ctx.tenant_id),
                        # RFC #1002 PR C: the session's backing Artifact (the
                        # FK target of InterviewSession.artifact; None for a
                        # multi-mode session) plus the artifact_type the
                        # protocol captures, so the consolidation pipeline can
                        # scope facts to the artifact. `session.artifact_id`
                        # is the Artifact PK column access -- the same id
                        # space memory.models.MemoryEntry.artifact uses.
                        "artifact_id": (
                            str(session.artifact_id) if session.artifact_id else None
                        ),
                        "entity_type": session.artifact_type,
                    },
                )
            )

        # L2.4: deliberately OUTSIDE the atomic block above -- the turn is
        # already committed, so a compression failure (or a slow second LLM
        # call) can neither roll back nor lose it. Never raises; see
        # _compress_transcript_if_needed's contract.
        self._compress_transcript_if_needed(ctx, session)

        return {"reply": reply, "state": self.get_state(ctx, session_id)}

    def _generate_multi_chat_turn(
        self, ctx, session: InterviewSession, user_message: str
    ) -> dict[str, Any]:
        """One free-form multi-artifact chat turn (multi-artifact plan Task 5).

        Deliberately NOT ``get_state()``-backed: that helper resolves the
        per-artifact-type protocol via ``get_protocol()``, which has no
        answer for a multi session's ``artifact_type=None`` (it would raise
        ProtocolValidationError). The state dict below mirrors get_state's
        shape minus phase/missing_fields, which do not exist in multi mode.

        Unlike single mode there is no per-field extraction step: the whole
        reply is parsed as one fenced-JSON artifact proposal and stored
        under ``grounding_snapshot["pending_proposal"]`` when it parses
        (parse_multi_proposal already returns None for no-fence/malformed/
        non-list payloads, so "no proposal this turn" degrades gracefully).
        """
        from application.interview_multi_protocol import (
            get_multi_protocol_prompt,
            parse_multi_proposal,
        )
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import (
            approximate_token_count,
            is_over_daily_limit,
            record_token_usage,
        )

        provider, provider_name, resolve_error = self._resolve_provider()
        if provider is None:
            # NOT fail-open -- same contract as single-mode generate_chat_turn.
            raise ValidationError(f"No LLM provider available for interview chat: {resolve_error}")

        audit_logger = LlmAuditLogger()
        entity_id = str(session.id)

        # REQ-106: per-tenant daily token budget, mirrored 1:1 from the
        # single-mode path (review-2 fixes M2/M3). This free-form flow
        # bypasses CapabilityRouter, so nothing else enforces the budget --
        # and not fail-open here either: an exhausted budget still means
        # "cannot chat right now", not "chat silently does nothing".
        if is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.chat_turn",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise ValidationError(
                "Daily LLM token limit exceeded for this tenant. Try again later "
                "or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        prompt = get_multi_protocol_prompt(ctx, session.workspace_id, user_message, session.transcript)
        timeout = resolve_timeout_seconds("interview.chat_turn")
        try:
            reply = provider.complete(prompt, purpose="interview.chat_turn", timeout=timeout)
        except Exception as error:  # noqa: BLE001 -- mirror single-mode error surfacing
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.chat_turn",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            raise ValidationError(f"Interview chat LLM call failed: {error}") from error

        audit_logger.log_llm_call(
            provider=provider_name,
            capability="interview.chat_turn",
            artifact_id=entity_id,
            token_usage=None,
            success=True,
            error=None,
        )
        # SA-26: this used to hardcode input_tokens=0, leaving the daily
        # budget (is_over_daily_limit above) blind to this call's real
        # spend. Estimate both sides client-side, matching every other
        # free-form path (see ``approximate_token_count``).
        record_token_usage(
            provider=provider_name,
            capability="interview.chat_turn",
            input_tokens=approximate_token_count(prompt),
            output_tokens=approximate_token_count(reply),
        )

        # Multi-mode turns use role/content keys -- the shape
        # get_multi_protocol_prompt() renders back into the next prompt.
        # Single mode's role/text/timestamp shape never mixes in here.
        session.transcript = [
            *session.transcript,
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ]
        proposal = parse_multi_proposal(reply)
        if proposal is not None:
            session.grounding_snapshot = {
                **session.grounding_snapshot,
                "pending_proposal": proposal,
            }
        # Same optimistic-concurrency bump as the single-mode chat save
        # (review-2 fix n2): a multi chat turn must not silently overwrite a
        # concurrent edit either.
        # DB write + event publish grouped in their own atomic block --
        # same rationale as the single-mode path above (avoid holding a
        # transaction open across the LLM call already made further up).
        with transaction.atomic():
            session.version = F("version") + 1
            session.save(update_fields=["transcript", "grounding_snapshot", "modified_at", "version"])
            session.refresh_from_db(fields=["version"])

            self._emit_event(
                self._make_event(
                    event_type=DomainEventOutbox.EventType.INTERVIEW_CHAT_TURN,
                    entity_id=session.id,
                    workspace_id=session.workspace_id,
                    payload={
                        "session_kind": session.session_kind,
                        "user_message": user_message,
                        "reply": reply,
                        "has_proposal": proposal is not None,
                        # See generate_chat_turn's identical addition above
                        # -- final whole-branch review Finding 2.
                        "user_id": str(ctx.user_id),
                        # See generate_chat_turn's identical addition above
                        # -- final whole-branch review round-2 Finding A.
                        "tenant_id": str(ctx.tenant_id),
                    },
                )
            )

        return {
            "reply": reply,
            "proposal": proposal,
            "state": {
                "session_id": str(session.id),
                "status": session.status,
                # Finding B2, second half: the chat pane replaces its whole
                # interview object with this state after every turn. Omitting
                # the discriminator here would silently demote the session to
                # "single" from turn 1 onwards, even with get_state() fixed.
                "session_kind": session.session_kind,
                "collected_fields": session.collected_fields,
                "grounding_snapshot": session.grounding_snapshot,
                "transcript": session.transcript,
            },
        }
